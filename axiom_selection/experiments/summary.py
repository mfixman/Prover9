import argparse
import json
from pathlib import Path
import statistics

def summarize(directory):
    if directory.suffix.lower() == '.csv':
        directory = directory.with_suffix('')

    rows = json.loads((directory / 'results.json').read_text())
    manifest = json.loads((directory / 'manifest.json').read_text())
    limit = manifest['seconds']
    invalid = [r for r in rows if all('Unsupported symbol' in x.get('error', '') for x in r['results'].values())]
    rows = [r for r in rows if r not in invalid]
    if not rows:
        return {'cases':0, 'unsupported':[r['problem'] for r in invalid], 'modes':{}}

    modes = list(rows[0]['results'])
    key = lambda r:(r['problem'], r.get('replicate', 0))
    base = {key(r) for r in rows if r['results']['Baseline'].get('proved')}
    reference = {key(r) for r in rows if r['results'].get('Support16', {}).get('proved')}
    result = {'cases':len(rows), 'unsupported':[r['problem'] for r in invalid], 'modes':{}}

    for mode in modes:
        solved = {key(r) for r in rows if r['results'][mode].get('proved')}
        common = [r for r in rows if key(r) in base & solved]
        durations = [r['results'][mode]['elapsed_s'] if r['results'][mode].get('proved') else 2 * limit for r in rows]
        info = {'proofs':len(solved), 'par2_s':statistics.mean(durations),
                'gains':[k[0] for k in sorted(solved-base)], 'losses':[k[0] for k in sorted(base-solved)],
                'common_s':sum(r['results'][mode]['elapsed_s'] for r in common),
                'common_baseline_s':sum(r['results']['Baseline']['elapsed_s'] for r in common)}
        if 'Support16' in modes:
            info.update(gains_over_support16 = [k[0] for k in sorted(solved-reference)], losses_to_support16 = [k[0] for k in sorted(reference-solved)])

        info['guided_searches'] = sum(bool(r['results'][mode].get('guided_search')) or any(s['name']=='selected' for s in r['results'][mode].get('stages', [])) for r in rows)
        result['modes'][mode] = info

    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type = Path)
    args = parser.parse_args()
    if args.directory.suffix.lower() == '.csv':
        args.directory = args.directory.with_suffix('')

    result = summarize(args.directory)
    (args.directory / 'summary.json').write_text(json.dumps(result, indent = 2))
    print(json.dumps(result, indent = 2))
