# Tessera-X — SIH PPT Content

Paste-ready content for a six-slide technical SIH deck describing the complete production system: offline data ingestion, semantic search, temporal intelligence, distributed execution, security, observability and reproducible release operations. Figures marked as design targets require validation on the deployment hardware.

## Slide 1 — Title

### SMART INDIA HACKATHON 2026

- **Problem Statement ID:** [INSERT OFFICIAL PS ID]
- **Problem Statement:** [INSERT EXACT OFFICIAL TITLE]
- **Theme:** [INSERT THEME]
- **Category:** Software
- **Team ID:** [INSERT TEAM ID]
- **Team:** [INSERT REGISTERED TEAM NAME]

### Project

**TESSERA-X**

*Offline Semantic Earth-Observation Intelligence*

**One-line pitch:** Ask a satellite archive a natural-language question; receive geospatially grounded, temporally verified and source-linked evidence—without sending data to the cloud.

**Visual:** one search sentence over a map, flowing to a ranked change-evidence card. Keep this slide sparse.

---

## Slide 2 — Proposed Solution

### THE PROBLEM — SEARCH FINDS SCENES, NOT ANSWERS

- Satellite archives are searched mainly by **coordinates, dates, sensor and cloud cover**, not by visual meaning.
- Embedding similarity may find “construction-like” texture, but it cannot prove **near a river**, **inside a zone** or another exact spatial relation.
- Naive before/after comparison confuses cloud, shadow, seasonality and misregistration with real change.
- A language model can parse intent, but an unconstrained model can silently alter dates, distances or unsupported relations.
- Cloud-first AI conflicts with sensitive, bandwidth-constrained and sovereign data environments.

### THE SOLUTION — COMPILE LANGUAGE INTO AUDITABLE COMPUTATION

```text
Analyst question + AOI/session context
              ↓
Typed GeoQueryPlan
              ↓
Independent constraint check + capability/budget validation
              ↓
STAC/PostGIS metadata filters + LRSCLIP/FAISS semantic retrieval
              ↓
Deterministic PostGIS spatial predicates
              ↓
Quality-valid temporal pair/baseline + image registration
              ↓
Change localization + temporal/lifecycle analysis
              ↓
Source-linked evidence + analyst verdict + reproducible release
```

### CORE DESIGN PRINCIPLES

- **The model plans; operators prove.** The planner proposes a typed plan but never creates observational facts.
- **Hard constraints remain hard filters.** Distance, containment, dates and AOI are executed deterministically.
- **Expensive inference runs last.** Candidate reduction and quality gates happen before change detection.
- **Report observation support, not intent.** Tessera-X describes visible indicators; it does not infer actor or motive.
- **Every answer cites a release.** Scene, model, prompt, relation policy, index and code versions remain reproducible.

**Visual:** problem blocks on the left; the computation chain in the centre; five principles on the right.

---

## Slide 3 — Technical Approach

### CONTROL PLANE

1. **Rules planner first; optional local LLM second.** Both emit the same versioned `GeoQueryPlan` schema.
2. **Independent constraint checker** re-extracts dates, numbers, AOI and spatial language from the raw query.
3. **Capability validator** rejects unavailable feature layers, sensors or relations instead of approximating them silently.
4. **Cost gate + DAG compiler** predicts candidate cardinality and routes only the operators needed for the query.

### EXECUTION PLANE

| Stage | Technical path |
|---|---|
| **Ingest** | COG rasters + STAC items; footprints, timestamps, bands and quality metadata in PostgreSQL/PostGIS |
| **Semantic retrieval** | Frozen **LRSCLIP** patch/text embeddings; normalized prompt ensemble; **FAISS HNSW**, optional SQ8 |
| **Spatial grounding** | Versioned feature layers compiled to `ST_DWithin`, `ST_Intersects`, `ST_Contains` and related PostGIS predicates |
| **Temporal pairing** | Select sensor/resolution/season-compatible observations; construct a versioned multi-observation historical baseline |
| **Registration + QA** | AROSICS/equivalent local co-registration; reject excessive RMSE, cloud, nodata or insufficient overlap |
| **Change** | **ChangeFormerV6** binary change baseline; **UniChange** only after checkpoint, licence, hardware and benchmark gates pass |
| **Activity intelligence** | Source-linked `IndicatorObservation` records + versioned `ActivitySignature`; lifecycle and explained review priority |
| **Evidence** | Rank fusion, provenance object, analyst verdict, content-addressed artifacts and release manifest |

