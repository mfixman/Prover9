from dataclasses import dataclass
from enum import StrEnum
import json
import math
import os
from pathlib import Path
import random
import subprocess
import time

class Premises(StrEnum):
    P001 = 'P001'
    P01 = 'P01'
    P05 = 'P05'
    Full = 'Full'
    Ranked = 'Ranked'
    Top16 = 'Top16'
    Top64 = 'Top64'
    Quarter = 'Quarter'
    Half = 'Half'
    SampleQuarter = 'SampleQuarter'

@dataclass
class Slice:
    premises: Premises
    seconds: float

def select_indices(weights, conjectures, mode, seed = 1):
    candidates = [i for i in range(len(weights)) if i not in set(conjectures)]
    ranked = sorted(candidates, key = lambda i: (-weights[i], i))
    if mode == Premises.Full:
        return list(range(len(weights)))
    if mode == Premises.Ranked:
        return list(conjectures) + ranked

    thresholds = {Premises.P001: 0.01, Premises.P01: 0.1, Premises.P05: 0.5}
    if mode in thresholds:
        return sorted(set(conjectures) | {i for i in candidates if weights[i] >= thresholds[mode]})

    sizes = {Premises.Top16: 16, Premises.Top64: 64,
             Premises.Quarter: max(8, math.ceil(len(ranked) / 4)),
             Premises.Half: max(8, math.ceil(len(ranked) / 2))}
    if mode == Premises.SampleQuarter:
        rng = random.Random(seed)
        ranked.sort(key = lambda i: -math.log(max(rng.random(), 1e-15)) / weights[i])
        count = max(8, math.ceil(len(ranked) / 4))
    else:
        count = sizes[mode]

    return sorted(set(conjectures) | set(ranked[:count]))

def native_input(clauses, indices, seconds):
    settings = ['set(prolog_style_variables).', f'assign(max_seconds,{max(1, math.ceil(seconds))}).',
                'assign(max_megs,512).', 'clear(print_given).',
                'clear(print_initial_clauses).', 'clear(print_kept).', 'formulas(assumptions).']
    lines = [f'{clauses[i]} # label(torok_input_{i}).' for i in indices]
    return '\n'.join(settings + lines + ['end_of_list.', ''])

def search(clauses, indices, seconds, output, binary = None, extra_env = None, settings = (), usable = ()):
    output = Path(output)
    output.parent.mkdir(parents = True, exist_ok = True)
    text = '\n'.join(settings) + '\n' + native_input(clauses, indices, seconds)
    if usable:
        lines = [f'{clauses[i]} # label(torok_input_{i}).' for i in usable]
        text += '\nformulas(usable).\n' + '\n'.join(lines) + '\nend_of_list.\n'
    output.with_suffix('.in').write_text(text)
    env = {k: v for k, v in os.environ.items() if not k.startswith('PROVER9_TOROK_')}
    env.update(extra_env or {})
    binary = binary or Path(__file__).resolve().parents[1] / 'provers.src/prover9'
    started = time.monotonic()
    runner = Path(__file__).resolve().parent / 'build/native-search'
    command = [str(runner), str(binary), str(output.with_suffix('.in')), str(output.with_suffix('.log')), str(max(0.001, seconds))]
    process = subprocess.run(command, capture_output = True, text = True, env = env, check = True)
    result = json.loads(process.stdout)
    result['search_s'] = time.monotonic() - started
    result['retained'] = len(indices)
    return result

def run_schedule(prepared, schedule, budget_s, output, seed = 1):
    charged_s = prepared['parse_s']
    scored = False
    stages = []
    for number, stage in enumerate(schedule):
        if stage.premises != Premises.Full and not scored:
            charged_s += prepared['score_s']
            scored = True

        remaining = budget_s - charged_s
        if remaining <= 0:
            break
        if stage.premises != Premises.Full and prepared.get('score_error'):
            continue

        indices = select_indices(prepared['weights'], prepared['conjectures'], stage.premises, seed)
        result = search(prepared['clauses'], indices, min(stage.seconds, remaining), f'{output}-{number}')
        charged_s += result['search_s']
        stages.append({'premises': stage.premises, **result})
        if result['proved']:
            return {'proved': True, 'charged_s': charged_s, 'stages': stages, 'scored': scored}

    return {'proved': False, 'charged_s': charged_s, 'stages': stages, 'scored': scored}
