# Demo Script

Approximate length: 2 minutes

## Script

"This repository implements a deterministic candidate transformation pipeline.

First, I want to show the architecture. Raw candidate data comes in through source adapters for CSV, ATS JSON, and resume documents. The pipeline then resolves semantics through ontologies, groups records by identity, fuses evidence into one canonical candidate, computes confidence, records provenance, and finally projects the result into the assignment output schema.

The semantic layer is important because it turns noisy inputs into canonical values. For example, skill aliases and country names are normalized before any merge logic runs, which keeps the result stable and explainable.

The projection layer is configurable. That means the canonical model stays the same, but the output format can be adjusted through configuration without changing the transformation engine.

Confidence is also deterministic. It combines source reliability, agreement, extraction quality, semantic certainty, and conflict penalties. That gives us a score that is reproducible and easy to justify.

Here is the end-to-end run. The CLI ingests the source files, runs the full pipeline, writes the projected JSON output, and validates the result. The important thing is that every step is deterministic and every value can be traced back through provenance.

That is the system: ontology-backed semantic resolution, deterministic merging, configurable projection, and structured validation."

## Suggested Live Flow

1. Open the architecture diagram in the README.
2. Show the CLI command from the README.
3. Run the command on `sample_inputs/candidate.csv`.
4. Open the generated JSON and point out `full_name`, `skills`, `provenance`, and `overall_confidence`.
5. Finish by showing `python tests/run_all_tests.py`.