### PRODUCTION DEPLOYMENT TOPOLOGY

```text
Browser / REST API / batch CLI
              ↓
Ingress + OIDC/RBAC + request validation
              ↓
Stateless FastAPI control plane ───── PostgreSQL/PostGIS HA
              │                       plans, evidence, graph, audit
              ├── durable task broker ─ CPU geospatial worker pool
              │                        GPU embedding/change worker pool
              ├── Redis ─────────────── cache, locks, rate limits, progress
              ├── S3-compatible CAS ─── COGs, masks, baselines, manifests
              └── FAISS shard manager ─ immutable read replicas per release

OpenTelemetry → Prometheus/Grafana + centralized logs/traces
Kubernetes/Helm for HA production; Docker Compose for field/workstation use
```

**Runtime stack:** Python, GDAL, Rasterio, GeoPandas, Shapely, PyProj, AROSICS, PyTorch, LRSCLIP, FAISS, ChangeFormer, PostgreSQL/PostGIS, FastAPI, React, Kubernetes and Docker Compose.

### DATA AND RELEASE ARCHITECTURE

- Partition scene/patch/evidence tables by AOI and acquisition time; use spatial GiST indexes for deterministic relation filters.
- Store large rasters and derived products in content-addressed object storage; keep only metadata, hashes and URIs in PostGIS.
- Seal FAISS shards as immutable; new encoders create a new namespace instead of mutating historical vectors.
- A release manifest pins code SHA, container digest, model checksums, prompt/lexicon/relation policies, STAC snapshot, feature-layer versions and index shards.

**Visual:** make the control/execution architecture dominant. Show separate control, data, CPU and GPU planes.

---

## Slide 4 — Feasibility and Viability

### PRODUCTION FEASIBILITY

- Every mandatory stage has a reproducible baseline: STAC/COG, PostGIS, LRSCLIP, FAISS, AROSICS and ChangeFormer.
- The candidate cascade reduces work before GPU inference: **metadata/AOI → spatial filter → semantic top-K → temporal quality → change model**.
- Frozen embedding namespaces and append-only index shards keep old results reproducible after model upgrades.
- A compact deployment fits one offline workstation/server, while the same stateless API and worker boundaries scale to an on-premises cluster.
- Independent CPU and GPU queues prevent geospatial/IO work from occupying accelerators; admission control stops unrestricted archive-wide inference.
- Advanced models remain non-blocking: local LLM, UniChange, learned fusion, reranking and SAR activate only after separate release gates.
- Append-only artifacts, immutable shards and release-aware cache keys prevent model upgrades from rewriting historical evidence.

### PRODUCTION SERVICE TARGETS — VALIDATE BY LOAD/FAILOVER TEST

| SLI | Design target |
|---|---|
| **API availability** | **99.5% monthly** for query, evidence and audit services |
| **Warm semantic search** | **<3 s p95** after AOI/metadata filtering on the reference archive profile |
| **Job reliability** | **≥97%** of admitted jobs reach a terminal state without operator repair |
| **Recovery** | Database **RPO ≤15 min / RTO ≤4 h**; object artifacts versioned and checksummed |
| **Reproducibility** | **100%** of exported evidence packages cite a resolvable release manifest |
| **Safety** | **0 automated evidence claims** when mandatory registration/quality/provenance gates fail |

### EVALUATION CONTRACT — MEASURE EACH CLAIM SEPARATELY

