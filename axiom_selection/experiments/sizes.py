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

def strategy(p, directory, size):
    indices = list(range(len(p['clauses'])))
    charged = p['parse_s']
    conjectures = set(p['conjectures'])
    candidates = [i for i in indices if i not in conjectures]
    if size == 0 or len(candidates) <= size:
        r = search(p['clauses'], indices, 30 - charged, directory / f'Size{size}')
        return {'charged_s':charged + r['search_s'], **r}

    probe = search(p['clauses'], indices, 1, directory / f'Size{size}Probe')
    charged += probe['search_s']
    if probe['proved']:
        return {'charged_s':charged, **probe}

    charged += p['score_s']
    ranked = sorted(candidates, key = lambda i:(-p['weights'][i], i))
    selected = conjectures | set(ranked[:size])
    usable = [i for i in indices if i not in selected]
    r = search(p['clauses'], sorted(selected), 30 - charged, directory / f'Size{size}', usable = usable)
    charged += r['search_s']
    if not r['proved'] and charged < 29.99:
        r = search(p['clauses'], indices, 30 - charged, directory / f'Size{size}Fallback')
        charged += r['search_s']

    return {'charged_s':charged, **r}

def evaluate(source, output):
    p = json.loads((source / 'prepared.json').read_text())
    directory = Path(output) / source.name
    directory.mkdir()
    sizes = [0, 1, 4, 8, 16]
    random.Random(source.name).shuffle(sizes)
    result = {'problem':source.name, 'results':{str(k):strategy(p, directory, k) for k in sizes}}
    (directory / 'result.json').write_text(json.dumps(result, indent = 2))
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type = Path, required = True)
    parser.add_argument('--output', type = Path, required = True)
    args = parser.parse_args()
    args.output.mkdir(parents = True, exist_ok = False)
    cpus = sorted(os.sched_getaffinity(0))[:18]
    paths = [p.parent for p in args.source.glob('*/results.json')]
    results = []
    manifest = {'source':str(args.source), 'cpus':cpus, 'seconds':30, 'sizes':[0,1,4,8,16], 'protocol':'Development screen on previously scoreable cases; cached predictions charged at measured per-problem cost; not a final end-to-end comparison.'}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent = 2))
    with ProcessPoolExecutor(max_workers = len(cpus), mp_context = multiprocessing.get_context('spawn'), initializer = initialize, initargs = (cpus,)) as pool:
        for future in as_completed([pool.submit(evaluate, p, args.output) for p in paths]):
            results.append(future.result())
            (args.output / 'results.json').write_text(json.dumps(results, indent = 2))
            print(len(results),{k:sum(r['results'][str(k)]['proved'] for r in results) for k in [0,1,4,8,16]},flush = True)

if __name__ == '__main__':
    main()
