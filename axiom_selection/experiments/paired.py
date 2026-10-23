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
from bounded import bounded
from premise_run import Mode, solve
from validation import sample
from problem_split import ProblemSplit
from experiment_output import default_output, prepare_output, append_result
from experiment_resume import write_json, lock_output, case_directory, recover, check_manifest, start_session, rebuild_csv

predictor = None

def initialize(cpus, tptp):
    global predictor
    identity = multiprocessing.current_process()._identity[0]
    os.sched_setaffinity(0, {cpus[(identity - 1) % len(cpus)]})
    from predict import Predictor
    predictor = Predictor()
    from problem import load_problem
    root = Path(tptp)
    warmup = load_problem(root / 'Problems/GRP/GRP001-1.p', root)
    for i in range(3):
        predictor.predict(warmup)

def evaluate(path, tptp, output, budget, threshold, probe, minimum, modes, replicate = 0, previous = None):
    path = Path(path)
    directory = case_directory(Path(output), path, replicate)
    directory.mkdir(exist_ok = True)
    modes = [Mode(m) for m in modes]
    random.Random(f'{path.stem}:{replicate}').shuffle(modes)
    cpu = min(os.sched_getaffinity(0))
    result = previous or {'problem': path.stem, 'replicate': replicate, 'cpu':cpu, 'results': {}}
    result.setdefault('cpu', cpu)
    result.setdefault('mode_cpus', {})
    for mode in result['results']:
        result['mode_cpus'].setdefault(mode, result['cpu'])

    for mode in modes:
        if mode in result['results']:
            continue

        target = directory / mode
        if target.exists():
            target.rename(directory / f'{mode}.interrupted-{time.time_ns()}')
        target.mkdir()
        run = lambda: solve(path, tptp, predictor, mode, budget - 0.05, target, threshold, probe, minimum)
        result['results'][mode] = bounded(run, budget, target / 'result.json', process_group = True)
        result['mode_cpus'][mode] = cpu
        write_json(directory / 'results.json', result)

    write_json(directory / 'results.json', result)
    return result

