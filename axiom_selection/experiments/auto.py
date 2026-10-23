import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing
from pathlib import Path
import os
import random
import sys

folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(folder))
from portfolio import search
from supplement import initialize

def evaluate(directory):
    p = json.loads((directory / 'prepared.json').read_text())
    old = json.loads((directory / 'results.json').read_text())['results']['Full']
    if old['proved'] and old['charged_s'] <= p['parse_s'] + 1:
        return {'problem': directory.name, 'results': {k:old for k in ['Auto2', 'Auto2Filter', 'Auto2Soft']}}

    all_indices = list(range(len(p['clauses'])))
    conjectures = set(p['conjectures'])
    candidates = [i for i in all_indices if i not in conjectures]
    ranked = sorted(candidates, key = lambda i: (-p['weights'][i], i))
    required = conjectures | set(ranked[:64])
    selected = [i for i, w in enumerate(p['weights']) if i in required or w >= 0.01]
    weights = directory / 'soft.weights'
    weights.write_text(str(len(p['weights'])) + '\n' + '\n'.join(map(str, p['weights'])) + '\n')

    modes = ['Auto2', 'Auto2Filter', 'Auto2Soft']
    random.Random(directory.name).shuffle(modes)
    results = {}
    for mode in modes:
        charged = p['parse_s'] + 1 + (p['score_s'] if mode != 'Auto2' else 0)
        env = {'PROVER9_TOROK_MODE':'Soft', 'PROVER9_TOROK_WEIGHTS':str(weights.resolve())} if mode == 'Auto2Soft' else {}
        binary = folder / 'build/prover9-soft' if mode == 'Auto2Soft' else None
        result = search(p['clauses'], selected if mode == 'Auto2Filter' else all_indices, 20 - charged, directory / mode, binary, env, ['set(auto2).'])
        results[mode] = {'charged_s':charged + result['search_s'], **result}

    return {'problem':directory.name, 'results':results}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type = Path)
    args = parser.parse_args()
    cpus = sorted(os.sched_getaffinity(0))[:17]
    paths = [p.parent for p in args.directory.glob('*/results.json')]
    results = []
    with ProcessPoolExecutor(max_workers = len(cpus), mp_context = multiprocessing.get_context('spawn'), initializer = initialize, initargs = (cpus,)) as pool:
        for future in as_completed([pool.submit(evaluate, p) for p in paths]):
            results.append(future.result())
            (args.directory / 'auto.json').write_text(json.dumps(results, indent = 2))
            print(len(results), {k:sum(r['results'][k]['proved'] for r in results) for k in ['Auto2','Auto2Filter','Auto2Soft']}, flush = True)

if __name__ == '__main__':
    main()
