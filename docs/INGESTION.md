# Phase 1 — Geospatial foundation

## Implemented

- Strict explicit source metadata and local GeoTIFF inspection, including complete base-resolution decoding and SHA-256.
- GDAL COG preparation with decoded pixel/mask, grid and calibration comparison; atomic no-overwrite publication.
- Deterministic source-linked patches, including clipped edges and rotated grids, with densified WGS84 footprints.
- Patch reconstruction that checks source identity and recomputes patch metadata.
- Atomic local bundles containing prepared raster, original source metadata/checksum, STAC Item and patch manifest.
- Idempotent ingestion; conflicting source, metadata or patch-size policy is rejected.
- PostGIS schema and transactional adapter with Polygon/4326 geometries, GiST indexes, foreign keys, window constraints and full JSON payloads.

## Local commands

Install the locked environment with `uv sync --locked`. Run from the repository root:

```bash
uv run python -m tessera_x.ingestion inspect /path/to/image.tif \
  --scene-id example --platform local --sensor optical \
  --acquisition-time 2024-01-01T00:00:00Z --ingestion-release foundation-v1

uv run python -m tessera_x.ingestion ingest /path/to/image.tif \
  --store data/archive --patch-size 256 \
  --scene-id example --platform local --sensor optical \
  --acquisition-time 2024-01-01T00:00:00Z --ingestion-release foundation-v1

uv run python -m tessera_x.ingestion show example --store data/archive
```

These are example timestamps, not metadata for the staged Sentinel assets. Supply actual timezone-aware acquisition metadata. `--cloud-cover` is optional and is a fraction from 0 to 1; STAC converts it to percent. Unknown cloud cover stays unknown.

`prepare-cog SOURCE DESTINATION` accepts the same source metadata flags and creates only a prepared raster. All commands emit JSON; expected input/storage errors return exit code 2 with a JSON error on stderr.

### Bundle layout

```text
data/archive/<sha256-of-scene-id>/
  image.tif
  manifest.json
  item.json
```

Scene IDs are hashed for directory naming rather than used as paths. `manifest.json` retains separate `source` and prepared `scene` records. Patch checksums refer to the prepared scene. Files remain local; no network schemas, imagery or models are fetched. The manifest stores absolute paths, so bundles are currently tied to their store location. `show` verifies the prepared raster, regenerated patch records and STAC Item; it validates original-source metadata consistency but does not require the original input file to remain present or re-hash it. Original source path/checksum remain recorded provenance, not cryptographically authenticated history; protect manifests against unauthorized edits.

### Patch API

```python
from tessera_x.ingestion import inspect_scene
from tessera_x.ingestion.patches import extract_patches, read_patch

scene = inspect_scene(path, **metadata)
patches = extract_patches(scene, patch_size=256)
pixels = read_patch(scene, patches[0])
```

`window` is `(column_offset, row_offset, width, height)`; `acquisition_time` preserves the source timestamp. Returned pixels are masked arrays in original band order and dtype, without radiometric calibration. `quality_score` under `valid_fraction_v1` is the fraction valid and finite in every band, **not cloud-free fraction or scientific suitability**.

### PostGIS

Install psycopg 3 separately in the operator environment. No database connection is opened automatically. Supply a caller-owned psycopg connection to:

```python
from tessera_x.ingestion.postgis import initialize_database, register_scene

initialize_database(connection)
inserted = register_scene(connection, scene, patches)
```

Bootstrap requires PostGIS and suitable CREATE privileges. Tables are `tessera_scenes` and `tessera_patches` in the caller's trusted `search_path`. Bootstrap is additive, not an incompatible-schema migration tool. `register_scene` returns `True` for insertion, `False` for an identical retry, and raises `SceneConflictError` if any scene or complete patch payload differs. Use trusted extractor output: database validation is not an independent recomputation of quality or geometry from raster pixels.

Local publication and PostGIS registration are separate transactions. If database registration fails, the verified local bundle remains available for a retry; there is no distributed transaction.

## Verification

```bash
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
```

Real database tests in `tests/integration/test_postgis.py` additionally require psycopg and `TESSERA_X_TEST_DB_URL` pointing at a disposable PostGIS database. They isolate test tables in a temporary schema and roll back. Without that setting the database tests skip; SQL-contract unit tests are not a substitute for database integration.

## Gate status and limits

This implements the bulk of Phase 1, **not a declaration that G0/G1 passed for the demo archive**.

- Scope freeze, verified demo acquisition timestamps, model/license inventory and hardware acceptance remain unresolved. The staged `data/demo/source_manifest.json` explicitly records unknown timestamps and incomplete requested-AOI coverage; no timestamps were invented and no demo assets were changed.
- One local GeoTIFF per canonical record. Sentinel multi-asset assembly, band semantics and SCL resampling are not implemented.
- Only EPSG projected metre CRSs with square orthogonal grids; geographic grids and antimeridian products are rejected.
- COG preparation is GDAL-generated plus decoded comparison, not independent full COG specification certification.
- STAC Items are emitted, but there is no STAC HTTP service or external-schema validation.
- No immutable source snapshot during inspection; callers must prevent concurrent input mutation. Atomic publication does not guarantee power-loss durability. COG publication requires hard-link support.
- Patch extraction returns a list and re-inspects the raster before extraction/reconstruction. This favors integrity over high-volume performance; no archive-scale throughput claim is made.
- Cloud/shadow quality, registration, embeddings and semantic retrieval belong to later phases.
