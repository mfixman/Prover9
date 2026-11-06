import json
import os
from pathlib import Path
import select
import signal
import subprocess
from portfolio import native_input

def pidfd(pid):
    try:
        return os.pidfd_open(pid)
    except OSError as error:
        if isinstance(error, ProcessLookupError) or error.errno != 38:
            raise

        return None

class LiveSearch:
    def __init__(self, clauses, seconds, output, binary = None):
        self.result = None
        self.child_fd = None
        self.child_pid = None
        output = Path(output)
        root = Path(__file__).resolve().parent
        source = output.with_suffix('.in')
        source.write_text(native_input(clauses, list(range(len(clauses))), seconds))

        command = [str(root / 'build/native-search-control'), str(binary or root.parent / 'provers.src/prover9'),
                   str(source), str(output.with_suffix('.log')), str(seconds), '--pid']
        self.process = subprocess.Popen(command, stdout = subprocess.PIPE, text = True)
        # Kernels before Linux 5.3, such as the HPC's, lack pidfds; fall back to process ids.
        self.process_fd = pidfd(self.process.pid)
        pid = json.loads(self.process.stdout.readline())['pid']
        try:
            self.child_fd = pidfd(pid)
        except ProcessLookupError:
            pass

        if self.child_fd is None:
            self.child_pid = pid

    def send(self, sig):
        try:
            if self.child_fd is not None:
                signal.pidfd_send_signal(self.child_fd, sig)
            elif self.child_pid is not None and self.process.poll() is None:
                os.kill(self.child_pid, sig)
        except ProcessLookupError:
            pass

    def wait(self, seconds):
        if self.result is not None:
            return self.result
        if self.process_fd is None:
            try:
                self.process.wait(timeout = max(0, seconds))
            except subprocess.TimeoutExpired:
                return None
        else:
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
