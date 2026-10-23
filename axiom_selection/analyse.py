import argparse
import json
import math
from pathlib import Path
import statistics

bad_outcomes = {'InputOrModelError', 'ProverError', 'DriverError'}

def summarize(groups, mode, seed, limit):
    paired = []
    for group in groups:
        baseline = next(r for r in group['results'] if r['mode'] == 'Baseline')
        guided = next(r for r in group['results'] if r['mode'] == mode and r['seed'] == seed)
        paired.append((group['problem'], baseline, guided))

    gains = [name for name, base, run in paired if base['outcome'] != 'Proved' and run['outcome'] == 'Proved']
    losses = [name for name, base, run in paired if base['outcome'] == 'Proved' and run['outcome'] != 'Proved']
    successes = [run for _, _, run in paired if run['outcome'] == 'Proved']
    common = [(base, run) for _, base, run in paired if base['outcome'] == run['outcome'] == 'Proved']
    ratios = [run['end_to_end_s'] / base['end_to_end_s'] for base, run in common]

    return {'mode': mode, 'seed': seed, 'proved': len(successes), 'total': len(paired), 'gains': gains, 'losses': losses, 'par2_mean_s': statistics.mean(run['end_to_end_s'] if run['outcome'] == 'Proved' else 2 * limit for _, _, run in paired), 'median_solved_s': statistics.median(run['end_to_end_s'] for run in successes) if successes else None, 'common_solved': len(common), 'median_common_time_ratio_vs_baseline': statistics.median(ratios) if ratios else None, 'geomean_common_time_ratio_vs_baseline': math.exp(statistics.mean(map(math.log, ratios))) if ratios else None, 'solved_by_s': {str(t): sum(run['end_to_end_s'] <= t for run in successes) for t in [1, 5, 10, limit]}}

def robust_changes(groups):
    gains, losses, speedups = [], [], []
    for group in groups:
        base = next(r for r in group['results'] if r['mode'] == 'Baseline')
        runs = [r for r in group['results'] if r['mode'] == 'Torok']
        both_proved = all(r['outcome'] == 'Proved' for r in runs)
        if base['outcome'] != 'Proved' and both_proved:
            gains.append(group['problem'])
        elif base['outcome'] == 'Proved' and all(r['outcome'] != 'Proved' for r in runs):
            losses.append(group['problem'])

        if base['outcome'] == 'Proved' and both_proved and base['end_to_end_s'] > 1:
            guided = statistics.mean(r['end_to_end_s'] for r in runs)
            if guided < base['end_to_end_s']:
                speedups.append({'problem': group['problem'], 'baseline_s': base['end_to_end_s'], 'torok_mean_s': guided, 'speedup': base['end_to_end_s'] / guided})

    return {'gains_both_torok_seeds': gains, 'losses_both_torok_seeds': losses, 'faster_common_proofs_baseline_over_1s': speedups}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type = Path)
    args = parser.parse_args()
    groups = json.loads((args.directory / 'results.json').read_text())
    metadata = json.loads((args.directory / 'manifest.json').read_text())
    errors = [g for g in groups if any(r['outcome'] in bad_outcomes for r in g['results'])]
    excluded = [g for g in groups if all(r['outcome'] == 'InputOrModelError' for r in g['results'])]
    valid = [g for g in groups if g not in excluded]

    configs = [('Baseline', 1), ('Torok', 1), ('Torok', 2), ('Uniform', 1), ('Uniform', 2)]
    summaries = [summarize(valid, mode, seed, metadata['seconds_per_arm_including_startup']) for mode, seed in configs]
    report = {'attempted_problems': len(groups), 'valid_matched_problems': len(valid), 'excluded_common_input_errors': [g['problem'] for g in excluded], 'input_or_runtime_errors': errors, 'elapsed_s': metadata.get('elapsed_s'), 'configurations': summaries, **robust_changes(valid)}
    (args.directory / 'summary.json').write_text(json.dumps(report, indent = 2))
    print(json.dumps(report, indent = 2))

if __name__ == '__main__':
    main()