def main():
    allowed = sorted(os.sched_getaffinity(0))
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type = Path, help = 'CSV file or legacy output directory (default: axiom_selection/results/part-{part}.csv).')
    parser.add_argument('--manifest', type = Path)
    parser.add_argument('--tptp', type = Path, default = folder.parent.parent / 'TPTP', help = 'TPTP dataset root (default: sibling TPTP directory).')
    parser.add_argument('--all-cnf-unsat', action = 'store_true')
    parser.add_argument('--split', type = int, default = 1, help = 'Partition the selected problems into N stable hash parts (default: 1).')
    parser.add_argument('--part', '--parts', dest = 'parts', type = int, nargs = '+', help = 'Zero-based parts to run (default: all parts).')
    parser.add_argument('--count', type = int, default = 100)
    parser.add_argument('--seed', type = int, default = 2026102402)
    parser.add_argument('--seconds', type = float, default = 60, help = 'Wall seconds per strategy and problem (default: 60).')
    parser.add_argument('--threshold', type = float, default = 0.01)
    parser.add_argument('--probe', type = float, default = 1)
    parser.add_argument('--minimum', type = int, default = 16)
    parser.add_argument('--modes', nargs = '+', choices = list(Mode), default = [Mode.Baseline, Mode.TorokSupport, Mode.RandomSupport])
    parser.add_argument('--repeat', type = int, default = 1)
    parser.add_argument('--workers', type = int, default = len(allowed), help = 'Search workers (default: all CPUs in the process affinity mask).')
    parser.add_argument('--strategy', choices = ['support1', 'support4', 'support8', 'support16', 'weighted16', 'half1', 'half16', 'resume1', 'resume16', 'support16-longscore'])
    args = parser.parse_args()
    try:
        partition = ProblemSplit(args.split, args.parts, scheme = 5)
    except ValueError as error:
        parser.error(str(error))

    if args.strategy:
        special = {'support16-longscore':Mode.Support16LongScore, 'weighted16':Mode.WeightedSupport16, 'half1':Mode.HalfSupport1, 'half16':Mode.HalfSupport16,
                   'resume1':Mode.ResumeSupport1, 'resume16':Mode.ResumeSupport16}
        strategy_mode = special[args.strategy] if args.strategy in special else Mode(args.strategy.capitalize())
        args.modes = [Mode.Baseline, strategy_mode]
        args.minimum = 1 if args.strategy == 'half1' else 16
        if args.strategy.startswith('support') and args.strategy != 'support16-longscore':
            args.minimum = int(args.strategy.removeprefix('support'))
        args.probe = 1
    if not 1 <= args.workers <= len(allowed) or args.repeat < 1:
        parser.error(f'Use 1–{len(allowed)} workers and a positive repeat count.')
    requested_output = args.output or default_output(folder, partition.parts, partition.split)
    args.output, csv_output = prepare_output(requested_output)
    output_lock = lock_output(args.output)
    cpus = allowed[:args.workers]
    tptp = args.tptp.resolve()
    paths = []
    if not args.all_cnf_unsat and not args.manifest:
        paths = sample(tptp, 8, args.count, args.seed)

    split_description = 'scheme4 part8 development'
    if args.all_cnf_unsat:
        import re
        paths = []
        for path in sorted((tptp / 'Problems').glob('*/*-*.p')):
            header = path.open().read(16000)
            if re.search(r'%\s*Status\s*:\s*Unsatisfiable\b', header) and re.search(r'%\s*SPC\s*:\s*CNF_', header):
                paths.append(str(path))
        split_description = 'All known-unsatisfiable CNF variants, including model training families'
    if args.manifest:
        source_manifest = json.loads(args.manifest.read_text())
        paths = source_manifest['paths']
        split_description = source_manifest.get('split', 'User-supplied paths; split not asserted')

    candidate_count = len(paths)
    paths = partition.select(paths)
    source_names = ['premise_run.py', 'portfolio.py', 'bounded.py', 'native_search.c', 'predict.py', 'problem.py', 'half_support.py', 'live_search.py', 'experiment_output.py', 'experiment_resume.py', 'problem_split.py', 'experiments/paired.py', 'experiments/validation.py']
    source_names += [str(p.relative_to(folder)) for p in sorted((folder / 'torok_vendor').rglob('*')) if p.is_file() and (p.suffix in ('.py', '.json') or p.name == 'LICENSE')]
    manifest = {'tptp':str(tptp), 'paths': paths, 'split': split_description, 'seconds': args.seconds,
                'csv_output': str(csv_output) if csv_output else None,
                'partition': partition.to_dict(), 'candidate_count': candidate_count,
                'strategy': args.strategy, 'repeats': args.repeat, 'modes': args.modes, 'minimum': args.minimum, 'threshold': args.threshold, 'probe': args.probe, 'cpus': cpus,
                'model_sha256': hashlib.sha256((folder / 'models/torok.ts').read_bytes()).hexdigest(),
                'binary_sha256': hashlib.sha256((folder.parent / 'provers.src/prover9').read_bytes()).hexdigest(),
                'runner_sha256': {name: hashlib.sha256((folder / 'build' / name).read_bytes()).hexdigest() for name in ['native-search', 'native-search-control']},
                'source_sha256': {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in source_names},
                'protocol': 'Actual wall deadline includes parse, lazy scoring and search. Model loaded and warmed with three GRP001-1 forwards per worker before timing; warm batch deployment. RandomSupport selects the same fixed number of axioms without scoring; Random filtering pays scoring to match subset size.'}
    previous_manifest = check_manifest(args.output, manifest)
    session = start_session(args.output, manifest, folder)
    results, pending = recover(args.output, paths, args.modes, args.repeat)
    if previous_manifest is None:
        write_json(args.output / 'manifest.json', manifest)
    else:
        manifest = previous_manifest

    rebuild_csv(csv_output, results)
    write_json(args.output / 'results.json', results)
    print(f'Resuming: {len(results)} complete problem groups; {len(pending)} pending.', flush = True)
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers = len(cpus), mp_context = multiprocessing.get_context('spawn'), initializer = initialize, initargs = (cpus, str(tptp))) as pool:
        futures = [pool.submit(evaluate, p, str(tptp), str(args.output), args.seconds, args.threshold, args.probe, args.minimum, args.modes, repeat, previous) for p, repeat, previous in pending]
        for future in as_completed(futures):
            results.append(future.result())
            append_result(csv_output, results[-1])
            write_json(args.output / 'results.json', results)
            counts = {str(m):sum(r['results'][m].get('proved', False) for r in results) for m in args.modes}
            print(len(results), counts, flush = True)

    elapsed = time.monotonic() - started
    manifest['elapsed_s'] = manifest.get('elapsed_s', 0) + elapsed
    write_json(args.output / 'manifest.json', manifest)
    write_json(session / 'completion.json', {'elapsed_s':elapsed, 'groups':len(results)})
    output_lock.close()

if __name__ == '__main__':
    main()
