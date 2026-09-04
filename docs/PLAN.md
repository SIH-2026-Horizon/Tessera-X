# Tessera-X — Implementation Plan

> This plan is organized entirely by **phases and gates**.  
> It intentionally does not assign calendar durations. Advancement depends on exit criteria, not elapsed time.

---

# 1. Planning Principles

The implementation order follows five rules.

1. **Prove data integrity before AI.**
2. **Prove semantic retrieval before orchestration complexity.**
3. **Create ground truth before claiming evaluation.**
4. **Keep expensive models behind deployment gates.**
5. **Freeze a working path before adding research features.**

The project is divided into:

```text
FOUNDATION
    ↓
SEARCH
    ↓
CONTROL PLANE
    ↓
CHANGE
    ↓
EVALUATION
    ↓
EVIDENCE
    ↓
ADVANCED INTELLIGENCE
    ↓
RELEASE HARDENING
```

---

# 2. Phase 0 — Scope Freeze and Acceptance Contract

## Objective

Define exactly what the first complete Tessera-X release must prove.

## Required decisions

Freeze:

```text
primary AOI
supported optical sensor
reference feature layers
semantic encoder
vector-index type
binary change model
demo queries
evaluation datasets
offline target environment
```

## Core user story

The release must support:

```text
Analyst enters a natural-language query
        ↓
system creates a validated GeoQueryPlan
        ↓
semantic + metadata + spatial filtering returns geolocated candidates
        ↓
analyst selects a candidate
        ↓
system compares suitable temporal observations
        ↓
binary change evidence is produced
        ↓
earliest supported observation is estimated
        ↓
result is exported with provenance
```

## Scope constraints

Do not include in the first acceptance contract:

- SAR fusion
- full UniChange dependency
- distributed infrastructure
- continual semantic-encoder training
- all-pairs graph construction
- bidirectional analyst vault sync
- autonomous enforcement decisions

## Deliverables

- `docs/acceptance.md`
- fixed AOI definition
- fixed source-scene list
- fixed demo query set
- capability matrix
- non-goal list
- model/license inventory
- target hardware profile

## Exit gate G0 — Scope Frozen

Pass when:

- every required capability has one named implementation path
- every model dependency has a fallback or explicit gate
- demo data is locally available
- no core path depends on an external network service

---

# 3. Phase 1 — Geospatial Data Foundation

## Objective

Guarantee that every later AI result maps correctly to source imagery and coordinates.

## Workstream 1.1 — Ingestion

Implement:

```text
scene validation
metadata extraction
CRS validation
timestamp validation
COG conversion/validation
checksum generation
STAC registration
```

## Workstream 1.2 — Canonical scene record

Minimum schema:

```yaml
scene_id:
platform:
sensor:
acquisition_time:
footprint:
crs:
gsd:
cloud_cover:
asset_path:
checksum:
ingestion_release:
```

## Workstream 1.3 — Patch extraction

Each patch must preserve:

```yaml
patch_id:
scene_id:
pixel_window:
footprint:
bbox:
timestamp:
sensor:
gsd:
quality_score:
```

The patch geometry, not just its centroid, must be queryable in PostGIS.

## Workstream 1.4 — Storage layout

Separate:

```text
metadata → PostgreSQL/PostGIS
scene rasters → local artifact store
patch metadata → PostgreSQL/PostGIS
large derived artifacts → CAS/DVC-style local store
```

## Tests

### Unit

- invalid CRS rejected
- invalid timestamp rejected
- duplicate scene ID handled
- bbox derived correctly
- patch footprints match raster transform

### Integration

- click a database patch and reconstruct the correct source window
- project patch footprint onto map
- trace patch → scene → source file

## Deliverables

- ingestion CLI
- STAC/PostGIS schema
- raster-store layout
- patch extractor
- geospatial integrity tests

## Exit gate G1 — Data Integrity

Pass when:

