import csv
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(folder))
from experiment_output import append_result, log_statistics, read_csv_results

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    source = root / 'ABC001-1.p'
    source.write_text('% Status : Unsatisfiable\ncnf(a,axiom,p).')
    legacy = root / 'legacy'
    stage = legacy / 'ABC001-1/Baseline'
    stage.mkdir(parents = True)
    (stage / 'baseline.log').write_text('Given=2. Generated=4. Kept=3.\nGiven=5. Generated=9. Kept=6.\n')
    assert log_statistics(stage) == {'steps':5, 'generated':9, 'kept':6}
    (stage / 'selected.log').write_text('incomplete search')
    assert log_statistics(stage) == {}
    (stage / 'selected.log').unlink()

    outcome = {'proved':False, 'error':'comma, newline\nerror', 'elapsed_s':0.25}
    (stage / 'result.json').write_text(json.dumps(outcome))
    manifest = {'paths':[str(source)], 'modes':['Baseline'], 'seconds':1, 'model_sha256':'fixture', 'partition':{'split':10, 'parts':list(range(10)), 'scheme':5}}
    (legacy / 'manifest.json').write_text(json.dumps(manifest))
    compact = root / 'compact'
    command = [sys.executable, str(folder / 'export_results.py'), str(legacy), '--output', str(compact)]
    subprocess.run(command, check = True)
    assert [p.name for p in compact.iterdir()] == ['results-Baseline.csv']
    with (compact / 'results-Baseline.csv').open(newline = '') as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 1
    row = rows[0]
    assert row['declared_status'] == 'Unsatisfiable' and row['result'] == 'Error'
    assert row['steps'] == '5' and float(row['time_ms']) == 250
    assert row['error'] == outcome['error']
    assert row['problem'] == 'ABC001-1.p'
    expected_part = int.from_bytes(hashlib.md5(b'ABC001', usedforsecurity = False).digest(), 'big') % 10
    assert int(row['part']) == expected_part
    assert not {'metadata', 'budget_s', 'elapsed_s', 'cpu', 'replicate', 'details'} & row.keys()
    assert read_csv_results(compact)[0]['results']['Baseline']['error'] == outcome['error']
    recovered = read_csv_results(compact)[0]
    assert recovered['problem'] == 'ABC001-1' and recovered['replicate'] == 0
    assert int(recovered['part']) == expected_part
    repeated = {**recovered, 'replicate':1}
    append_result(compact / 'results.csv', repeated)
    assert {r['replicate'] for r in read_csv_results(compact)} == {0, 1}
    assert (compact / 'results-Baseline-repeat2.csv').exists()
    from experiment_resume import rebuild_csv
    rebuild_csv(compact / 'results.csv', read_csv_results(compact))
    assert {r['replicate'] for r in read_csv_results(compact)} == {0, 1}
    assert all(int(r['part']) == expected_part for r in read_csv_results(compact))
    assert (stage / 'result.json').exists()
    retry = subprocess.run(command, capture_output = True)
    assert retry.returncode != 0

print('Legacy export, statistics completeness, CSV escaping, schema and overwrite protection passed.')
