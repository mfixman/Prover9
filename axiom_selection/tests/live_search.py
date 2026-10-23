from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_search import LiveSearch

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    fake = root / 'fake-prover'
    fake.write_text('#!/usr/bin/python3\nimport time\ntime.sleep(0.2)\nprint("============================== end of proof", flush=True)\n')
    fake.chmod(0o755)
    live = LiveSearch(['p'], 2, root / 'resume', fake)
    live.pause()
    time.sleep(.3)
    assert live.wait(0) is None
    live.resume()
    assert live.wait(1)['proved']
    live.close()

    live = LiveSearch(['p'], .15, root / 'timeout', fake)
    live.pause()
    result = live.wait(1)
    assert result is not None and not result['proved']
    live.close()

print('Paused search resumes; a paused child is killed at its wall deadline.')
