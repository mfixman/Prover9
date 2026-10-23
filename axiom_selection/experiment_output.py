import csv
from pathlib import Path

fields = ['problem', 'replicate', 'cpu', 'strategy', 'proved', 'elapsed_s', 'error']

def default_output(folder, parts, split):
    label = '-'.join(map(str, sorted(parts)))
    if len(parts) == split and split > 1:
        label = 'all'

    return folder / 'results' / f'part-{label}.csv'

def prepare_output(path):
    path = Path(path)
    csv_path = path if path.suffix.lower() == '.csv' else None
    directory = path.with_suffix('') if csv_path else path
    if path.exists() or directory.exists():
        raise FileExistsError(f'Output already exists: {path} or {directory}')

    directory.mkdir(parents = True)
    if csv_path:
        with csv_path.open('x', newline = '') as stream:
            csv.DictWriter(stream, fieldnames = fields).writeheader()

    return directory, csv_path

def append_result(path, result):
    if path is None:
        return

    with path.open('a', newline = '') as stream:
        writer = csv.DictWriter(stream, fieldnames = fields)
        for strategy, outcome in result['results'].items():
            row = {name:result.get(name, '') for name in ('problem', 'replicate', 'cpu')}
            row.update(strategy = strategy, proved = bool(outcome.get('proved')),
                       elapsed_s = outcome.get('elapsed_s', ''), error = outcome.get('error', ''))
            writer.writerow(row)
