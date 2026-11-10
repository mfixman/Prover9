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

# The second ladder ranking comes from an untrained symbol-overlap scorer unless SECOND_RANKING_MODEL overrides it.
def second_scorer():
    global second_predictor
    if second_predictor is None:
        from predict import Predictor
        second_predictor = Predictor(os.environ.get('SECOND_RANKING_MODEL', '/home/msf43/axiom-goal/models/overlap.ts'))

    return second_predictor

# An order drawn without replacement in proportion to weight ** (1 / temperature) (Gumbel top-k).
def sampled_order(ranked, weights, temperature, seed):
    import math
    import random
    min_weight = 1e-6
    rng = random.Random(seed)
    keys = {
        i: math.log(max(min_weight, weights[i])) / temperature - math.log(-math.log(max(1e-300, rng.random())))
        for i in ranked
    }

    return sorted(ranked, key = lambda i: -keys[i])

def solve_half(path, tptp, predictor, budget, output, support_size = 1, resume = False, shuffled = False, filter_size = 0, ladder = (), temperature = 0):
    started = time.monotonic()
    output = Path(output)
    matrix = load_problem(path, tptp)
    clauses = [clause_text(c) for c in matrix.clauses]
    remaining = lambda: max(.001, budget - (time.monotonic() - started))
    baseline = LiveSearch(clauses, remaining(), output / 'baseline')
    result = {'proved':False, 'clauses':len(clauses), 'support_size':support_size, 'filter_size':filter_size, 'ladder':list(ladder), 'temperature':temperature}
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

        # Noise control between the learned order (temperature 0) and the shuffled one.
        if temperature:
            ranked = sampled_order(ranked, prediction['weights'], temperature, path.stem)

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