- every indexed patch maps back to the correct scene and geographic footprint
- source metadata is preserved
- raster and database identifiers agree
- an invalid geospatial product cannot silently enter the searchable archive

---

# 4. Phase 2 — Semantic Retrieval Baseline

## Objective

Prove useful offline text-to-satellite retrieval before adding a planner.

## Workstream 2.1 — Frozen LRSCLIP inference

Implement:

```text
image preprocessing
image embedding
text embedding
L2 normalization
model-version recording
```

Policy:

```text
semantic encoder is frozen
```

## Workstream 2.2 — FAISS index

Initial index:

```text
HNSW
```

Add SQ8 only if measured memory pressure justifies it.

Persist:

```yaml
vector_id:
patch_id:
embedding_namespace:
model_version:
index_shard:
```

## Workstream 2.3 — Hybrid metadata filtering

Support filters:

- AOI
- date range
- sensor
- quality threshold
- cloud threshold

## Workstream 2.4 — Search API

Implement:

```http
POST /search
```

Minimum request:

```json
{
  "query": "new residential construction",
  "bbox": [80.10, 12.60, 80.40, 12.90],
  "top_k": 50
}
```

## Workstream 2.5 — Map result view

Each result shows:

- patch
- scene
- timestamp
- similarity
- quality
- map geometry

## Baseline evaluation

Before query enhancement, capture retrieval performance on the fixed retrieval label pack.

This baseline is required so prompt ensembling or planner rewriting can later prove that it helps.

## Deliverables

- frozen embedding pipeline
- FAISS index builder
- retrieval API
- basic map results
- baseline retrieval report

## Exit gate G2 — Search Works

Pass when:

- text queries execute locally
- results are geolocated
- results map to source scenes
- retrieval metrics run automatically
- the index can accept new vectors without a full rebuild

---

# 5. Phase 3 — Query Contract and Deterministic Control Plane

## Objective

Convert analyst language into a machine-checkable execution contract.

## Workstream 3.1 — `GeoQueryPlan` schema

Define fields for:

```text
raw query
intent
targets
prompt candidates
AOI
spatial relations
temporal window
sensor filters
quality filters
execution budget
unresolved slots
ignored terms
defaults
release ID
```

## Workstream 3.2 — Rules-tier planner

Support the most important patterns:

```text
<concept> near <feature>
<concept> in <AOI>
<concept> since <date>
<concept> between <date1> and <date2>
changes in <AOI>
sites similar to <site_id>
```

The deterministic rule tier is the default path for the fixed demo query family.

## Workstream 3.3 — Independent constraint checker

Do not allow the planner to audit itself.

Create a separate extractor for:

- dates
- numeric distances
- AOI names
- sensor names
- relation phrases
- recognized concepts
- negations

Compare extracted constraints against the plan.

### Hard failure examples

Reject if:

```text
500 m → 300 m
Sentinel-2 → Landsat
since 2022 → since 2024
near river → relation omitted
```

unless the analyst explicitly edits the plan.

## Workstream 3.4 — Deterministic planner confidence

Planner confidence is computed from measurable coverage.

Suggested components:

```text
slot_coverage
constraint_coverage
lexicon_coverage
capability_coverage
default_penalty
fallback_penalty
```

No LLM-generated confidence field is trusted.

## Workstream 3.5 — Capability validator

Validate:

```text
requested AOI exists
requested time range intersects archive coverage
required feature layer covers AOI
requested sensor exists
change search has enough temporal observations
requested relation is supported
```

## Workstream 3.6 — Relation policy

Create versioned relation defaults by relation + feature class.

Example:

```yaml
- policy_id: REL_NEAR_RIVER_V1
  relation: near
  feature_class: waterway_river
  default_distance_m: 300

- policy_id: REL_NEAR_ROAD_V1
  relation: near
  feature_class: road_major
  default_distance_m: 150
```

## Workstream 3.7 — PostGIS relation compiler

Compile:

```text
near / beside / close to
inside / within
outside / away from
```

into deterministic predicates.

