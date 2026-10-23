from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portfolio import search

with tempfile.TemporaryDirectory() as directory:
    output = Path(directory)
    proof = search(['p', '-p', '-q'], [0, 1, 2], 2, output / 'multiple')
    assert proof['proved']
    assert 'end of proof' in (output / 'multiple.log').read_text()
    consistent = search(['p', '-q'], [0, 1], 2, output / 'consistent')
    assert not consistent['proved']
    support = search(['p', '-p', 'q'], [1], 2, output / 'support', usable = [0, 2])
    assert support['proved']

print('First-refutation stopping, consistent input, and usable/SOS split passed.')
