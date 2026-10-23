import json
import os
from pathlib import Path
import signal
import time

def prepare(path, tptp, predictor):
    from problem import load_problem, clause_text

    started = time.monotonic()
    matrix = load_problem(path, tptp)
    data = {'clauses': [clause_text(c) for c in matrix.clauses],
            'conjectures': list(matrix.conjecture_clauses), 'parse_s': time.monotonic() - started}
    scored = time.monotonic()
    weights, info = predictor.predict(matrix)
    info['clause_count'] = info.pop('clauses')
    data.update(weights = weights, score_s = time.monotonic() - scored, **info)
    return data

def prepare_bounded(path, tptp, predictor, output, seconds = 5):
    output = Path(output)
    started = time.monotonic()
    pid = os.fork()
    if pid == 0:
        try:
            output.write_text(json.dumps(prepare(path, tptp, predictor)))
        except Exception as error:
            output.write_text(json.dumps({'error': repr(error)}))
        finally:
            os._exit(0)

    while time.monotonic() - started < seconds:
        finished, status = os.waitpid(pid, os.WNOHANG)
        if finished:
            if output.exists():
                return json.loads(output.read_text())
            return {'error': f'Preparation process exited: {status}'}
        time.sleep(0.01)

    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)
    result = {'error': 'PreparationTimeout', 'elapsed_s': time.monotonic() - started}
    output.write_text(json.dumps(result))
    return result
