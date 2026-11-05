import csv
import json
from pathlib import Path
import re
from problem_split import ProblemSplit

fields = ['problem', 'part', 'declared_status', 'strategy', 'result', 'time_ms', 'steps',
          'proved', 'clauses', 'score_ms',
          'generated', 'kept', 'error', 'score_error']

def default_output(folder, parts, split):
    label = '-'.join(map(str, sorted(parts)))
    if len(parts) == split and split > 1:
        label = 'all'

    return folder / 'results' / f'part-{label}.csv'

def prepare_output(path):
    path = Path(path)
    directory = path.with_suffix('') if path.suffix.lower() == '.csv' else path
    directory.mkdir(parents = True, exist_ok = True)
    return directory, directory / 'results.csv'

def strategy_path(path, mode, replicate = 0):
    if replicate:
        mode = f'{mode}-repeat{replicate + 1}'

    return path.with_name(f'{path.stem}-{mode}.csv')

def declared_status(path):
    try:
        with Path(path).open() as stream:
            header = stream.read(16000)
    except OSError:
        return ''

    match = re.search(r'%\s*Status\s*:\s*(\w+)', header)
    return match[1] if match else ''

def log_statistics(directory):
    logs = list(directory.glob('*.log'))
    counts = []
    for path in logs:
        latest = {}
        with path.open(errors = 'replace') as stream:
            for line in stream:
                for name, value in re.findall(r'\b(Given|Generated|Kept)=(\d+)', line):
                    latest[name] = int(value)

        counts.append(latest)

    return {
        column:sum(c[name] for c in counts)
        for column, name in [('steps', 'Given'), ('generated', 'Generated'), ('kept', 'Kept')]
        if counts and all(name in c for c in counts)
    }

def result_label(outcome):
    if 'result' in outcome:
        return outcome['result']

    if outcome.get('proved'):
        return 'Proved'
    if outcome.get('error'):
        return 'Timeout' if outcome['error'] == 'Timeout' else 'Error'

    searches = outcome.get('stages', []) + [outcome.get(k) for k in ('baseline_search', 'guided_search')]
    if any(s and s.get('exit') == 4 for s in searches):
        return 'Timeout'

    return 'Unproved'

def append_result(path, result, partition = None):
    if path is None:
        return

    part = ProblemSplit(**partition).part(result['problem']) if partition else result.get('part', '')
    for strategy, outcome in result['results'].items():
        destination = strategy_path(path, strategy, result.get('replicate', 0))
        header = not destination.exists() or destination.stat().st_size == 0
        row = {key:outcome.get(key, '') for key in fields}
        row.update(problem = result['problem'].removesuffix('.p') + '.p', declared_status = result.get('declared_status', ''),
                   result = result_label(outcome), strategy = strategy, part = part,
                   proved = bool(outcome.get('proved')))
        for source, target in [('elapsed_s', 'time_ms'), ('score_s', 'score_ms')]:
            row[target] = round(outcome[source] * 1000, 3) if source in outcome else ''

        with destination.open('a', newline = '') as stream:
            writer = csv.DictWriter(stream, fieldnames = fields)
            if header:
                writer.writeheader()

            writer.writerow(row)
            stream.flush()

def csv_outcome(row):
    if any(row.get(field) is None for field in fields if field != 'part'):
        raise ValueError('Incomplete CSV row')
    if row['result'] not in ('Proved', 'Timeout', 'Error', 'Unproved'):
        raise ValueError('Invalid result')

    outcome = {'proved':row['proved'] == 'True', 'result':row['result']}
    for key in ('error', 'score_error'):
        if row[key]:
            outcome[key] = row[key]

    for source, target in [('time_ms', 'elapsed_s'), ('score_ms', 'score_s')]:
        if row[source]:
            outcome[target] = float(row[source]) / 1000

    for key in ('steps', 'clauses', 'generated', 'kept'):
        if row[key]:
            outcome[key] = int(row[key])

    return outcome

def read_csv_results(directory):
    indexed = {}
    for path in sorted(directory.glob('results-*.csv')):
        match = re.search(r'-repeat(\d+)$', path.stem)
        file_replicate = int(match[1]) - 1 if match else 0
        with path.open(newline = '') as stream:
            for row in csv.DictReader(stream):
                if 'problem' not in row and 'name' in row:
                    row['problem'] = row.pop('name')

                try:
                    outcome = json.loads(row['details']) if row.get('details') else csv_outcome(row)
                    if not isinstance(outcome, dict) or not ('proved' in outcome or 'error' in outcome):
                        continue

                    replicate = int(row.get('replicate', outcome.get('replicate', file_replicate)))
                    key = (row['problem'].removesuffix('.p'), replicate)
                except (ValueError, KeyError, TypeError):
                    continue

                result = indexed.setdefault(key, {'problem':key[0], 'replicate':key[1],
                                                   'declared_status':row['declared_status'], 'part':row.get('part', ''),
                                                   'results':{}, 'mode_cpus':{}})
                result['results'][row['strategy']] = outcome
                result['mode_cpus'][row['strategy']] = row.get('cpu', '')

    return list(indexed.values())
