import argparse
import json
from pathlib import Path
import statistics

def summarize(directory):
    rows = json.loads((directory / 'results.json').read_text())
    modes = list(rows[0]['results'])
    budget = json.loads((directory / 'manifest.json').read_text())['seconds']
    invalid = [r for r in rows if all('Unsupported symbol' in v.get('error', '') for v in r['results'].values())]
    rows = [r for r in rows if r not in invalid]
    baseline = {r['problem'] for r in rows if r['results']['Baseline'].get('proved', False)}
    print('Cases', len(rows), 'common unsupported inputs', [r['problem'] for r in invalid])
    for mode in modes:
        solved = {r['problem'] for r in rows if r['results'][mode].get('proved', False)}
        par2 = statistics.mean(r['results'][mode]['elapsed_s'] if r['results'][mode].get('proved') else 2 * budget for r in rows)
        common = [r for r in rows if r['problem'] in baseline & solved]
        base_time = sum(r['results']['Baseline']['elapsed_s'] for r in common)
        mode_time = sum(r['results'][mode]['elapsed_s'] for r in common)
        print(mode, 'solved',len(solved), 'PAR2',round(par2,3), 'common sum',round(mode_time,3), 'baseline sum',round(base_time,3))
        print(' gains',sorted(solved-baseline),'losses', sorted(baseline-solved))
        selected = [r for r in rows if any(s['name']=='selected' for s in r['results'][mode].get('stages', []))]
        print(' selected search',len(selected),'selected proofs',sum(r['results'][mode].get('proved',False) for r in selected))

    for r in rows:
        b, t = r['results']['Baseline'], r['results'].get('TorokSupport', r['results'].get('Torok', {}))
        if b.get('proved') and t.get('proved') and b['elapsed_s']>1 and b['elapsed_s']/t['elapsed_s']>1.2:
            print('speedup', r['problem'], round(b['elapsed_s'],3), round(t['elapsed_s'],3))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type = Path)
    summarize(parser.parse_args().directory)
