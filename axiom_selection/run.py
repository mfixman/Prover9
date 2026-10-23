import argparse
from enum import StrEnum
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

class Mode(StrEnum):
    Baseline = 'Baseline'
    Torok = 'Torok'
    Uniform = 'Uniform'

def arguments():
    parser = argparse.ArgumentParser(description = 'Run Prover9 on shared CNF with optional Torok guidance.')
    parser.add_argument('problem', type = Path)
    parser.add_argument('--mode', type = Mode, choices = list(Mode), default = Mode.Torok)
    parser.add_argument('--tptp', type = Path, default = Path(__file__).resolve().parents[2] / 'TPTP')
    parser.add_argument('--seconds', type = float, default = 20)
    parser.add_argument('--seed', type = int, default = 1)
    parser.add_argument('--output', type = Path, required = True)
    parser.add_argument('--model', type = Path, default = Path(__file__).parent / 'models/torok.ts')
    return parser.parse_args()

def execute(args, started, result):
    from problem import load_problem, prover_input
    from predict import save_weights

    matrix = load_problem(args.problem, args.tptp)
    result['clauses'] = len(matrix.clauses)
    result['parse_s'] = time.monotonic() - started
    text = prover_input(matrix, args.seconds)
    args.output.with_suffix('.in').write_text(text)

    if args.mode == Mode.Torok:
        from predict import Predictor
        loading = time.monotonic()
        predictor = Predictor(args.model)
        result['model_load_s'] = time.monotonic() - loading
        weights, info = predictor.predict(matrix)
        result.update(info)
    else:
        weights = [1.0] * len(matrix.clauses)

    remaining = args.seconds - (time.monotonic() - started)
    if remaining <= 0:
        result['outcome'] = 'PreprocessingTimeout'
        return

    env = {key: value for key, value in os.environ.items() if not key.startswith('PROVER9_TOROK_')}
    with tempfile.TemporaryDirectory(prefix = 'prover9-torok-') as folder:
        if args.mode != Mode.Baseline:
            weights_path = Path(folder) / 'weights'
            save_weights(weights_path, weights)
            env.update(PROVER9_TOROK_WEIGHTS = str(weights_path), PROVER9_TOROK_SEED = str(args.seed))

        root = Path(__file__).resolve().parents[1]
        binary = root / ('provers.src/prover9' if args.mode == Mode.Baseline else 'axiom_selection/build/prover9-torok')
        run_search(binary, text, env, remaining, args.output, result)

def run_search(binary, text, env, remaining, output, result):
    import re

    started = time.monotonic()
    try:
        process = subprocess.run([str(binary)], input = text, text = True, capture_output = True, env = env, timeout = remaining)
        log = process.stdout + process.stderr
        result['exit_code'] = process.returncode
        result['outcome'] = 'Proved' if 'THEOREM PROVED' in log else 'Unsolved'
    except subprocess.TimeoutExpired as error:
        log = ((error.stdout or b'') + (error.stderr or b'')).decode(errors = 'replace')
        result['outcome'] = 'SearchTimeout'

    output.with_suffix('.log').write_text(log)
    result['search_s'] = time.monotonic() - started
    cpu = re.findall(r'User_CPU=([\d.]+), System_CPU=([\d.]+)', log)
    if cpu:
        result['search_cpu_s'] = sum(map(float, cpu[-1]))

    if 'Fatal error' in log or 'FATAL ERROR' in log:
        result['outcome'] = 'ProverError'

    result['weighted_queue_used'] = '% Torok:' in log

def main():
    started = time.monotonic()
    args = arguments()
    args.output.parent.mkdir(parents = True, exist_ok = True)
    result = {'problem': args.problem.stem, 'mode': args.mode, 'seed': args.seed}
    try:
        execute(args, started, result)
    except Exception as error:
        result.update(outcome = 'InputOrModelError', error = repr(error))
    finally:
        result['total_s'] = time.monotonic() - started
        args.output.write_text(json.dumps(result, indent = 2))

    print(json.dumps(result), flush = True)
    return 1 if result['outcome'] in ('InputOrModelError', 'ProverError') else 0

if __name__ == '__main__':
    raise SystemExit(main())