Use patch geometry, not only centroid geometry.

Example:

```sql
ST_DWithin(
    p.geom::geography,
    f.geom::geography,
    :distance_m
)
```

## Workstream 3.8 — Budget gate

Estimate candidate cardinality using database/index statistics.

Enforce limits such as:

```text
max semantic candidates
max temporal candidates
max change pairs
```

Degrade explicitly rather than silently.

## Workstream 3.9 — Explain endpoint

Implement:

```http
GET /plan/{plan_id}/explain
```

Show:

```text
constraints
defaults
ignored terms
unresolved fields
operators
candidate counts by stage
degradations
feature layers
policies
release
```

## Deliverables

- plan schema
- rules parser
- independent checker
- capability validator
- relation-policy table
- relation compiler
- budget enforcement
- explain trace

## Exit gate G3 — Query Plan Is Auditable

Pass when:

- every important raw-query constraint is accounted for
- explicit numeric constraints cannot change silently
- unsupported relations are declared
- defaults are visible
- the system can explain why a candidate survived each filtering stage

---

# 6. Phase 4 — Image Quality and Registration

## Objective

Prevent avoidable false change before running a change model.

## Workstream 4.1 — Observation quality

Generate or ingest:

- cloud mask
- cloud-shadow mask where available
- nodata mask
- saturation indicators
- usable-area fraction

## Workstream 4.2 — Registration

Integrate AROSICS or equivalent verified co-registration.

Persist:

```yaml
registration_status:
reference_scene:
target_scene:
mean_shift_x:
mean_shift_y:
rmse_px:
valid_control_points:
usable_overlap:
quality_score:
```

## Workstream 4.3 — Quality gate

Pairs can be:

```text
accepted
accepted_with_penalty
rejected
```

Reasons are machine-readable.

## Workstream 4.4 — Pair selection

Only select temporal pairs that satisfy:

- spatial overlap
- registration validity
- source quality
- required temporal ordering
- supported sensor policy

## Deliverables

- quality pipeline
- registration pipeline
- pair selector
- rejection reasons
- quality-gate tests

## Exit gate G4 — Temporal Inputs Are Trustworthy

Pass when:

- known poor pairs are rejected
- registration metrics are recorded
- temporal analysis never runs without pair-quality metadata
- false edge changes caused by obvious misalignment are reduced in the hard-negative evaluation set

---

# 7. Phase 5 — Binary Change Detection Baseline

## Objective

Produce a reproducible, measured binary change mask.

## Primary model

```text
ChangeFormerV6
```

## Workstream 5.1 — Public benchmark reproduction

Before local claims:

- run a public labeled example
- reproduce inference pipeline
- verify mask geometry
- calculate metrics against provided ground truth

## Workstream 5.2 — Local geospatial integration

Input:

```text
registered T1 patch
registered T2 patch
```

Output:

```yaml
change_probability_map:
binary_change_mask:
model_confidence:
model_version:
```

## Workstream 5.3 — Quality-aware confidence

Initial operational confidence:

```text
EffectiveConfidence =
    ModelConfidence
  × RegistrationQuality
  × ObservationQuality
```

Do not freeze this formula permanently.

Later calibrate it against the locked local set.

## Workstream 5.4 — Post-processing

If needed:

- thresholding
- removal of tiny components
- optional morphology

Every parameter is versioned.

## Deliverables

- change inference service
- public benchmark test
- local mask output
- effective-confidence record
- change visualization

## Exit gate G5 — Binary Change Is Measured

Pass when:

- public benchmark scoring works
- local T1/T2 pair produces a georeferenced mask
- mask can be overlaid on source imagery
- confidence includes source-quality information
- false positives are categorized

---

# 8. Phase 6 — Ground Truth and Evaluation

## Objective

Make every claimed metric executable.

## Workstream 6.1 — Public benchmark layer

Use established labeled datasets for model/pipeline correctness.

For binary change detection, use one or more supported public datasets.

