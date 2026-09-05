# Tessera-X — SIH PPT Content

Paste-ready content for a six-slide technical SIH submission describing the proposed production-grade system: offline data ingestion, semantic search, temporal intelligence, distributed execution, security, observability and reproducible release operations.

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

*Production-grade, offline semantic Earth-observation intelligence*

**One-line pitch:** A production platform for continuously ingesting satellite archives and converting natural-language investigations into geospatially grounded, temporally verified and source-linked evidence—fully offline.

**Production scope:** Continuous archive ingestion · multi-user investigations · distributed CPU/GPU execution · governed AI releases · HA/DR · signed air-gapped deployment

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

### COMPLETE PRODUCTION SCOPE

- **Archive-scale data plane:** continuous COG/STAC ingestion, spatially partitioned metadata, content-addressed artifacts and append-only FAISS shards.
- **Operational control plane:** concurrent analyst sessions, quotas, admission-controlled background jobs, cancellation, resumable stages and priority queues.
- **Production intelligence:** semantic retrieval, deterministic relations, historical baselines, binary/semantic change, lifecycle tracking and verified similar-pattern discovery.
- **Governed human workflow:** explained confidence and priority, analyst verdicts, immutable audit events and contamination-safe evaluation/training channels.
- **Sovereign operations:** on-premises HA cluster, no-egress inference, signed offline releases, monitoring, backup, restore and model/index rollback.

**Visual:** problem blocks on the left; computation chain in the centre; “Complete Production Scope” on the right with data, compute, governance, security and reliability icons.

---

## Slide 3 — Technical Approach

### CONTROL PLANE

1. **Rules planner first; optional local LLM second.** Both emit the same versioned `GeoQueryPlan` schema.
2. **Independent constraint checker** re-extracts dates, numbers, AOI and spatial language from the raw query.
3. **Capability validator** rejects unavailable feature layers, sensors or relations instead of approximating them silently.
4. **Cost gate + DAG compiler** predicts candidate cardinality and routes only the operators needed for the query.

### TYPED QUERY CONTRACT

`GeoQueryPlan` records intent, semantic targets, positive/negative prompts, AOI, temporal interval, spatial relations, sensors, quality filters and compute budget. It also preserves which constraints were explicit, which defaults were applied, which terms were ignored and which capabilities remain unresolved.

The independent checker compares raw-language dates, distances, place names and relations with the compiled plan. A mismatch blocks execution or requests clarification; the planner cannot approve its own interpretation.

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

### EVIDENCE AND CONFIDENCE CONTRACT

- `EffectiveConfidence = ModelConfidence × RegistrationQuality × ObservationQuality`; priority remains a separate, explained policy score.
- Each result links the patch/geometry, spatial predicate, source observations, historical-baseline members, change mask, indicator observations and analyst verdict.
- Earliest-change output is a defensible observation bracket: **last supported no-change → earliest supported change → next confirming observation**, with unusable scenes listed explicitly.
- Similar-pattern discovery is two-stage: FAISS retrieves top-K signatures, then a verifier checks indicators, spatial relations, timing, lifecycle compatibility and evidence quality.

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

**Production-readiness statement:** Tessera-X is scoped as a governed Earth-observation intelligence service from continuous ingestion to evidence publication—not only a semantic-search interface. Data, compute, analyst review, provenance, security, observability and recovery share one release contract.

### PRODUCTION ASSURANCE

| Area | Production capability |
|---|---|
| **Availability** | Redundant API/data services, durable job queues and visible degraded modes for unavailable dependencies |
| **Search performance** | Partition-pruned metadata/spatial filtering, immutable FAISS read replicas and cached query plans |
| **Job reliability** | Idempotent operators, resumable stages, bounded retries, cancellation and dead-letter handling |
| **Recovery** | Database point-in-time recovery, replicated/versioned objects and tested model/index rollback |
| **Reproducibility** | Every evidence export resolves a signed release manifest and checksummed source artifacts |
| **Safety** | Evidence publication is blocked when mandatory registration, quality or provenance gates fail |

### EVALUATION CONTRACT — MEASURE EACH CLAIM SEPARATELY

| Capability | Metrics |
|---|---|
| **Retrieval** | nDCG@5/10, Precision@5/10, MRR |
| **Binary change** | Precision, recall, F1, IoU and false-alarm category |
| **Temporal localization** | Exact acquisition match, valid-acquisition error, temporal error and unusable-scene skip accuracy |
| **Planner safety** | Intent accuracy, slot exact match, numeric/constraint preservation and unsupported-capability detection |
| **System** | P50/P95/P99 latency, embedding throughput, candidate reduction, memory, index size and cache hit rate |

### FALSE-ALARM CONTROL

Cloud, cloud shadow, seasonal vegetation, phenology, parallax, resampling seams, sensor differences and registration error are stored as explicit false-alarm categories. Quality gates can reject the pair before inference, reduce confidence after inference or route the result to mandatory analyst review.

### REQUIREMENT-TO-EVIDENCE TRACEABILITY

