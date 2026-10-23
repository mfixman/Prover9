import os
import sys
from pathlib import Path

def connections_root(path = None):
    root = Path(path or os.environ.get('CONNECTIONS_ROOT', '~/TP/connections')).expanduser().resolve()
    sys.path[:0] = [str(root / 'src'), str(root / 'packages')]
    return root
