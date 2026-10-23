import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing
import os
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio import Premises, Slice, run_schedule

def initialize(cpus):
    identity = multiprocessing.current_process()._identity[0]
    os.sched_setaffinity(0, {cpus[(identity - 1) % len(cpus)]})

def evaluate(path):
    prepared = json.loads((path / 'prepared.json').read_text())
    if 'error' in prepared:
        return

    result = json.loads((path / 'results.json').read_text())
    modes = [Premises.P001, Premises.P01, Premises.P05]
    random.Random(path.name).shuffle(modes)
    for mode in modes:
        result['results'][mode] = run_schedule(prepared, [Slice(mode, 20)], 20, path / mode)

    (path / 'results.json').write_text(json.dumps(result, indent = 2))
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type = Path)
    args = parser.parse_args()
    paths = [p.parent for p in args.directory.glob('*/results.json')]
    cpus = sorted(os.sched_getaffinity(0))[:17]
    with ProcessPoolExecutor(max_workers = len(cpus), mp_context = multiprocessing.get_context('spawn'), initializer = initialize, initargs = (cpus,)) as pool:
        for i, future in enumerate(as_completed([pool.submit(evaluate, p) for p in paths])):
            result = future.result()
            print(i + 1, result['problem'], {k:v['proved'] for k,v in result['results'].items()}, flush = True)

    rows = [json.loads(p.read_text()) for p in args.directory.glob('*/results.json')]
    (args.directory / 'supplement.json').write_text(json.dumps(rows, indent = 2))

if __name__ == '__main__':
    main()
