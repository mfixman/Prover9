import json
import os
from pathlib import Path
import signal
import time

def bounded(function, seconds, output, process_group = False):
    output = Path(output)
    started = time.monotonic()
    pid = os.fork()
    if pid == 0:
        if process_group:
            os.setsid()

        try:
            result = function()
        except Exception as error:
            result = {'error': repr(error)}

        output.write_text(json.dumps(result, indent = 2))
        os._exit(0)

    while time.monotonic() - started < seconds:
        finished, status = os.waitpid(pid, os.WNOHANG)
        if finished:
            if output.exists():
                return json.loads(output.read_text())

            return {'error': f'Child exit {status}'}

        time.sleep(0.002)

    try:
        if process_group:
            os.killpg(pid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    os.waitpid(pid, 0)
    result = {'error': 'Timeout', 'elapsed_s': time.monotonic() - started}
    output.write_text(json.dumps(result, indent = 2))
    return result
