"""Consolidate a legacy comparison run without modifying its original files."""
import argparse
import json
from pathlib import Path
from experiment_output import append_result, declared_status, log_statistics
from experiment_resume import recover, case_directory

def main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument('run', type = Path)
    parser.add_argument('--tptp', type = Path, help = 'Relocated TPTP root for reading declared statuses.')
    parser.add_argument('--output', type = Path, required = True)
    args = parser.parse_args()
    manifest = json.loads((args.run / 'manifest.json').read_text())
    args.output.mkdir(parents = True, exist_ok = True)
    if list(args.output.glob('results-*.csv')):
        parser.error('Output already contains result CSVs; choose an empty directory.')

    complete, pending = recover(args.run, manifest['paths'], manifest['modes'], manifest.get('repeats', 1))
    paths = {Path(p).stem:p for p in manifest['paths']}
    results = complete + [previous for _, _, previous in pending]
    for result in results:
        source = Path(paths[result['problem']])
        if args.tptp:
            source = args.tptp / 'Problems' / source.parent.name / source.name

        result['declared_status'] = declared_status(source)
        target = case_directory(args.run, paths[result['problem']], result.get('replicate', 0))
        for mode, outcome in result['results'].items():
            outcome.update(log_statistics(target / mode))

        append_result(args.output / 'results.csv', result, manifest.get('partition'))

    print(f'Exported {len(results)} problem groups to {args.output}; originals retained.')

if __name__ == '__main__':
    main()
