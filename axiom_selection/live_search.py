import json
import os
from pathlib import Path
import select
import signal
import subprocess
from portfolio import native_input

class LiveSearch:
    def __init__(self, clauses, seconds, output, binary = None):
        self.result = None
        self.child_fd = None
        output = Path(output)
        root = Path(__file__).resolve().parent
        source = output.with_suffix('.in')
        source.write_text(native_input(clauses, list(range(len(clauses))), seconds))

        command = [str(root / 'build/native-search-control'), str(binary or root.parent / 'provers.src/prover9'),
                   str(source), str(output.with_suffix('.log')), str(seconds), '--pid']
        self.process = subprocess.Popen(command, stdout = subprocess.PIPE, text = True)
        self.process_fd = os.pidfd_open(self.process.pid)
        pid = json.loads(self.process.stdout.readline())['pid']
        try:
            self.child_fd = os.pidfd_open(pid)
        except ProcessLookupError:
            pass

    def send(self, sig):
        if self.child_fd is not None:
            try:
                signal.pidfd_send_signal(self.child_fd, sig)
            except ProcessLookupError:
                pass

    def wait(self, seconds):
        if self.result is not None:
            return self.result
        ready, _, _ = select.select([self.process_fd], [], [], max(0, seconds))
        if not ready:
            return None

        self.process.wait()
        self.result = json.loads(self.process.stdout.read())
        return self.result

    def pause(self):
        self.send(signal.SIGSTOP)

    def resume(self):
        self.send(signal.SIGCONT)

    def close(self):
        if self.result is None:
            self.send(signal.SIGKILL)
            self.wait(1)
        if self.child_fd is not None:
            os.close(self.child_fd)
            self.child_fd = None
        if self.process_fd is not None:
            os.close(self.process_fd)
            self.process_fd = None

        return self.result
