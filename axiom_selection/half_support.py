from pathlib import Path
import time
from bounded import bounded
from live_search import LiveSearch
from portfolio import search
from problem import load_problem, clause_text

def solve_half(path, tptp, predictor, budget, output, support_size = 1, resume = False):
    started = time.monotonic()
    output = Path(output)
    matrix = load_problem(path, tptp)
    clauses = [clause_text(c) for c in matrix.clauses]
    remaining = lambda: max(.001, budget - (time.monotonic() - started))
    baseline = LiveSearch(clauses, remaining(), output / 'baseline')
    result = {'proved':False, 'clauses':len(clauses), 'support_size':support_size}

    def fallback():
        baseline.resume()
        found = baseline.wait(remaining())
        result['proved'] = bool(found and found['proved'])
        return result

    try:
        initial = min(1, budget / 2) if resume else budget / 2
        found = baseline.wait(max(0, initial - (time.monotonic() - started)))
        if found and found['proved']:
            result['proved'] = True
            return result

        baseline.pause()
        found = baseline.wait(.002)
        if found and found['proved']:
            result['proved'] = True
            return result

        def score():
            weights, info = predictor.predict(matrix)
            return {'weights':weights, **info}

        scoring = time.monotonic()
        prediction = bounded(score, min(budget / 4, remaining()), output / 'prediction.json')
        result['score_s'] = time.monotonic() - scoring
        found = baseline.wait(0)
        if found and found['proved']:
            result['proved'] = True
            return result

        if 'error' in prediction:
            result['score_error'] = prediction['error']
            return fallback()

        conjectures = set(matrix.conjecture_clauses)
        indices = list(range(len(clauses)))
        ranked = sorted((i for i in indices if i not in conjectures), key = lambda i:(-prediction['weights'][i], i))
        selected = conjectures | set(ranked[:support_size])
        usable = [i for i in indices if i not in selected]
        seconds = min(budget / 3, remaining()) if resume else remaining()
        guided = search(clauses, sorted(selected), seconds, output / 'selected', usable = usable)
        result['guided_search'] = guided
        if guided['proved']:
            result['proved'] = True
            return result

        return fallback()
    finally:
        result['baseline_search'] = baseline.close()
        if result['baseline_search'] and result['baseline_search']['proved']:
            result['proved'] = True
        result['elapsed_s'] = time.monotonic() - started