For semantic change detection, reserve the appropriate semantic benchmark for the UniChange phase.

## Workstream 6.2 — Local change pack

Build a deliberately difficult local pack.

Include:

### Positive examples

- building construction
- road construction
- land clearing
- water-extent change
- land-cover-to-built-up transitions

### Hard negatives

- seasonal vegetation
- crop-state differences
- cloud
- cloud shadow
- registration artifacts
- true no-change pairs

## Workstream 6.3 — Annotation schema

Minimum:

```yaml
pair_id:
scene_t1:
scene_t2:
bbox:
change_present:
change_types:
binary_change_mask:
quality_flags:
annotator_1:
annotator_2:
adjudication_status:
```

## Workstream 6.4 — Review protocol

Use independent review.

Escalate disagreements in:

- change/no-change
- transition class
- mask geometry
- earliest-supported observation

## Workstream 6.5 — Locked evaluation split

Separate:

```text
calibration/development
locked final evaluation
```

The final set must not be used to tune thresholds.

## Workstream 6.6 — Retrieval relevance benchmark

Create:

- fixed query set
- pooled candidate results
- blinded relevance judgments
- graded labels `0 / 1 / 2`

Metrics:

- nDCG@5
- nDCG@10
- Precision@5
- Precision@10
- MRR

Do not claim local corpus-wide Recall@K unless relevance labels are exhaustive.

## Workstream 6.7 — Planner benchmark

Create query cases that test:

- dates
- distance constraints
- sensor names
- AOIs
- defaults
- ambiguity
- negation
- unsupported relations
- unknown terms

Metrics:

```text
slot exact match
constraint preservation
numeric preservation
ignored-term recall
unsupported-capability detection
clarification rate
plan execution success
```

## Workstream 6.8 — Runtime benchmark

Measure:

```text
P50/P95/P99 search latency
embedding throughput
index memory
change-inference latency
registration latency
cache hit rate
candidate reduction by operator
```

Always record:

```text
hardware
corpus size
model versions
index parameters
batch size
release ID
```

## Deliverables

- public benchmark scripts
- local annotation pack
- retrieval relevance pack
- planner test pack
- locked evaluation configuration
- reproducible metric report

## Exit gate G6 — Claims Are Backed by Labels

Pass when:

- every core metric has actual ground truth
- benchmark scripts run automatically
- literature, target, and measured numbers are visibly separated
- final evaluation data is locked
- failure categories are reported

---

# 9. Phase 7 — Earliest Supported Observation

## Objective

Determine the earliest usable observation supporting a verified change.

## Workstream 7.1 — Timeline construction

For a selected AOI/candidate:

- fetch all overlapping observations
- order temporally
- attach quality
- attach registration availability
- attach usability reason

## Workstream 7.2 — Trusted baseline

Select a valid pre-change baseline.

## Workstream 7.3 — Coarse-to-fine search

Search the usable timeline without assuming every calendar observation is valid.

## Workstream 7.4 — Persistence confirmation

Where the phenomenon should persist, verify support in a later valid observation.

## Output

```yaml
last_supported_no_change:
earliest_supported_change:
next_confirming_observation:
unusable_observations:
confidence:
```

## Workstream 7.5 — Timeline benchmark

Create curated AOI timelines with reviewer labels.

Measure:

- exact-acquisition match
- valid-acquisition error
- temporal error
- correct skipping of unusable scenes

## Deliverables

- timeline service
- earliest-supported API
- timeline UI
- temporal benchmark

## Exit gate G7 — Timeline Claim Is Defensible

Pass when:

- the system never reports an unusable observation as the earliest support
- source scenes are visible
- reviewers can reproduce the result from the timeline
- the output wording says “earliest supported observation,” not “exact event date”

---

# 10. Phase 8 — Evidence Workspace and Provenance

## Objective

Turn model output into inspectable evidence.

## Workstream 8.1 — Evidence view

Show:

