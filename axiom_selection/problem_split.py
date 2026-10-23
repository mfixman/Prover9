import hashlib
from pathlib import Path
import re

class ProblemSplit:
    def __init__(self, split = 1, parts = None, scheme = 5):
        if split < 1:
            raise ValueError('--split must be at least 1')
        self.split = split
        self.parts = list(range(split)) if parts is None else list(parts)
        self.scheme = scheme
        if scheme not in (4, 5):
            raise ValueError('Supported split schemes are 4 and 5')
        if not self.parts or any(p < 0 or p >= split for p in self.parts):
            raise ValueError(f'--part must be between 0 and {split - 1}')
        if len(set(self.parts)) != len(self.parts):
            raise ValueError('--part must not repeat a part')

    def part(self, problem):
        name = Path(problem).stem
        match = re.match(r'[A-Z]{3}\d{3}', name)
        key = match.group() if match else name.split('__', 1)[0]
        if self.scheme == 5:
            digest = hashlib.md5(key.encode('utf-8'), usedforsecurity = False).digest()
        else:
            digest = hashlib.blake2b(f'{self.split}\0{key}'.encode('utf-8'), digest_size = 8, person = b'lcsplit').digest()

        return int.from_bytes(digest, 'big') % self.split

    def contains(self, problem):
        return len(self.parts) == self.split or self.part(problem) in self.parts

    def select(self, paths):
        return [path for path in paths if self.contains(path)]

    def to_dict(self):
        return {'split':self.split, 'parts':self.parts, 'scheme':self.scheme}