| Problem / requirement | System response | Evidence and gate | User-visible outcome |
|---|---|---|---|
| Metadata search misses visual meaning | LRSCLIP embeddings + FAISS retrieval | Blinded hard-negative retrieval set; nDCG, precision, MRR and recall | Ranked, geolocated semantic candidates |
| Similarity cannot prove “near/inside” | Typed relation + versioned PostGIS predicate | Known-answer predicate fixtures and constraint-preservation tests | Named geometry, relation and distance evidence |
| Cloud, season or misalignment looks like change | Quality-valid baseline + AROSICS + false-alarm policy | Registration/quality gates and category-wise F1/IoU/false alarms | Registered comparison and qualified change mask |
| Pairwise comparison cannot say when | Multi-observation temporal localizer | Exact/valid-acquisition error and unusable-scene skip accuracy | Last no-change → earliest supported change → confirmation |
| Language models can alter constraints | Independent checker + capability validator | Numeric/slot preservation and unsafe-plan rejection | Executable plan, defaults and unresolved terms |
| Results drift after data/model upgrades | Immutable index/artifact namespaces + signed release | Fixed-release replay and rollback tests | Reproducible scene-to-verdict evidence package |

This matrix connects every stated limitation to its deterministic or learned operator, its independent validation measure and the evidence an analyst ultimately receives.

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

**Visual:** production assurance and evaluation on the left; risks, security and recovery controls on the right.

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

The explain trace also reports how many candidates survived each stage—metadata, semantic, spatial, temporal and quality—so an analyst can see exactly why a result was included or excluded.

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

### END-TO-END PRODUCTION LIFECYCLE

**Ingest → validate → embed/index → plan → retrieve/ground → register → detect/localize → review → publish → monitor → reproduce**

### IMPACT DASHBOARD

**candidate reduction · retrieval nDCG · false-alarm rate · change F1/IoU · valid-acquisition error · analyst acceptance rate · reproduction success · query latency**

**Visual:** use a four-panel evidence card: query plan, map candidate, change mask and timeline. Keep societal claims tied to these measurable outputs.

---

## Slide 6 — Research, Standards and Differentiation

### PRIMARY TECHNICAL REFERENCES

