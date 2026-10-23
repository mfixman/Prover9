from pathlib import Path
import os
import subprocess
import sys
import tempfile

folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(folder))
from preprocessing import check_preprocessing
from problem import load_problem, prover_input
from predict import Predictor

def check_logic():
    cases = [
        ('cnf(a,axiom,p(a)). cnf(b,negated_conjecture,~p(a)).', True),
        ('cnf(a,axiom,p(a)). cnf(b,axiom,~p(b)).', False),
        ('cnf(a,axiom,a=b). cnf(b,axiom,p(a)). cnf(c,negated_conjecture,~p(b)).', True),
        ('cnf(a,axiom,p|q). cnf(b,axiom,~p|q). cnf(c,axiom,p|~q). cnf(d,axiom,~p|~q).', True),
        ('cnf(a,axiom,a!=a).', True),
        ('cnf(a,axiom,$false).', True),
        ('cnf(a,axiom,$true).', False),
    ]
    with tempfile.TemporaryDirectory() as directory:
        for index, (source, proves) in enumerate(cases):
            path = Path(directory) / 'test.p'
            path.write_text(source)
            matrix = load_problem(path, directory)
            text = 'clear(predicate_elim).\n' + prover_input(matrix, 2)
            outputs = []
            for binary in [folder.parent / 'provers.src/prover9', folder / 'build/prover9-torok']:
                env = {k: v for k, v in os.environ.items() if not k.startswith('PROVER9_TOROK_')}
                result = subprocess.run([str(binary)], input = text, text = True, capture_output = True, timeout = 3, env = env)
                outputs.append(result.stdout.split('============================== INPUT')[1].split('User_CPU=')[0])
                assert ('THEOREM PROVED' in result.stdout) == proves

            assert outputs[0] == outputs[1], 'Disabled adapter changed proof/search output'

    print('CNF signs, distinct constants, equality, and disabled-path parity passed.')

if __name__ == '__main__':
    subprocess.run(['gcc', '-O2', '-Wall', str(folder / 'tests/selection.c'), str(folder.parent / 'ladr/libladr.a'), '-lm', '-o', str(folder / 'build/check-selection')], check = True)
    subprocess.run([str(folder / 'build/check-selection')], check = True)
    check_preprocessing()
    check_logic()
