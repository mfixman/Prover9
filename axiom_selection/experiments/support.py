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

def strategy(p, directory, mode):
    indices = list(range(len(p['clauses'])))
    budget = 20 - p['parse_s']
    if mode == 'Baseline':
        r = search(p['clauses'], indices, budget, directory / 'FirstBaseline')
        return {'charged_s': p['parse_s'] + r['search_s'], **r}

    probe = search(p['clauses'], indices, min(1, budget), directory / f'{mode}Probe')
    charged = p['parse_s'] + probe['search_s']
    if probe['proved']:
        return {'charged_s':charged, **probe}

    charged += p['score_s']
    conjectures = set(p['conjectures'])
    candidates = [i for i in indices if i not in conjectures]
    ranked = sorted(candidates, key = lambda i: (-p['weights'][i], i))
    n = 16 if mode == 'Support16' else 64
    required = conjectures | set(ranked[:n])
    settings = []
    if mode == 'Auto2Filter':
        selected = [i for i in indices if i in required or p['weights'][i] >= .01]
        usable = []
        settings = ['set(auto2).']
    else:
        selected = sorted(required)
        usable = [i for i in indices if i not in required]

    r = search(p['clauses'], selected, max(.001, 20 - charged), directory / mode, settings = settings, usable = usable)
    charged += r['search_s']
    if not r['proved'] and charged < 19.99:
        r = search(p['clauses'], indices, 20 - charged, directory / f'{mode}Fallback')
        charged += r['search_s']

    return {'charged_s':charged, **r}

def evaluate(directory):
    p = json.loads((directory / 'prepared.json').read_text())
    modes = ['Baseline', 'Support16', 'Support64', 'Auto2Filter']
    random.Random(directory.name).shuffle(modes)
    return {'problem':directory.name, 'results':{mode:strategy(p, directory, mode) for mode in modes}}

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
            (args.directory / 'support.json').write_text(json.dumps(results, indent = 2))
            print(len(results), {k:sum(r['results'][k]['proved'] for r in results) for k in ['Baseline','Support16','Support64','Auto2Filter']}, flush = True)

if __name__ == '__main__':
    main()