1. [Chen et al. — **LRSCLIP: Aligning Remote-Sensing Images with Longer Text**](https://arxiv.org/abs/2503.19311), 2025.
2. [Liu et al. — **RemoteCLIP: A Vision-Language Foundation Model for Remote Sensing**](https://doi.org/10.1109/TGRS.2024.3390838), IEEE TGRS 2024.
3. [Zhang et al. — **RS5M and GeoRSCLIP**](https://arxiv.org/abs/2306.11300), 2023.
4. [Bandara & Patel — **ChangeFormer**](https://arxiv.org/abs/2201.01293), IGARSS 2022.
5. [**UniChange: Unifying Change Detection with Multimodal Large Language Models**](https://arxiv.org/abs/2511.02607), 2025.
6. [Scheffler et al. — **AROSICS**](https://doi.org/10.3390/RS9070676), Remote Sensing 2017.
7. [Douze et al. — **The Faiss Library**](https://arxiv.org/abs/2401.08281) and [Johnson et al. — billion-scale GPU similarity search](https://arxiv.org/abs/1702.08734).
8. [Malkov & Yashunin — **Hierarchical Navigable Small World graphs**](https://arxiv.org/abs/1603.09320), IEEE TPAMI 2020.
9. [Open Geospatial Consortium — **STAC 1.1.0 / STAC API 1.0.0**](https://www.ogc.org/standards/stac/).
10. [OGC — **Cloud Optimized GeoTIFF 1.0**](https://www.ogc.org/standards/ogc-cloud-optimized-geotiff/) and [PostGIS spatial operators](https://postgis.net/docs/).
11. [W3C — **PROV-O Provenance Ontology**](https://www.w3.org/TR/prov-o/) for interoperable evidence lineage.
12. [Chen & Shi — **LEVIR-CD**](https://justchenhao.github.io/LEVIR/) building-change benchmark, with local hard-negative and temporal evaluation packs.
13. [Google Earth Engine documentation](https://developers.google.com/earth-engine/guides/getstarted) — cloud-scale geospatial analysis and image collections.
14. [Copernicus Data Space Browser](https://documentation.dataspace.copernicus.eu/Applications/Browser.html) — catalog search, visualization, comparison and time-series tools.
15. [Microsoft Planetary Computer STAC API](https://planetarycomputer.microsoft.com/docs/reference/stac/) — cloud-hosted STAC catalog and asset discovery.

### BENCHMARK AND VALIDATION DESIGN

| Benchmark layer | Dataset/protocol | Reported measures | What it proves |
|---|---|---|---|
| **Semantic retrieval** | RSITMD/RSICD-style public sets plus a blinded local query–candidate pool with hard negatives | nDCG@5/10, Precision@5/10, MRR, recall and latency | Natural-language relevance beyond metadata search |
| **Spatial grounding** | Versioned synthetic and real feature layers with known distance/intersection/containment answers | Predicate accuracy, distance error, constraint preservation | “Near/inside/adjacent” is geometrically correct |
| **Binary change** | LEVIR-CD/DSIFN-style benchmarks plus local cloud, season, shadow and registration negatives | Precision, recall, F1, IoU and false-alarm breakdown | Change masks remain useful outside clean benchmark pairs |
| **Temporal localization** | Multi-observation AOI timelines with unusable scenes and independently labelled change brackets | Exact acquisition match, valid-acquisition error, temporal error, skip accuracy | Earliest-supported observation is defensible |
| **Planner safety** | Gold natural-language queries containing dates, quantities, AOIs, negation and unsupported relations | Intent/slot accuracy, numeric preservation, ignored-term recall, unsafe-plan rejection | The language layer preserves analyst constraints |
| **Activity intelligence** | Curated multi-indicator timelines and verified similar-site pools | Indicator/signature precision–recall, lifecycle agreement, area error, verified-signature nDCG | Correlated activity claims and analogues are evidence-backed |
| **Production replay** | Fixed release replay plus worker loss, stale cache, missing shard and read-only storage tests | Reproduction success, stage recovery, cache isolation, latency and resource use | Operational reliability and historical reproducibility |

### EXISTING SOLUTIONS AND TESSERA-X ADVANTAGE

| Existing solution/approach | Primary strength | Remaining gap for this workflow | Tessera-X advantage |
|---|---|---|---|
| **Copernicus Data Space Browser** | Strong catalog search, visualization, download, comparison and time-series exploration | Primarily interactive product discovery; does not compile free-form investigations into versioned evidence plans | Natural-language plan → deterministic grounding → change/timeline evidence → analyst verdict |
| **Microsoft Planetary Computer / STAC APIs** | Standards-based discovery and cloud access to large geospatial collections | Catalog/API layer; semantic retrieval, spatial-relation proof and evidence lifecycle must be assembled separately | Adds offline semantic indexing, typed planning, temporal verification and release-linked evidence |
| **Google Earth Engine** | Large cloud catalog and scalable code-driven geospatial computation | Cloud/service dependency; investigation logic, model lineage and evidence packaging are application responsibilities | Air-gapped execution with governed models, immutable artifacts and a reproducible scene-to-verdict chain |
| **RemoteCLIP/GeoRSCLIP + FAISS** | Strong open-vocabulary remote-sensing retrieval | Similarity cannot prove exact spatial relations or whether/when change occurred | Uses embeddings only for candidate generation; PostGIS, registration, change models and temporal logic verify the claim |
| **AROSICS + ChangeFormer pipelines** | Capable registration and binary-change components | Pair selection, language interpretation, lifecycle reasoning, provenance and analyst workflow are outside the models | Integrates them behind quality gates with historical baselines, earliest-support logic and human review |
| **End-to-end multimodal VLM** | Flexible instruction-driven visual reasoning | May alter constraints or produce ungrounded explanations; difficult to audit and reproduce | LLM output is a checked plan; source observations and deterministic operators remain authoritative |

### WHY TESSERA-X IS STRONGER AS A SYSTEM

- **Semantics plus geometry:** embeddings find visual meaning; PostGIS proves spatial relations using named, versioned features.
- **Search plus verification:** candidates pass observation-quality, registration, baseline and change gates before becoming evidence.
- **Time is explicit:** the system reports last no-change, earliest supported change, confirmation and lifecycle—never an unsupported exact event time.
- **Evidence survives model upgrades:** immutable index namespaces, content hashes and signed release manifests reproduce historical results.
- **Offline operational ownership:** data, models, indexes, policies, logs and analyst decisions remain inside the deployment boundary.

### CAPABILITY SUMMARY

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

### TECHNICAL EVIDENCE PACK

- [System architecture](ARCHITECTURE.md) — invariants, typed plans, execution layers, evidence graph and release model.
- [Production implementation plan](PLAN.md) — workstreams, qualification gates, test matrix and release hardening.
- [Activity-intelligence decision record](ADR-001-ACTIVITY-INTELLIGENCE.md) — observation, signature, lifecycle and analyst-verdict semantics.

**Visual:** use a two-column reference block across the top; place the benchmark and existing-solution comparisons below it. If space is tight, move the detailed benchmark table to an appendix slide and retain its seven benchmark-layer labels on Slide 6.

---

## Editing Rules for the Final Deck

- Copy the official Problem Statement ID/title, theme and registered team metadata verbatim into Slide 1 before submission; do not infer them from the solution description.
- The project repository is private. Add its URL or QR to the submitted deck only after public visibility or judge access has been verified; apply the same rule to any demo or evidence URL.
- Present the full production design and end-to-end operational lifecycle.
- Keep the phrases **“production platform,” “continuous ingestion,” “distributed execution,” “governed evidence”** and **“signed air-gapped release”** visible in the actual slides—not only in speaker notes.
- Do not present the illustrative result JSON or example candidate counts as benchmark results.
- Say “earliest supported observation,” never “exact date the real-world event began.”
- Say “observed activity signature,” never infer an actor, motive or intent from imagery.
- Keep ChangeFormerV6 as the baseline; describe UniChange as optional until its checkpoint, licence, hardware and benchmark gates pass.
