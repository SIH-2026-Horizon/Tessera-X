# ADR-001: Evidence-First Activity Intelligence

## Status

Accepted

## Context

Tessera-X already supports semantic retrieval, deterministic spatial grounding, temporal change analysis, earliest-supported observations, and similar-site discovery. The next capability must correlate several observable changes, compare them with a defensible historical baseline, track their lifecycle, prioritize review, and find comparable patterns without weakening provenance or implying intent from imagery.

The repository is currently at the specification stage. The first release remains offline, quality-gated, and analyst-reviewed.

## Options Considered

| Option | Benefits | Costs and risks |
|---|---|---|
| One end-to-end activity classifier | Simple runtime contract | Opaque reasoning, weak provenance, difficult calibration, expensive labels |
| Independent detectors plus a learned fusion model | Flexible and potentially accurate | Requires substantial training data and careful correlated-error handling |
| Typed indicator observations plus versioned correlation policies | Auditable, incrementally implementable, compatible with current architecture | More explicit schemas and policy management |

## Decision

Use typed, source-linked `IndicatorObservation` records and versioned `ActivitySignature` definitions. Correlate indicators only after quality, registration, historical-baseline, and change gates pass.

Represent each result as an `ActivityAssessment` containing:

- matched and missing indicators
- baseline and source-scene provenance
- correlation-policy version
- lifecycle history and geometry measurements
- evidence confidence
- a separate, explained review priority
- release and model versions

Use a two-stage similar-pattern workflow: FAISS generates multi-temporal signature candidates, then an explicit verifier checks required indicators, spatial relationships, timing, lifecycle compatibility, and evidence quality.

## Rationale

1. It preserves the architectural rule that models generate candidates while source-linked operators provide evidence.
2. It allows an initial narrow vocabulary to work before specialist detectors or learned fusion are mature.
3. It prevents a high review priority from being mistaken for strong evidence.
4. It distinguishes genuine multi-temporal similarity from a single-image visual lookalike.

## Trade-offs

- More records and policy versions must be managed.
- Rule-based correlation may initially miss valid patterns that a mature learned fusion model could detect.
- Multi-observation baselines increase storage and preprocessing cost.
- Signature-level retrieval requires a new embedding namespace and evaluation set.

## Mitigations

- Begin with clearing, new tracks, and new structures in a fixed AOI and sensor profile.
- Preserve `unclassified_change` when no typed detector is sufficiently supported.
- Calibrate and evaluate each layer independently before measuring end-to-end signatures.
- Keep learned fusion behind a future deployment gate; do not make it a core dependency.

## Revisit Triggers

Reconsider the correlation implementation when a locked, representative dataset shows that a learned fusion model materially improves signature-level precision/recall without reducing explainability or reproducibility.
