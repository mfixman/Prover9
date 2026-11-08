from enum import StrEnum
import os
from pathlib import Path
import time
from bounded import bounded
from live_search import LiveSearch
from portfolio import search
from problem import load_problem, clause_text

class Ranking(StrEnum):
    Learned = 'Learned'
    Overlap = 'Overlap'

second_predictor = None

# The second ladder ranking comes from an untrained symbol-overlap scorer unless TOROK_SECOND_MODEL overrides it.
def second_scorer():
    global second_predictor
    if second_predictor is None:
        from predict import Predictor
        second_predictor = Predictor(os.environ.get('TOROK_SECOND_MODEL', '/home/msf43/axiom-goal/models/overlap.ts'))

    return second_predictor

def solve_half(path, tptp, predictor, budget, output, support_size = 1, resume = False, shuffled = False, filter_size = 0, ladder = ()):
    started = time.monotonic()
    output = Path(output)
    matrix = load_problem(path, tptp)
    clauses = [clause_text(c) for c in matrix.clauses]
    remaining = lambda: max(.001, budget - (time.monotonic() - started))
    baseline = LiveSearch(clauses, remaining(), output / 'baseline')
    result = {'proved':False, 'clauses':len(clauses), 'support_size':support_size, 'filter_size':filter_size, 'ladder':list(ladder)}
    dual = any(ranking == Ranking.Overlap for _, _, ranking in ladder)

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

        # Filtering every axiom repeats the paused baseline.
        if not support_size and not ladder and len(clauses) - len(matrix.conjecture_clauses) <= filter_size:
            return fallback()

        def score():
            weights, info = predictor.predict(matrix)
            if dual:
                info['overlap_weights'] = second_scorer().predict(matrix)[0]

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
        rank = lambda weights: sorted((i for i in indices if i not in conjectures), key = lambda i:(-weights[i], i))
        ranked = rank(prediction['weights'])
        # Ranking control: pays the same scoring cost, then ignores the learned scores.
        if shuffled:
            import random
            random.Random(path.stem).shuffle(ranked)

        rankings = {Ranking.Learned: ranked}
        if dual:
            rankings[Ranking.Overlap] = rank(prediction['overlap_weights'])

        if filter_size and len(ranked) > filter_size:
            kept = conjectures | set(ranked[:filter_size])
            filtered = search(clauses, sorted(kept), min(2, remaining()), output / 'filtered')
            result['filtered_search'] = filtered
            if filtered['proved']:
                result['proved'] = True
                return result

        # Premise-selection ladder (DeepMath-style cutoffs); a cutoff covering every axiom repeats the baseline.
        result['ladder_searches'] = []
        for size, seconds, ranking in ladder:
            if len(ranked) <= size:
                break

            kept = conjectures | set(rankings[ranking][:size])
            step = search(clauses, sorted(kept), min(seconds, remaining()), output / f'ladder{size}{ranking}')
            result['ladder_searches'].append({'size':size, 'ranking':ranking, **step})
            if step['proved']:
                result['proved'] = True
                return result

        if not support_size:
            return fallback()

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
