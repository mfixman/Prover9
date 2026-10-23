import dataclasses
import hashlib
import importlib.abc
import json
from pathlib import Path
import sys
import tempfile

folder = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(folder))

class BlockExternal(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path = None, target = None):
        if fullname.split('.')[0] in ('connections', 'axiom_prediction'):
            raise ImportError(f'External checkout import forbidden: {fullname}')

def check_preprocessing():
    blocker = BlockExternal()
    sys.meta_path.insert(0, blocker)
    try:
        check_fixtures()
    finally:
        sys.meta_path.remove(blocker)

def check_fixtures():
    from predict import Predictor
    from problem import load_problem, clause_text
    from torok_vendor.axiom_prediction.graph import build_axiom_graph

    predictor = Predictor()
    cases = json.loads((folder / 'tests/fixtures/preprocessing.json').read_text())
    for case in cases:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, source in case['files'].items():
                (root / name).write_text(source)

            matrix = load_problem(root / 'case.p', root)
            conjectures = list(matrix.conjecture_clauses)
            axioms = [i for i in range(len(matrix.clauses)) if i not in conjectures]
            graph = build_axiom_graph(matrix, axiom_clause_ids = axioms, conjecture_clause_ids = conjectures).graph
            fingerprint = hashlib.sha256(json.dumps(dataclasses.asdict(graph), sort_keys = True).encode()).hexdigest()
            assert fingerprint == case['graph_sha256'], case['name']
            assert [clause_text(c) for c in matrix.clauses] == case['clauses']
            assert conjectures == case['conjectures']
            weights, _ = predictor.predict(matrix)
            assert len(weights) == len(case['weights'])
            assert all(abs(a - b) < 1e-6 for a, b in zip(weights, case['weights'])), case['name']

    assert not any(name.split('.')[0] in ('connections', 'axiom_prediction') for name in sys.modules)
    print('Bundled parsing, graph fingerprints and Torok probabilities match original fixtures; external imports blocked.')

if __name__ == '__main__':
    check_preprocessing()
