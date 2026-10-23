import argparse
import itertools
import json
from pathlib import Path


def simulate(row, modes, seconds, budget = 20, probe = 1):
    results = row['results']
    baseline = results['Full']
    if baseline['proved'] and baseline['charged_s'] <= probe + row['parse_s']:
        return True, baseline['charged_s']

    charged = row['parse_s'] + probe + row['score_s']
    for mode, limit in zip(modes, seconds):
        result = results[mode]
        duration = min(limit, budget - charged)
        if duration <= 0:
            break

        search = result['stages'][0] if result['stages'] else {}
        measured = search.get('search_s', 1000)
        if result['proved'] and measured <= duration:
            return True, charged + measured

        charged += min(measured, duration)

    return False, charged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type = Path)
    args = parser.parse_args()
    rows = json.loads((args.directory / 'results.json').read_text())
    rows = [r for r in rows if 'results' in r]
    base = {r['problem'] for r in rows if r['results']['Full']['proved']}
    print('Cases', len(rows), 'baseline', len(base))
    modes = [m for m in rows[0]['results'] if m != 'Full']
    for mode in modes:
        solved = {r['problem'] for r in rows if r['results'][mode]['proved']}
        print(mode, len(solved), 'gains', sorted(solved - base), 'losses', sorted(base - solved))

    scores = []
    for length in (1, 2, 3):
        for choices in itertools.permutations(modes, length):
            limits = [8] * length
            results = [simulate(r, choices, limits) for r in rows]
            solved = {r['problem'] for r, (ok, _) in zip(rows, results) if ok}
            par2 = sum(t if ok else 40 for ok, t in results) / len(rows)
            scores.append((len(solved), -par2, choices, sorted(solved - base), sorted(base - solved)))

    for score in sorted(scores, reverse = True)[:15]:
        print('Portfolio', score)

if __name__ == '__main__':
    main()
