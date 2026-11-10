from enum import StrEnum
from pathlib import Path
import time
from bounded import bounded
from portfolio import search
from problem import load_problem, clause_text

class Mode(StrEnum):
    ResumeSupport1 = 'ResumeSupport1'
    ResumeSupport16 = 'ResumeSupport16'
    ShuffledResumeSupport1 = 'ShuffledResumeSupport1'
    ResumeFilter16 = 'ResumeFilter16'
    ShuffledResumeFilter16 = 'ShuffledResumeFilter16'
    ResumeFilter16Support1 = 'ResumeFilter16Support1'
    ResumeLadder = 'ResumeLadder'
    ShuffledResumeLadder = 'ShuffledResumeLadder'
    SampledResumeLadder = 'SampledResumeLadder'
    SharpSampledResumeLadder = 'SharpSampledResumeLadder'
    ResumeLadderSupport1 = 'ResumeLadderSupport1'
    ShuffledResumeLadderSupport1 = 'ShuffledResumeLadderSupport1'
    ResumeLongLadder = 'ResumeLongLadder'
    ShuffledResumeLongLadder = 'ShuffledResumeLongLadder'
    ResumeDualLadder = 'ResumeDualLadder'
    ShuffledResumeDualLadder = 'ShuffledResumeDualLadder'
    ResumeDualLadderSupport1 = 'ResumeDualLadderSupport1'
    ShuffledResumeDualLadderSupport1 = 'ShuffledResumeDualLadderSupport1'
    ShuffledResumeFilter16Support1 = 'ShuffledResumeFilter16Support1'
    Support16LongScore = 'Support16LongScore'
    HalfSupport1 = 'HalfSupport1'
    HalfSupport16 = 'HalfSupport16'
    WeightedSupport16 = 'WeightedSupport16'
    WeightedSupport16Seed2 = 'WeightedSupport16Seed2'
    Support1 = 'Support1'
    Support4 = 'Support4'
    Support8 = 'Support8'
    Support16 = 'Support16'
    LearnedSupport = 'LearnedSupport'
    RandomSupport = 'RandomSupport'
    Baseline = 'Baseline'
    Learned = 'Learned'
    LearnedDirect = 'LearnedDirect'
    Random = 'Random'

sampled = {Mode.SampledResumeLadder: 1, Mode.SharpSampledResumeLadder: 0.5}
ladders = (Mode.ResumeLadder, Mode.ShuffledResumeLadder, *sampled, Mode.ResumeLongLadder, Mode.ShuffledResumeLongLadder, Mode.ResumeDualLadder, Mode.ShuffledResumeDualLadder)
ladder_support = (Mode.ResumeLadderSupport1, Mode.ShuffledResumeLadderSupport1, Mode.ResumeDualLadderSupport1, Mode.ShuffledResumeDualLadderSupport1)
duals = (Mode.ResumeDualLadder, Mode.ShuffledResumeDualLadder, Mode.ResumeDualLadderSupport1, Mode.ShuffledResumeDualLadderSupport1)

# Dual ladders alternate the learned and symbol-overlap rankings at each cutoff.
def ladder_steps(mode):
    from half_support import Ranking
    sizes = (16, 64, 256)
    if mode in duals:
        return tuple((size, 6, ranking) for size in sizes for ranking in Ranking)
    if mode in (Mode.ResumeLongLadder, Mode.ShuffledResumeLongLadder):
        return tuple((size, 12, Ranking.Learned) for size in sizes)

    return tuple((size, 8, Ranking.Learned) for size in sizes) if mode in (*ladders, *ladder_support) else ()

def solve(path, tptp, predictor, mode, budget, output, threshold = 0.01, probe = 1, minimum = 64):
    filters = (Mode.ResumeFilter16, Mode.ShuffledResumeFilter16)
    combined = (Mode.ResumeFilter16Support1, Mode.ShuffledResumeFilter16Support1)
    resumed = (Mode.ResumeSupport1, Mode.ResumeSupport16, Mode.ShuffledResumeSupport1, *filters, *combined, *ladders, *ladder_support)
    if mode in (Mode.HalfSupport1, Mode.HalfSupport16, *resumed):
        from half_support import solve_half
        size = 16 if mode in (Mode.HalfSupport16, Mode.ResumeSupport16) else 1
        if mode in (*filters, *ladders):
            size = 0

        filter_size = 16 if mode in (*filters, *combined) else 0
        return solve_half(
            path,
            tptp,
            predictor,
            budget,
            output,
            size,
            mode in resumed,
            mode.startswith('Shuffled'),
            filter_size,
            ladder_steps(mode),
            sampled.get(mode, 0),
        )

    score_limit = budget / 4 if mode == Mode.Support16LongScore else 5
    if mode == Mode.Support16LongScore:
        minimum, probe, mode = 16, 1, Mode.LearnedSupport

    weighted = mode in (Mode.WeightedSupport16, Mode.WeightedSupport16Seed2)
    selection_seed = 2 if mode == Mode.WeightedSupport16Seed2 else 1
    if weighted:
        minimum, probe, mode = 16, 1, Mode.LearnedSupport

    sizes = {Mode.Support1: 1, Mode.Support4: 4, Mode.Support8: 8, Mode.Support16: 16}
    conservative_small = mode in (Mode.Support1, Mode.Support4, Mode.Support8)
    if mode in sizes:
        minimum, probe, mode = sizes[mode], 1, Mode.LearnedSupport

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
    gate = max(16, minimum) if conservative_small else minimum
    if mode == Mode.Baseline or len(candidates) <= gate:
        return finish(attempt(indices, budget, 'baseline'))
    if mode != Mode.LearnedDirect and probe > 0 and attempt(indices, probe, 'probe'):
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
    prediction = bounded(score, min(score_limit, max(0.001, remaining)), output / 'prediction.json')
    score_s = time.monotonic() - score_started
    if 'error' in prediction:
        return finish(attempt(indices, budget, 'fallback'), score_error = prediction['error'], score_s = score_s)

    weights = prediction['weights']
    ranked = sorted(candidates, key = lambda i: (-weights[i], i))
    if weighted:
        import math
        import random
        rng = random.Random(selection_seed)
        ranked = sorted(candidates, key = lambda i: -math.log(max(rng.random(), 1e-15)) / weights[i])
    required = conjectures | set(ranked[:minimum])
    selected = [i for i, p in enumerate(weights) if i in required or p >= threshold]
    support = mode in (Mode.LearnedSupport, Mode.RandomSupport)
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
