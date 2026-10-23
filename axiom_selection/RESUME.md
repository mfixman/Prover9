# Short Torok search, then resume Prover9

The strongest coverage result in this development search is available as
`--strategy resume1`. The earlier strategy remains `--strategy support16`.

## Rule

1. Run ordinary Prover9 for one second of the total wall budget.
2. If unsolved, pause that process and score the input with Torok, allowing up
   to one quarter of the total budget for scoring.
3. Start ordinary Prover9 with the highest-scoring axiom and all conjecture
   clauses in the initial set of support. Keep every other axiom usable.
   Give this search at most one third of the total budget.
4. If no proof is found, resume the original process for the remaining time.
   Scoring failure also resumes the original process.

At a 30-second budget this means a one-second probe, a scoring cap of 7.5
seconds, and at most ten seconds of guided search. Parsing, scoring, both
searches and orchestration are inside one wall deadline. Input-order ties are
stable. No axiom is deleted. Nonempty usable lists also disable Prover9's initial
predicate elimination. There is no problem-family routing or retraining.

The paused baseline preserves its search state. Only one search or scorer is
CPU-active per case, but retaining the paused prover can increase peak memory.
Python orchestrates parsing and compiled TorchScript inference; proof search and
first-refutation detection run in C. Linux pidfds control pause/resume safely.

## Paired development result

`results/resume1-comparison/` contains the full paired run: the same 180 CNF
families as earlier comparisons, with two unsupported-symbol cases excluded.
Each arm has 30 seconds, 18 single-core workers, and model loading/warm-up once
per worker outside individual problem budgets. Per-problem scoring is charged.

| Strategy | Proofs / 178 | PAR-2 seconds |
|---|---:|---:|
| Ordinary Prover9 | 101 | 26.840 |
| Preserved Torok top-16 | 103 | 26.598 |
| Short Torok top-1, resume baseline | 106 | 26.351 |

This is five more proofs than baseline (4.95%) and three more than the paired
preserved strategy (2.91%). PAR-2 improves by 1.82% and 0.93%, respectively.
PAR-2 charges 60 seconds for a timeout. All 101 baseline successes are retained.
However, their summed time rises from 157.46 to 341.11 seconds. The strategy
improves coverage and penalized time, not speed on common successes.

New baseline successes are GEO077-4, GEO083-1, GRP235-1, LCL806-1 and NUM017-1.
Against top-16, it adds GRP235-1 and NUM017-1 and recovers SET025-8 and SET163-6,
but loses HWV003-1. NUM017-1 and scoring near cutoffs vary between earlier runs;
use contemporaneous comparisons rather than claiming every difference is stable.
Torok-guided search was reached on 74 of the 178 supported cases.

The main comparison took 467.39 seconds. Two further repetitions of each of
the five new successes took 42.67 seconds: Torok solved all 10 runs. Baseline
again failed on GEO077-4, GEO083-1, LCL806-1 and NUM017-1 in both repetitions.
GRP235-1 became a baseline success at 28.06/28.67 seconds, versus Torok at
6.35/6.32 seconds. Thus four coverage gains repeated, while the fifth is a
clear speed gain in those repeats rather than a stable timeout distinction.
Repetitions used ten active workers, so machine load differed from the main run.
See `results/resume1-repeats/`; these repeats do not enlarge the independent sample.

This is repeatedly tuned development data: split scheme 4, part 8, which was
also used for checkpoint selection. It is not an independent generalization
result. A matching random-ranking ablation for this final schedule has not been
run; these results do not isolate how much the learned ranking contributes.

## Execute

The defaults are 60 seconds per strategy and one worker per CPU available in
the process affinity mask. On the HPC, run inside the scheduler allocation
with the appropriate CPU binding. For local runs, pass `--workers 18`. The
commands below specify the original 30-second budget for reproducibility.

Reproduce the paired sample:

```sh
python axiom_selection/compare.py --strategy resume1 --seconds 30 --workers 18 \
  --manifest axiom_selection/results/paired-support16/manifest.json \
  --output axiom_selection/results/my-resume1-comparison
```

Compare all three arms across known-unsatisfiable CNF variants:

```sh
python axiom_selection/compare.py --all-cnf-unsat --seconds 30 --workers 18 \
  --modes Baseline Support16 ResumeSupport1 \
  --output axiom_selection/results/full-cnf-resume1
```

The output directory must be new. This adapter supports CNF only, not all TPTP
languages; FOF still needs a shared clausification step. The all-CNF command
includes training families, so analyze held-out families separately. A longer
per-problem budget scales the guided allocation and scoring cap, which has not
yet been validated. Model startup contributes to batch elapsed time.

The implementation and model hashes are frozen in `resume_config.json`; each
new experiment also saves its source snapshot and executable hashes. The
pause/resume, paused-process timeout, first-proof, and support-splitting checks
pass. Earlier unsuccessful alternatives are recorded in `SUPPORT.md`.
