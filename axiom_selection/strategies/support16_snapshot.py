from enum import StrEnum
from pathlib import Path
import time
from bounded import bounded
from portfolio import search
from problem import load_problem, clause_text

class Mode(StrEnum):
    TorokSupport = 'TorokSupport'
    RandomSupport = 'RandomSupport'
    Baseline = 'Baseline'
    Torok = 'Torok'
    TorokDirect = 'TorokDirect'
    Random = 'Random'

def solve(path, tptp, predictor, mode, budget, output, threshold = 0.01, probe = 1, minimum = 64):
    started = time.monotonic()
    output = Path(output)
    matrix = load_problem(path, tptp)
    clauses = [clause_text(c) for c in matrix.clauses]
    indices = list(range(len(clauses)))
    stages = []

    def attempt(selected, seconds, name, usable = ()):
        remaining = budget - (time.monotonic() - started)
        if remaining <= 0:
            return False

        result = search(clauses, selected, min(seconds, remaining), output / name, usable = usable)
        stages.append({'name': name, **result})
        return result['proved']

    def finish(proved, **extra):
        return {'proved': proved, 'elapsed_s': time.monotonic() - started,
                'stages': stages, 'clauses': len(clauses), **extra}

    conjectures = set(matrix.conjecture_clauses)
    candidates = [i for i in indices if i not in conjectures]
    if mode == Mode.Baseline or len(candidates) <= minimum:
        return finish(attempt(indices, budget, 'baseline'))
    if mode != Mode.TorokDirect and probe > 0 and attempt(indices, probe, 'probe'):
        return finish(True, scored = False)

    if mode == Mode.RandomSupport:
        import random
        chosen = random.Random(1).sample(candidates, min(minimum, len(candidates)))
        selected = sorted(conjectures | set(chosen))
        selected_set = set(selected)
        usable = [i for i in indices if i not in selected_set]
        proved = attempt(selected, budget, 'selected', usable)
        if not proved and time.monotonic() - started < budget:
            proved = attempt(indices, budget, 'fallback')

        return finish(proved, scored = False)

    def score():
        weights, info = predictor.predict(matrix)
        return {'weights': weights, **info}

    score_started = time.monotonic()
    remaining = budget - (time.monotonic() - started)
    prediction = bounded(score, min(5, max(0.001, remaining)), output / 'prediction.json')
    score_s = time.monotonic() - score_started
    if 'error' in prediction:
        return finish(attempt(indices, budget, 'fallback'), score_error = prediction['error'], score_s = score_s)

    weights = prediction['weights']
    ranked = sorted(candidates, key = lambda i: (-weights[i], i))
    required = conjectures | set(ranked[:minimum])
    selected = [i for i, p in enumerate(weights) if i in required or p >= threshold]
    support = mode in (Mode.TorokSupport, Mode.RandomSupport)
    if support:
        selected = sorted(required)
    if mode in (Mode.Random, Mode.RandomSupport):
        import random
        candidates = [i for i in indices if i not in conjectures]
        chosen = random.Random(1).sample(candidates, len(selected) - len(conjectures))
        selected = sorted(conjectures | set(chosen))

    usable = [i for i in indices if i not in set(selected)] if support else []
    proved = attempt(selected, budget, 'selected', usable)
    if not proved and time.monotonic() - started < budget:
        proved = attempt(indices, budget, 'fallback')

    return finish(proved, scored = True, score_s = score_s, threshold = threshold)
