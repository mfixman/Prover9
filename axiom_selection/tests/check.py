from pathlib import Path
import os
import subprocess
import sys
import tempfile

folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(folder))
from environment import connections_root
from problem import load_problem, prover_input
from predict import Predictor

def check_export():
    from axiom_prediction.model import AxiomPredictor

    root = connections_root()
    original = AxiomPredictor.load(root / 'models/torok.pt', device = 'cpu')
    exported = Predictor()
    for name in ['GRP001-1', 'SYN139-1']:
        matrix = load_problem(folder.parent.parent / f'TPTP/Problems/{name[:3]}/{name}.p', folder.parent.parent / 'TPTP')
        weights, _ = exported.predict(matrix)
        conjectures = list(matrix.conjecture_clauses)
        axioms = [i for i in range(len(matrix.clauses)) if i not in conjectures]
        expected = original.predict(matrix, axiom_clause_ids = axioms, conjecture_clause_ids = conjectures)
        assert max(abs(weights[item.clause_index] - max(1e-6, item.probability)) for item in expected) < 1e-5

    print('Copied TorchScript probabilities match the original checkpoint.')

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
    check_export()
    check_logic()
