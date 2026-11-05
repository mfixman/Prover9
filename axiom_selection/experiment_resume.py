import csv
import fcntl
import json
from pathlib import Path

from experiment_output import append_result, fields, read_csv_results, strategy_path, declared_status

def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent = 2) + '\n')
    temporary.replace(path)

def read_result(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def lock_output(directory):
    lock = (directory / '.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise ValueError(f'Another experiment is using {directory}') from None

    return lock

def case_directory(directory, path, replicate):
    suffix = f'-repeat{replicate + 1}' if replicate else ''
    return directory / (Path(path).stem + suffix)

def valid_outcome(outcome):
    return isinstance(outcome, dict) and ('proved' in outcome or 'error' in outcome)

def recover(directory, paths, modes, repeats):
    saved = read_result(directory / 'results.json', []) + read_csv_results(directory)
    indexed = {(r['problem'], r.get('replicate', 0)):r for r in saved}
    completed, pending = [], []
    for replicate in range(repeats):
        for path in paths:
            target = case_directory(directory, path, replicate)
            result = indexed.get((Path(path).stem, replicate), {'problem':Path(path).stem, 'replicate':replicate, 'results':{}})
            result.setdefault('declared_status', declared_status(path))
            checkpoint = read_result(target / 'results.json', {})
            result['results'].update(checkpoint.get('results', {}))
            if 'cpu' in checkpoint:
                result['cpu'] = checkpoint['cpu']
            result['mode_cpus'] = checkpoint.get('mode_cpus', result.get('mode_cpus', {}))
            for mode in modes:
                if not valid_outcome(result['results'].get(mode)):
                    outcome = read_result(target / mode / 'result.json', {})
                    if valid_outcome(outcome):
                        result['results'][mode] = outcome
                    else:
                        result['results'].pop(mode, None)

            if all(valid_outcome(result['results'].get(mode)) for mode in modes):
                completed.append(result)
            else:
                pending.append((path, replicate, result))

    return completed, pending

def check_manifest(directory, manifest):
    path = directory / 'manifest.json'
    if not path.exists():
        return None

    old = json.loads(path.read_text())
    keys = ['seconds', 'modes', 'minimum', 'threshold', 'probe', 'repeats', 'model_sha256', 'binary_sha256']
    different = [key for key in keys if key in old and old[key] != manifest[key]]
    if sorted(Path(p).name for p in old['paths']) != sorted(Path(p).name for p in manifest['paths']):
        different.append('paths')
    if different:
        raise ValueError('Cannot resume with changed ' + ', '.join(different) + '; use a different --output.')

    return old

def rebuild_csv(path, results, metadata = None):
    if path is None:
        return

    modes = (metadata or {}).get('modes', [])
    modes = set(modes) | {m for r in results for m in r['results']}
    temporary = path.with_name('rebuilding.csv')
    pairs = {(mode, 0) for mode in modes}
    pairs.update((m, r.get('replicate', 0)) for r in results for m in r['results'])
    for mode, replicate in pairs:
        destination = strategy_path(temporary, mode, replicate)
        with destination.open('w', newline = '') as stream:
            csv.DictWriter(stream, fieldnames = fields).writeheader()

        for result in results:
            if mode in result['results'] and result.get('replicate', 0) == replicate:
                append_result(temporary, {**result, 'results':{mode:result['results'][mode]}}, (metadata or {}).get('partition'))

        destination.replace(strategy_path(path, mode, replicate))
