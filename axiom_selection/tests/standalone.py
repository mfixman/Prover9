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

    for name in ('experiments', 'connections_vendor'):
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
    output = adapter / 'results/part-0'
    files = sorted(output.glob('results-*.csv'))
    assert len(files) == 3
    assert {p.name for p in output.iterdir()} == {p.name for p in files} | {'manifest.json', '.lock'}
    rows = []
    for path in files:
        with path.open(newline = '') as stream:
            rows.extend(csv.DictReader(stream))

    assert len(rows) == 6 and all(not row['error'] for row in rows), rows
    assert all(row['proved'] == str(row['problem'] == 'GRP001-1.p') for row in rows)
    assert all(float(row['time_ms']) > 0 for row in rows)
    assert all('details' not in row for row in rows)
    scored = [r for r in rows if r['problem'] == 'GRP002-1.p' and r['strategy'] == 'WeightedSupport16']
    assert float(scored[0]['score_ms']) > 0
    original = {p:p.read_bytes() for p in files}
    subprocess.run(command, cwd = root, env = env, check = True, timeout = 90)
    assert all(p.read_bytes() == data for p, data in original.items())

    partial = output / 'results-WeightedSupport16.csv'
    with partial.open('w', newline = '') as stream:
        writer = csv.DictWriter(stream, fieldnames = list(rows[0]))
        writer.writeheader()
        writer.writerows(r for r in rows if r['strategy'] == 'WeightedSupport16' and r['problem'] == 'GRP001-1.p')
        stream.write('truncated,row')

    subprocess.run(command, cwd = root, env = env, check = True, timeout = 90)
    assert all(p.read_bytes() == data for p, data in original.items() if p != partial)
    with partial.open(newline = '') as stream:
        resumed_rows = list(csv.DictReader(stream))

    assert len(resumed_rows) == 2 and all(not row['error'] for row in resumed_rows)
    rejected = subprocess.run(command + ['--seconds', '4'], cwd = root, env = env, capture_output = True, text = True)
    assert rejected.returncode != 0 and 'changed seconds' in rejected.stderr
    subprocess.run([sys.executable, str(adapter / 'experiments/summary.py'), str(output)], cwd = root, env = env, check = True, capture_output = True)

print('Standalone strategies, no-op resume, partial/corrupt checkpoint recovery, CSV deduplication and configuration checks passed with external imports forbidden.')
