import contextlib
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(folder / 'experiments'))
sys.path.insert(0, str(folder))
from paired import main
from summary import summarize
from experiment_output import default_output, append_result, prepare_output

paths = [f'/tptp/Problems/ABC/ABC{i:03d}-{v}.p' for i in range(60) for v in (1, 2)]
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    source = root / 'input.json'
    source.write_text(json.dumps({'paths':paths}))
    selections = []
    for part in range(4):
        output = root / str(part)
        argv = ['compare.py', '--manifest', str(source), '--split', '4', '--part', str(part), '--output', str(output)]
        with patch.object(sys, 'argv', argv), patch('paired.sample', return_value = []):
            with patch('paired.ProcessPoolExecutor'), patch('paired.as_completed', return_value = []):
                main()

        manifest = json.loads((output / 'manifest.json').read_text())
        expected = [p for p in paths if int.from_bytes(hashlib.md5(Path(p).stem[:6].encode(), usedforsecurity = False).digest(), 'big') % 4 == part]
        assert manifest['paths'] == expected
        assert manifest['partition'] == {'split':4, 'parts':[part], 'scheme':5}
        selections.extend(manifest['paths'])

    assert sorted(selections) == sorted(paths)
    assert len(selections) == len(set(selections))
    assert summarize(root / '0')['cases'] == 0
    for options in (['--split', '0'], ['--split', '4', '--part', '4'], ['--part', '-1']):
        argv = ['compare.py', '--output', str(root / 'invalid'), *options]
        with patch.object(sys, 'argv', argv), contextlib.redirect_stderr(io.StringIO()):
            try:
                main()
            except SystemExit as error:
                assert error.code == 2
            else:
                raise AssertionError('Invalid partition accepted')

    assert not (root / 'invalid').exists()

    assert default_output(root, [2], 4) == root / 'results/part-2.csv'
    assert default_output(root, [0], 1) == root / 'results/part-0.csv'
    output = root / 'part-2.csv'
    argv = ['compare.py', '--manifest', str(source), '--split', '4', '--part', '2']
    with patch.object(sys, 'argv', argv), patch('paired.sample', return_value = []):
        with patch('paired.default_output', return_value = output), patch('paired.ProcessPoolExecutor'), patch('paired.as_completed', return_value = []):
            main()

    assert output.is_file() and output.with_suffix('').is_dir()
    assert summarize(output)['cases'] == 0
    result = {'problem':'ABC001-1', 'replicate':0, 'cpu':2,
              'results':{'Baseline':{'proved':True, 'elapsed_s':0.1},
                         'Other':{'error':'comma, newline\nerror'}}}
    append_result(output, result)
    with output.open(newline = '') as stream:
        rows = list(csv.DictReader(stream))

    assert rows[0]['proved'] == 'True' and rows[0]['elapsed_s'] == '0.1'
    assert rows[1]['error'] == 'comma, newline\nerror'
    original = output.read_bytes()
    prepare_output(output)
    assert output.read_bytes() == original

print('Partition CLI matches Connections scheme 5; parts are disjoint and exhaustive; invalid parts and empty summaries handled. No searches launched.')