- map context
- source T1
- source T2
- swipe/overlay comparison
- change mask
- quality masks
- registration metrics
- candidate geometry
- spatial relation evidence
- timeline
- model/release versions

## Workstream 8.2 — Analyst verdicts

Support:

```text
confirm
reject
uncertain
```

Record:

```yaml
analyst_id:
timestamp:
candidate_id:
verdict:
notes:
release_id:
```

## Workstream 8.3 — Release manifest

A release ties together:

- code commit
- model hashes
- embedding namespace
- index shards
- STAC snapshot
- feature-layer versions
- prompt/lexicon versions
- relation policy
- evaluation pack
- benchmark report

## Workstream 8.4 — Reproduction command

Design toward:

```bash
python -m tessera_x.repro run \
  --release REL_... \
  --result CHG_...
```

## Deliverables

- evidence workspace
- verdict storage
- release manifest
- provenance export
- reproduction command

## Exit gate G8 — Evidence Is Reproducible

Pass when:

- a result can be traced back to source scenes
- every default and model version is recorded
- a release manifest identifies all major dependencies
- historical evidence is not silently recomputed under a new model version

---

# 11. Phase 9 — Knowledge Substrate

## Objective

Persist operational facts and analyst decisions without adding an unnecessary graph database.

## Workstream 9.1 — Core graph tables

Use PostgreSQL/PostGIS:

```sql
kg_nodes(...)
kg_edges(...)
```

## Workstream 9.2 — Explicit `ChangeEvent` node

Represent change as:

```text
ChangeEvent
  ├── at_site → Site
  ├── baseline → Scene
  ├── comparison → Scene
  ├── classified_as → Concept
  └── derived_from → Release
```

Do not encode the temporal event as an ambiguous `Site → Scene, Scene` edge.

## Workstream 9.3 — Verdict graph

Persist:

```text
Query → Candidate
Verdict → Candidate
Candidate → Site/Patch
Report → ChangeEvent
```

## Workstream 9.4 — Sparse similarity edges

Rules:

- FAISS remains authoritative
- store top-N only
- materialize for confirmed or actively reviewed entities
- store encoder version and namespace
- invalidate on model promotion

## Workstream 9.5 — Ground-truth export

Analyst verdicts can be exported into a training/review pack.

Keep the locked evaluation set independent to avoid feedback leakage.

## Deliverables

- graph schema
- write adapters
- graph evidence paths
- verdict export
- sparse similarity projection

## Exit gate G9 — Knowledge Layer Adds Operational Value

Pass when at least one real workflow is improved:

- similar-site queue
- provenance graph
- verdict export
- evidence report linkage

The graph is not accepted merely because nodes can be displayed.

---

# 12. Phase 10 — Local LLM Planner Upgrade

## Objective

Support free-form analyst language while preserving deterministic guarantees.

## Preconditions

Do not start until:

- rules planner works
- independent checker works
- explain trace works
- evaluation queries exist

## Workstream 10.1 — Local planner model

Use a locally hosted instruction model appropriate for the available CPU/RAM.

Keep GPU resources reserved for vision/change inference when necessary.

## Workstream 10.2 — Grammar-constrained output

Generate only schema-valid JSON.

## Workstream 10.3 — Tiered execution

Order:

```text
cache
rules
LLM
rules fallback
```

## Workstream 10.4 — Lexicon-constrained concepts

Planner concepts must resolve to:

- supported retrieval concepts
- staged feature classes
- explicit unknown/ignored terms

## Workstream 10.5 — Query enhancement experiment

Evaluate prompt ensembling against the locked retrieval development set.

Do not enable by default unless measured results improve.

## Workstream 10.6 — Clarification policy

Ask only when:

- required scope is missing
- high-value constraint remains unresolved
- unsupported target is central
- budget degradation changes the user’s intended scope materially

Prefer preview over interrogation when relevance is the ambiguity.

## Deliverables

- local LLM tier
- constrained grammar
- prompt/lexicon versions
- fallback path
- planner evaluation report

