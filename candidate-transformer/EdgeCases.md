# EdgeCases

## Malformed CSV

If a CSV row is malformed or missing expected columns, the adapter should surface the issue and avoid corrupting the canonical pipeline state. The sample runner should still continue with valid rows when possible.

## Conflicting Emails

If multiple sources provide different emails for the same person, the merge policy keeps the evidence rather than guessing. Confidence and provenance capture the conflict so the reviewer can see the disagreement.

## Duplicate Skills

Duplicate skill mentions are deduplicated after canonicalization. Aliases such as `Python3`, `Python`, and `python` should collapse into one canonical skill.

## Unknown Companies

Unknown companies are preserved as raw or best-effort canonical values when no ontology match exists. The pipeline should not invent a company name.

## Missing Resume

If no resume is provided, the pipeline can still process structured sources such as CSV or ATS JSON. The result should degrade gracefully instead of failing the entire run.

## Invalid Phone

Invalid phone numbers should be reported by validation and may remain visible in the projected output if the projection configuration allows it. They should not be silently rewritten into a fake E.164 value.

## Conflicting Experience

When work history overlaps or sources disagree on dates, title, or employer, the merge policy should retain the strongest deterministic representation and keep provenance for the conflict.