| Capability | Metrics |
|---|---|
| **Retrieval** | nDCG@5/10, Precision@5/10, MRR |
| **Binary change** | Precision, recall, F1, IoU and false-alarm category |
| **Temporal localization** | Exact acquisition match, valid-acquisition error, temporal error and unusable-scene skip accuracy |
| **Planner safety** | Intent accuracy, slot exact match, numeric/constraint preservation and unsupported-capability detection |
| **System** | P50/P95/P99 latency, embedding throughput, candidate reduction, memory, index size and cache hit rate |

### RISKS AND MITIGATIONS

| Risk | Mitigation / fallback |
|---|---|
| Planner drops or alters a constraint | Independent raw-query checker; hard failure or clarification; deterministic rules fallback |
| Semantic false positives | PostGIS hard filters, negative/hard-negative benchmark and analyst review |
| False change from cloud/season/misalignment | Quality-valid baseline, AROSICS registration, cloud/nodata/overlap gates and false-alarm taxonomy |
| New model breaks historical reproducibility | New embedding namespace, versioned shards, release manifest and migration query mode |
| UniChange is unavailable or too heavy | Keep ChangeFormerV6 as the executable baseline; promote UniChange only after deployment gate |

### SECURITY AND OPERABILITY

- OIDC/PKCE for analysts, scoped service identities, least-privilege RBAC, mTLS between services and default-deny network policies.
- No-egress inference workers; signed offline images/model bundles; dependency hashes, SBOM and licence inventory per release.
- Raster/archive size limits, safe GDAL driver policy, parameterized SQL, geometry validation and immutable audit records.
- Per-operator traces and metrics: plan failures, candidate reduction, FAISS latency/recall, registration RMSE, change latency, GPU memory, queue depth and cache hit rate.
- Nightly base backups + continuous WAL archive, replicated object storage, tested restore procedure and last-known-good model/index rollback.

**Visual:** targets and evaluation on the left; risks, security and recovery controls on the right.

---

## Slide 5 — Impact, Operations and Benefits

### ONE QUERY, INSPECTABLE EVIDENCE

**Example:** “Show new construction near a river since 2022.”

Tessera-X returns:

- the interpreted `GeoQueryPlan`, explicit constraints, defaults and unresolved terms;
- ranked geolocated candidate patches with semantic scores;
- exact spatial-predicate evidence, named feature and geometry-layer version;
- registered before/after or baseline comparison with quality measurements;
- change mask, affected geometry/area and confidence adjusted by registration/observation quality;
- **last supported no-change**, **earliest supported change** and next confirming observation;
- lifecycle: `first_seen → expanding → persistent → contracting → no_longer_supported`;
- release/model/index/data provenance and the analyst’s final verdict.

### WHO BENEFITS

- **Earth-observation analysts:** meaning-based triage across large local archives.
- **Urban and infrastructure teams:** verify expansion, clearing, access routes and persistent activity.
- **Disaster/environment teams:** review flood, vegetation, land-use and recovery timelines using source observations.
- **Government and sensitive-data operators:** sovereign, air-gapped analysis with no external API dependency.
- **Audit/QA teams:** reproduce exactly why a result appeared and which evidence supported it.

### OPERATIONAL VALUE

- Reduces manual scene-by-scene search to a ranked, quality-gated investigation workflow.
- Saves compute by applying expensive change models only to reduced candidate sets.
- Separates **evidence confidence** from **review priority**, preventing urgency from being mistaken for certainty.
- Turns accepted findings into a sparse, provenance-backed knowledge layer for similar-site and similar-signature discovery.
- Preserves useful uncertainty: missing or unusable observations remain visible instead of being interpolated into false certainty.

### PRODUCTION WORKFLOWS

- **Continuous ingestion:** validate COG/STAC assets, compute patch embeddings, append to the open FAISS shard and seal/promote by release.
- **Interactive investigation:** return fast semantic/spatial candidates first; schedule registration and change inference as resumable background jobs.
- **Monitored AOIs:** apply a versioned watch policy when new observations arrive; update earliest support, lifecycle and affected-area trajectory.
- **Human review:** analysts compare raw observations, masks, predicates and confidence components before confirming/rejecting evidence.
- **Knowledge operations:** only confirmed sites/assessments generate sparse similarity edges; FAISS remains the similarity source of truth.
- **Release operations:** shadow new models/indexes, benchmark against a locked slice, promote atomically and retain reverse-migration access to old releases.