## Exit gate G10 — LLM Adds Flexibility, Not Risk

Pass when:

- rules queries remain stable
- explicit constraints are preserved
- fallback is automatic
- LLM planner improves free-form coverage
- the planner cannot silently bypass the independent checker

---

# 13. Phase 11 — UniChange Semantic Upgrade

## Objective

Add instruction-conditioned semantic change detection without making it a dependency of the binary-change release.

## Architecture assumption

UniChange is treated as:

```text
T1
T2
text instruction
    ↓
MLLM task-token generation
+
remote-sensing visual features
    ↓
Token Driven Decoder
    ↓
T1 semantics
T2 semantics
change mask
```

## Deployment gate

Verify:

- checkpoint availability
- code reproducibility
- hardware fit
- licensing
- benchmark reproduction
- inference stability
- geospatial mask alignment

## Evaluation

Compare against:

- binary baseline
- semantic public benchmark
- local semantic subset

Measure semantic-change metrics appropriate to the selected benchmark.

## Promotion rule

Enable UniChange in the analyst workflow only when it adds demonstrated semantic value.

Otherwise preserve:

```text
ChangeFormerV6 + analyst interpretation
```

as the stable path.

## Deliverables

- UniChange adapter
- benchmark report
- semantic output schema
- UI semantic-transition view

## Exit gate G11 — Semantic Change Adds Measured Value

Pass when the system can defend the semantic transition labels with ground truth.

---

# 14. Phase 12 — Similar-Site Intelligence and Feedback Reranking

## Objective

Use verified analyst knowledge to improve discovery without contaminating evaluation.

## Workstream 12.1 — Image-to-image retrieval

Select a known site or patch and query FAISS.

## Workstream 12.2 — Sparse graph expansion

Materialize only operational top-N neighbors.

## Workstream 12.3 — Analyst feedback

Create training data from non-evaluation verdicts.

## Workstream 12.4 — Lightweight reranker

Train only a post-embedding relevance layer.

Do not fine-tune the frozen encoder during normal ingestion.

## Workstream 12.5 — Bias controls

Maintain:

- fixed holdout
- per-concept confirmation rates
- class distribution
- rejection rates
- concentration alerts

## Deliverables

- similar-site API
- similarity evidence view
- reranker training pipeline
- feedback isolation policy

## Exit gate G12 — Feedback Improves Search Without Circular Evaluation

Pass when:

- holdout performance improves or stays stable
- feedback data never leaks into the locked test slice
- results still cite the original frozen embedding namespace

---

# 15. Phase 13 — Artifact and Index Versioning

## Objective

Make model and index upgrades operational rather than destructive.

## Workstream 13.1 — Append-only index shards

Design:

```text
namespace/
  shard_001 sealed
  shard_002 sealed
  shard_003 open
  tombstones
  manifest
```

## Workstream 13.2 — Content-addressed artifacts

Large artifacts use:

```text
sha256-derived identity
```

or a local DVC remote.

## Workstream 13.3 — New embedding namespace

New encoder version:

```text
ns_model_version_dimension
```

No overwrite.

## Workstream 13.4 — Priority re-embedding

Prioritize:

1. analyst-verified patches
2. confirmed sites
3. active AOIs
4. remaining archive

## Workstream 13.5 — Migration query mode

During migration:

```text
old namespace
+
new namespace
    ↓
rank fusion
```

Label results as migration mode.

## Workstream 13.6 — Promotion gate

Primary criteria:

- locked benchmark does not regress
- target operational concepts improve or trade off acceptably
- runtime and storage remain acceptable

Diagnostic criteria:

- old/new top-K overlap
- disagreement review

Top-K agreement with the old encoder is **not** itself a success requirement.

## Deliverables

- shard manager
- namespace manager
- migration tracker
- promotion report
- rollback capability

## Exit gate G13 — Model Upgrades Do Not Break Historical Evidence

Pass when:

