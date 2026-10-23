import csv
import fcntl
import json
from pathlib import Path
import time

from experiment_output import append_result, fields

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
    saved = read_result(directory / 'results.json', [])
    indexed = {(r['problem'], r.get('replicate', 0)):r for r in saved}
    completed, pending = [], []
    for replicate in range(repeats):
        for path in paths:
            target = case_directory(directory, path, replicate)
            result = indexed.get((Path(path).stem, replicate), {'problem':Path(path).stem, 'replicate':replicate, 'results':{}})
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

def start_session(directory, manifest, source_root):
    session = directory / 'sessions' / str(time.time_ns())
    session.mkdir(parents = True)
    write_json(session / 'manifest.json', manifest)
    for name in manifest['source_sha256']:
        destination = session / 'source' / name
        destination.parent.mkdir(parents = True, exist_ok = True)
        destination.write_bytes((source_root / name).read_bytes())

    return session

def rebuild_csv(path, results):
    if path is None:
        return

    temporary = path.with_suffix('.csv.tmp')
    with temporary.open('w', newline = '') as stream:
        csv.DictWriter(stream, fieldnames = fields).writeheader()
    for result in results:
        append_result(temporary, result)

    temporary.replace(path)
