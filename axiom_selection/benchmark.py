import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import queue
import random
import re
import signal
import subprocess
import sys
import threading
import time

folder = Path(__file__).resolve().parent

def candidates(tptp, seed):
    from environment import connections_root
    connections_root()
    from axiom_prediction.split import ProblemSplit

    split = ProblemSplit(10, [9], scheme = 4)
    paths = sorted((tptp / 'Problems').glob('*/*-*.p'))
    random.Random(seed).shuffle(paths)
    chosen, families = [], set()
    for path in paths:
        family = path.stem[:6]
        if family in families or not split.contains(path):
            continue

        header = path.open().read(16000)
        if re.search(r'%\s*Status\s*:\s*Unsatisfiable\b', header) and re.search(r'%\s*SPC\s*:\s*CNF_', header):
            chosen.append(path)
            families.add(family)

    return chosen

def revision(path):
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text = True).strip()

def run_arm(path, mode, seed, cpu, args):
    output = args.output / path.stem / f'{mode}-{seed}.json'
    output.parent.mkdir(parents = True, exist_ok = True)
    command = ['taskset', '-c', str(cpu), sys.executable, str(folder / 'run.py'), str(path), '--mode', mode, '--seed', str(seed), '--seconds', str(args.seconds), '--tptp', str(args.tptp), '--output', str(output)]
    env = {**os.environ, 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1'}
    started = time.monotonic()

    with output.with_suffix('.driver.log').open('w') as log:
        process = subprocess.Popen(command, stdout = log, stderr = subprocess.STDOUT, env = env, start_new_session = True)
        try:
            process.wait(timeout = args.seconds)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()

    elapsed = time.monotonic() - started
    if output.exists():
        result = json.loads(output.read_text())
    else:
        result = {'problem': path.stem, 'mode': mode, 'seed': seed, 'outcome': 'WallTimeout' if elapsed >= args.seconds else 'DriverError'}

    result.update(end_to_end_s = elapsed, cpu = cpu, driver_exit = process.returncode)
    output.write_text(json.dumps(result, indent = 2))
    return result

def worker(cpu, pending, args, deadline, completed, lock):
    while time.monotonic() < deadline:
        try:
            path = pending.get_nowait()
        except queue.Empty:
            return

        arms = [('Baseline', 1), ('Torok', 1), ('Torok', 2), ('Uniform', 1), ('Uniform', 2)]
        local_seed = int.from_bytes(hashlib.sha256(path.stem.encode()).digest()[:8], 'big')
        random.Random(local_seed).shuffle(arms)
        results = [run_arm(path, mode, seed, cpu, args) for mode, seed in arms]
        with lock:
            completed.append({'problem': path.stem, 'results': results})
            (args.output / 'results.json').write_text(json.dumps(completed, indent = 2))
            print(f'Completed {len(completed)}: {path.stem}; ' + ', '.join(f'{r["mode"]}/{r["seed"]}={r["outcome"]}' for r in results), flush = True)

        pending.task_done()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tptp', type = Path, default = folder.parent.parent / 'TPTP')
    parser.add_argument('--output', type = Path, required = True)
    parser.add_argument('--seconds', type = float, default = 15)
    parser.add_argument('--launch-seconds', type = float, default = 330)
    parser.add_argument('--workers', type = int, default = 18)
    args = parser.parse_args()

    cpus = sorted(os.sched_getaffinity(0))[:19]
    os.sched_setaffinity(0, cpus)
    args.workers = min(args.workers, 18, len(cpus))
    args.output.mkdir(parents = True, exist_ok = False)
    paths = candidates(args.tptp, 2026102303)
    sources = list(folder.glob('*.py')) + list(folder.glob('*.c')) + [folder.parent / 'provers.src/giv_select.c']

    metadata = {'seed': 2026102303, 'split': {'scheme': 4, 'split': 10, 'parts': [9]}, 'candidate_count': len(paths), 'sample_order': list(map(str, paths)), 'seconds_per_arm_including_startup': args.seconds, 'launch_seconds': args.launch_seconds, 'workers': args.workers, 'cpus': cpus, 'prover_revision': revision(folder.parent), 'connections_revision': revision(Path('~/TP/connections').expanduser()), 'model_sha256': hashlib.sha256((folder / 'models/torok.ts').read_bytes()).hexdigest(), 'source_sha256': {str(p.relative_to(folder.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}, 'selection': 'One random CNF Unsatisfiable variant per TPTP family, scheme-4 test part 9; stop launching whole matched groups at the preregistered wall deadline; no filtering on baseline outcomes.'}
    (args.output / 'manifest.json').write_text(json.dumps(metadata, indent = 2))
    started = time.monotonic()
    pending, completed, lock = queue.Queue(), [], threading.Lock()
    for path in paths:
        pending.put(path)

    print(f'Starting {len(paths)} eligible families on {args.workers} CPUs; 5 matched arms each.', flush = True)
    with concurrent.futures.ThreadPoolExecutor(max_workers = args.workers) as executor:
        futures = [executor.submit(worker, cpu, pending, args, started + args.launch_seconds, completed, lock) for cpu in cpus[:args.workers]]
        for future in futures:
            future.result()

    metadata['elapsed_s'] = time.monotonic() - started
    metadata['completed_problems'] = len(completed)
    (args.output / 'manifest.json').write_text(json.dumps(metadata, indent = 2))
    print(json.dumps({'completed_problems': len(completed), 'elapsed_s': metadata['elapsed_s']}), flush = True)

if __name__ == '__main__':
    main()
