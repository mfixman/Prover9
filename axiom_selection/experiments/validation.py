import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import random
import sys
import time

folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(folder))
from portfolio import Premises, Slice, run_schedule
from problem_split import ProblemSplit
from prepare import prepare_bounded

predictor = None

def initialize(cpus):
    global predictor
    identity = multiprocessing.current_process()._identity[0]
    os.sched_setaffinity(0, {cpus[(identity - 1) % len(cpus)]})
    from predict import Predictor
    predictor = Predictor()

def sample(tptp, part, size, seed, excluded = ()):
    import re

    split = ProblemSplit(10, [part], scheme = 4)
    paths = sorted((Path(tptp) / 'Problems').glob('*/*-*.p'))
    random.Random(seed).shuffle(paths)
    selected, seen = [], set(excluded)
    for path in paths:
        family = path.stem[:6]
        if family in seen or not split.contains(path):
            continue

        header = path.open().read(16000)
        if re.search(r'%\s*Status\s*:\s*Unsatisfiable\b', header) and re.search(r'%\s*SPC\s*:\s*CNF_', header):
            selected.append(str(path))
            seen.add(family)
        if len(selected) == size:
            break

    return selected

def evaluate(path, tptp, output):
    path = Path(path)
    output = Path(output) / path.stem
    output.mkdir()
    prepared = prepare_bounded(path, tptp, predictor, output / 'prepared.json')
    if 'error' in prepared:
        return {'problem': path.stem, 'preparation_error': prepared['error']}

    strategies = list(Premises)
    random.Random(path.stem).shuffle(strategies)
    results = {}
    for mode in strategies:
        budget = 20 if mode in (Premises.Full, Premises.Ranked) else 8
        results[mode] = run_schedule(prepared, [Slice(mode, budget)], budget, output / mode)

    result = {'problem': path.stem, 'parse_s': prepared['parse_s'], 'score_s': prepared['score_s'], 'results': results}
    (output / 'results.json').write_text(json.dumps(result, indent = 2))
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type = Path, required = True)
    parser.add_argument('--count', type = int, default = 72)
    args = parser.parse_args()
    args.output.mkdir(parents = True, exist_ok = False)
    cpus = sorted(os.sched_getaffinity(0))[:17]
    tptp = folder.parent.parent / 'TPTP'
    paths = sample(tptp, 8, args.count, 2026102401)

    manifest = {'split': {'scheme': 4, 'split': 10, 'parts': [8]}, 'paths': paths, 'cpus': cpus,
                'model_sha256': hashlib.sha256((folder / 'models/torok.ts').read_bytes()).hexdigest(),
                'protocol': 'Warm-model validation; charge measured per-problem parsing and scoring to every guided arm. Full/Ranked:20s; subsets:8s. Preparation cap:5s. No test-set tuning.'}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent = 2))
    started = time.monotonic()
    results = []

    with ProcessPoolExecutor(max_workers = len(cpus), mp_context = multiprocessing.get_context('spawn'), initializer = initialize, initargs = (cpus,)) as pool:
        futures = [pool.submit(evaluate, path, str(tptp), str(args.output)) for path in paths]
        for future in as_completed(futures):
            results.append(future.result())
            (args.output / 'results.json').write_text(json.dumps(results, indent = 2))
            counts = {str(mode): sum(r.get('results', {}).get(mode, {}).get('proved', False) for r in results) for mode in Premises}
            print(len(results), counts, flush = True)

    manifest['elapsed_s'] = time.monotonic() - started
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent = 2))
    print('Elapsed',manifest['elapsed_s'],flush = True)

if __name__ == '__main__':
    main()