### IMPACT DASHBOARD

**candidate reduction · retrieval nDCG · false-alarm rate · change F1/IoU · valid-acquisition error · analyst acceptance rate · reproduction success · query latency**

**Visual:** use a four-panel evidence card: query plan, map candidate, change mask and timeline. Keep societal claims tied to these measurable outputs.

---

## Slide 6 — Research, Standards and Differentiation

### PRIMARY TECHNICAL REFERENCES

1. [Chen et al. — **LRSCLIP: A Vision-Language Foundation Model for Aligning Remote Sensing Image with Longer Text**](https://arxiv.org/abs/2503.19311) (2025).
2. [Bandara & Patel — **ChangeFormer: A Transformer-Based Siamese Network for Change Detection**](https://arxiv.org/abs/2201.01293), IGARSS 2022.
3. [**UniChange: Unifying Change Detection with Multimodal Large Language Model**](https://arxiv.org/abs/2511.02607) (2025); retained behind a deployment gate.
4. [Scheffler et al. — **AROSICS: Automated and Robust Open-Source Image Co-Registration for Multi-Sensor Satellite Data**](https://doi.org/10.3390/RS9070676), Remote Sensing 2017.
5. [Douze et al. — **The Faiss Library**](https://arxiv.org/abs/2401.08281) (2024) and [Johnson et al. — billion-scale similarity search with GPUs](https://arxiv.org/abs/1702.08734) (2017).
6. [Open Geospatial Consortium — **STAC 1.1.0** and **STAC API 1.0.0**](https://www.ogc.org/standards/stac/) community standards.
7. [PostgreSQL/PostGIS documentation](https://postgis.net/docs/) — geography distance, containment, intersection and spatial indexing.
8. Public/local evaluation packs — LEVIR-CD/DSIFN-style binary-change evaluation plus locally curated hard negatives and temporal labels.

### POSITIONING AGAINST COMMON APPROACHES

| Capability | Metadata catalog | CLIP/vector search only | End-to-end VLM | Tessera-X |
|---|:---:|:---:|:---:|:---:|
| Natural-language semantic search | No | Yes | Yes | **Yes** |
| Exact spatial relations | Basic filters | No | Unreliable | **PostGIS predicates** |
| Constraint-preserving plan | No | No | Opaque | **Typed + independently checked** |
| Quality-gated temporal change | No | No | Model-dependent | **Registered baseline + gates** |
| Earliest supported observation | No | No | Rarely | **Explicit temporal bracket** |
| Offline/air-gapped operation | Possible | Possible | Often difficult | **Baseline requirement** |
| Full evidence/release provenance | Metadata only | Index/model only | Limited | **Scene-to-verdict trace** |
| Abstains on unsupported query | Filter error | Similarity anyway | May hallucinate | **Fail/clarify explicitly** |
| HA, resumable jobs and rollback | Tool-specific | Rarely complete | Model-serving focus | **Production control + worker planes** |
| Air-gapped signed releases | Possible | Possible | Often difficult | **Designed in** |

### PROJECT RESOURCES

- **Production repository:** add URL
- **Architecture:** add public document URL
- **Demo video:** add URL
- **Evaluation report:** add URL after the locked benchmark is run

**Visual:** references on the left and comparison table on the right; QR codes only for repository/demo.

---

## Editing Rules for the Final Deck

- Replace every Slide 1 and project-link placeholder before submission.
- Present the full production design. Describe implementation status separately from system scope; do not label the solution itself as an MVP.
- Do not present the illustrative result JSON or example candidate counts as benchmark results.
- Say “earliest supported observation,” never “exact date the real-world event began.”
- Say “observed activity signature,” never infer an actor, motive or intent from imagery.
- Keep ChangeFormerV6 as the baseline; describe UniChange as optional until its checkpoint, licence, hardware and benchmark gates pass.