- old reports remain reproducible
- old namespace remains available read-only
- new search can be promoted independently
- stale embedding-derived graph edges are invalidated

---

# 16. Phase 14 — SAR and Cross-Sensor Extensions

## Objective

Improve resilience where optical imagery is insufficient.

## Design rule

Do not replace source evidence with generated photorealistic imagery.

Preferred path:

```text
optical features
+
SAR features
    ↓
feature/decision fusion
```

## Workstreams

- Sentinel-1 ingestion
- SAR preprocessing
- sensor-aware quality
- cross-sensor calibration
- feature or decision fusion
- cross-sensor evaluation

## Honest status

Cross-sensor domain shift is **mitigated**, not assumed solved.

## Deliverables

- SAR ingestion
- SAR feature branch
- fusion experiment
- domain-shift evaluation

## Exit gate G14 — SAR Improves Measured Robustness

Pass only if it improves relevant cloudy/monsoon cases without introducing unsupported evidence claims.

---

# 17. Phase 15 — Release Hardening

## Objective

Prepare Tessera-X for repeatable offline use.

## Workstream 15.1 — Offline test

Disable outbound access and run the complete acceptance workflow.

## Workstream 15.2 — Dependency freeze

Capture:

- Python environment
- Docker images
- model hashes
- database migration version
- release manifest

## Workstream 15.3 — Failure testing

Test:

- corrupt scene
- missing feature layer
- unsupported relation
- no temporal pair
- poor registration
- stale cache
- wrong release ID
- missing model
- index shard unavailable
- planner failure

## Workstream 15.4 — Security controls

As required:

- local auth
- role-based permissions
- audit log
- file integrity
- release signing/checksums
- controlled update process

## Workstream 15.5 — Documentation freeze

Finalize:

- README
- architecture
- plan
- operator docs
- model inventory
- benchmark report
- demo runbook

## Deliverables

- offline release bundle
- smoke tests
- regression tests
- demo runbook
- benchmark report
- release manifest

## Exit gate G15 — Releasable System

Pass when the core workflow runs reproducibly in the offline target environment.

---

# 18. Cross-Phase Test Matrix

| Capability | Unit | Integration | Evaluation | Offline |
|---|---:|---:|---:|---:|
| COG/STAC ingestion | ✓ | ✓ | — | ✓ |
| Patch geolocation | ✓ | ✓ | sampled | ✓ |
| LRSCLIP embedding | ✓ | ✓ | retrieval benchmark | ✓ |
| FAISS retrieval | ✓ | ✓ | nDCG / Precision | ✓ |
| Query plan | ✓ | ✓ | planner benchmark | ✓ |
| Constraint checker | ✓ | ✓ | preservation rate | ✓ |
| PostGIS relations | ✓ | ✓ | spatial fixtures | ✓ |
| Registration | ✓ | ✓ | RMSE / hard negatives | ✓ |
| ChangeFormer | ✓ | ✓ | F1 / IoU | ✓ |
| Temporal localization | ✓ | ✓ | acquisition error | ✓ |
| Evidence/provenance | ✓ | ✓ | reproducibility | ✓ |
| Knowledge graph | ✓ | ✓ | workflow value | ✓ |
| UniChange | ✓ | ✓ | semantic benchmark | ✓ |
| Migration | ✓ | ✓ | promotion gate | ✓ |

---

# 19. Final Implementation Priority

When trade-offs are necessary, protect this chain first:

```text
DATA INTEGRITY
    ↓
RETRIEVAL
    ↓
QUERY VALIDATION
    ↓
SPATIAL GROUNDING
    ↓
QUALITY GATE
    ↓
BINARY CHANGE
    ↓
GROUND TRUTH
    ↓
TEMPORAL LOCALIZATION
    ↓
PROVENANCE
```

Then add:

```text
LLM planner
semantic change
knowledge-driven discovery
reranking
migration automation
SAR
```

The system is successful when the core evidence path is correct and measurable, not when every optional component exists.
