# Design Decisions

## Why Ontology

Ontology-backed resolution gives the pipeline stable canonical values for common entities such as skills, companies, job titles, degrees, and countries. It also allows aliases and related terms to be managed centrally instead of being scattered across code.

## Why Deterministic

The assignment requires repeatable behavior. Deterministic rules make the output explainable, testable, and easy to compare across runs. If the same data comes in twice, the same canonical profile should come out twice.

## Why No LLM

The pipeline is intentionally not built around free-form LLM generation. LLM output is difficult to reproduce exactly, harder to validate, and less suitable for controlled candidate profiling where traceability matters.

## Why Provenance

Provenance is what makes the result auditable. It answers the question, "Why does this field have this value?" That is important both for debugging and for reviewer trust.

## Why Configurable Projection

The canonical model should stay stable even if the assignment output shape changes. A configurable projection layer lets the repository adapt output formats without rewriting the core pipeline or the transformation engines.