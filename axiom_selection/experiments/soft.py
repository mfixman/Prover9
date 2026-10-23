import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing
import os
from pathlib import Path
import sys

folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(folder))
from portfolio import search
from supplement import initialize

def evaluate(directory, strength, mode):
    prepared = json.loads((directory / 'prepared.json').read_text())
    old = json.loads((directory / 'results.json').read_text())
    baseline = old['results']['Full']
    if baseline['proved'] and baseline['charged_s'] <= prepared['parse_s'] + 1:
        return {'problem': directory.name, 'proved': True, 'charged_s': baseline['charged_s'], 'probe': True}

    charged = prepared['parse_s'] + 1 + prepared['score_s']
    weights = directory / 'soft.weights'
    weights.write_text(str(len(prepared['weights'])) + '\n' + '\n'.join(map(str, prepared['weights'])) + '\n')
    result = search(prepared['clauses'], list(range(len(prepared['clauses']))), max(0.001, 20 - charged), directory / f'{mode}-{strength:g}', folder / 'build/prover9-soft', {'PROVER9_TOROK_STRENGTH': str(strength), 'PROVER9_TOROK_MODE': mode, 'PROVER9_TOROK_WEIGHTS': str(weights.resolve())})
    return {'problem': directory.name, 'charged_s': charged + result['search_s'], **result}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type = Path)
    parser.add_argument('--strength', type = float, default = 1)
    parser.add_argument('--mode', default = 'Soft', choices = ['Soft', 'Tie'])
    args = parser.parse_args()
    cpus = sorted(os.sched_getaffinity(0))[:17]
    paths = [p.parent for p in args.directory.glob('*/results.json')]
    results = []
    with ProcessPoolExecutor(max_workers = len(cpus), mp_context = multiprocessing.get_context('spawn'), initializer = initialize, initargs = (cpus,)) as pool:
        for future in as_completed([pool.submit(evaluate, p, args.strength, args.mode) for p in paths]):
            results.append(future.result())
            (args.directory / f'{args.mode.lower()}-{args.strength:g}.json').write_text(json.dumps(results, indent = 2))
            print(len(results), sum(r['proved'] for r in results), flush = True)

if __name__ == '__main__':
    main()
