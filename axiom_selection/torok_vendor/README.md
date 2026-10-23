# Frozen Torok preprocessing

This directory contains the parser, syntax representation, CNF conversion and
graph-building dependencies used by the bundled Torok model. It is copied from
the user's Connections checkout; no external checkout is imported at runtime.
Training, checkpoint selection and prover execution are not included.

`provenance.json` records the source revision and original/vendored file hashes.
Absolute package imports were renamed into the `torok_vendor` namespace, and
`axiom_prediction/__init__.py` was emptied to omit unused training-model exports.
The algorithms are unchanged. Preserve this snapshot alongside the model when
copying Prover9 to the HPC. Changes to preprocessing require parity validation.

The source is GPL-3.0-or-later; its original license and copyright notice are
preserved in `LICENSE`. Source paths and file hashes include working-tree changes
that may not be represented by the recorded Git revision alone.

`tests/fixtures/preprocessing.json` contains clauses, graph hashes and model
scores captured from the original checkout before vendoring. Run
`python axiom_selection/tests/preprocessing.py` to compare the bundled pipeline
against those references while forbidding external package imports.
