# Stage 1 One Page Design Document

## Problem

Candidate data arrives from multiple sources in inconsistent formats. The goal is to produce one trustworthy canonical profile without relying on non-deterministic guessing, while preserving explainability and traceability.

## Pipeline

1. Ingest CSV, ATS JSON, and resume sources through adapters.
2. Convert raw inputs into candidate fragments.
3. Resolve semantics against ontologies.
4. Cluster fragments by identity.
5. Fuse repeated evidence into a canonical candidate.
6. Score confidence and preserve provenance.
7. Project the canonical model into the assignment schema.
8. Validate the projected output.

## Canonical Schema

The canonical schema is the internal, normalized candidate contract. It holds the consolidated person profile, contact data, location, skills, experience, education, provenance, confidence, and evidence history.

The canonical schema is the only authoritative internal representation after fusion.

## Semantic Resolution

Semantic resolution maps noisy values to ontology-backed canonical values. Examples include skill aliases, company aliases, degree names, job titles, and country names.

This stage is deterministic and ontology-driven so the same input always yields the same resolution.

## Merge Policy

Merge behavior is policy-driven and field-specific.

- Emails and phones use union behavior.
- Skills use semantic union.
- Experience uses chronological ordering.
- Education uses merge behavior.
- Conflicts are retained when needed instead of being silently discarded.

## Confidence Policy

Confidence is computed from source reliability, cross-source agreement, extraction quality, semantic certainty, and conflict penalties.

The score is deterministic and bounded, with thresholds defining high, medium, and low confidence bands.

## Projection

Projection shapes the canonical candidate into the output schema required by the assignment. The default projection keeps the expected profile structure, while configuration can remap fields and normalize specific values.

Projection is the only layer allowed to reshape the output.

## Validation

Validation checks the projected JSON for missing required values, malformed phone numbers, invalid ISO country codes, and other schema issues.

Validation reports problems without crashing the pipeline so the output can still be reviewed.

## Edge Cases

The design explicitly handles malformed source data, duplicate values, conflicting values, unknown entities, and missing optional fields.

Unknown values are preserved, not fabricated.

## Scope Decisions

- No LLM-based candidate generation.
- No architectural coupling between output projection and semantic resolution.
- No hidden mutation of the canonical model after fusion.
- No silent dropping of provenance.
- No custom one-off branch logic for individual inputs.