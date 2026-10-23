import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

folder = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    checkout = root / 'Prover9'
    adapter = checkout / 'axiom_selection'
    adapter.mkdir(parents = True)
    for path in folder.glob('*.py'):
        shutil.copy2(path, adapter / path.name)

    for name in ('experiments', 'torok_vendor'):
        shutil.copytree(folder / name, adapter / name, ignore = shutil.ignore_patterns('__pycache__'))

    for name in ('models/torok.ts', 'build/native-search', 'build/native-search-control', 'native_search.c'):
        destination = adapter / name
        destination.parent.mkdir(parents = True, exist_ok = True)
        shutil.copy2(folder / name, destination)

    (checkout / 'provers.src').mkdir()
    shutil.copy2(folder.parent / 'provers.src/prover9', checkout / 'provers.src/prover9')
    tptp = root / 'dataset'
    problems = tptp / 'Problems/GRP'
    problems.mkdir(parents = True)
    (problems / 'GRP001-1.p').write_text('cnf(a,axiom,p). cnf(b,negated_conjecture,~p).')
    (problems / 'GRP002-1.p').write_text('\n'.join(f'cnf(a{i},axiom,p{i}).' for i in range(20)))
    manifest = root / 'input.json'
    manifest.write_text(json.dumps({'paths':[str(p) for p in sorted(problems.glob('*.p'))]}))

    blocker = root / 'sitecustomize.py'
    blocker.write_text("import importlib.abc, sys\nclass Block(importlib.abc.MetaPathFinder):\n def find_spec(self, fullname, path=None, target=None):\n  if fullname.split('.')[0] in ('connections','axiom_prediction'):\n   raise ImportError('External import forbidden: '+fullname)\nsys.meta_path.insert(0,Block())\n")
    env = dict(os.environ, PYTHONPATH = str(root), CONNECTIONS_ROOT = str(root / 'absent'))
    env.update(OMP_NUM_THREADS = '1', OPENBLAS_NUM_THREADS = '1', MKL_NUM_THREADS = '1')
    command = [sys.executable, str(adapter / 'compare.py'), '--manifest', str(manifest), '--tptp', str(tptp),
               '--seconds', '3', '--workers', '1', '--modes', 'Baseline', 'ResumeSupport1', 'WeightedSupport16']
    subprocess.run(command, cwd = root, env = env, check = True, timeout = 90)
    output = adapter / 'results/part-0.csv'
    with output.open(newline = '') as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 6 and all(not row['error'] for row in rows), rows
    assert all(row['proved'] == str(row['problem'] == 'GRP001-1') for row in rows)
    results = json.loads(output.with_suffix('').joinpath('results.json').read_text())
    unproved = next(row for row in results if row['problem'] == 'GRP002-1')['results']
    assert 'guided_search' in unproved['ResumeSupport1']
    assert unproved['WeightedSupport16']['scored']
    completed = output.with_suffix('') / 'GRP001-1/Baseline/result.json'
    original_time = completed.stat().st_mtime_ns
    original_csv = output.read_bytes()
    subprocess.run(command, cwd = root, env = env, check = True, timeout = 90)
    assert completed.stat().st_mtime_ns == original_time
    assert output.read_bytes() == original_csv

    partial = output.with_suffix('') / 'GRP002-1'
    (partial / 'results.json').unlink()
    (partial / 'WeightedSupport16/result.json').write_text('{interrupted')
    output.with_suffix('').joinpath('results.json').write_text('{interrupted')
    subprocess.run(command, cwd = root, env = env, check = True, timeout = 90)
    assert completed.stat().st_mtime_ns == original_time
    assert list(partial.glob('WeightedSupport16.interrupted-*'))
    with output.open(newline = '') as stream:
        resumed_rows = list(csv.DictReader(stream))

    assert len(resumed_rows) == 6 and all(not row['error'] for row in resumed_rows)
    rejected = subprocess.run(command + ['--seconds', '4'], cwd = root, env = env, capture_output = True, text = True)
    assert rejected.returncode != 0 and 'changed seconds' in rejected.stderr
    subprocess.run([sys.executable, str(adapter / 'experiments/summary.py'), str(output)], cwd = root, env = env, check = True, capture_output = True)

print('Standalone strategies, no-op resume, partial/corrupt checkpoint recovery, CSV deduplication and configuration checks passed with external imports forbidden.')
