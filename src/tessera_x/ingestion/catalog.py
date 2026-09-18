"""Atomic local ingestion bundles. PostGIS remains the production metadata store."""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from .cog import prepare_cog
from .inspection import inspect_scene
from .patches import extract_patches
from .record import SceneRecord, SourceMetadata, local_path
from .stac import scene_item


def _folder(root: str | Path, scene_id: str) -> Path:
    return local_path(root).resolve() / hashlib.sha256(scene_id.encode()).hexdigest()


def _metadata(record: dict) -> dict:
    return {key: record[key] for key in SourceMetadata.model_fields}


def load_scene(root: str | Path, scene_id: str) -> dict:
    """Read a bundle only after verifying its raster, metadata, patches and STAC."""
    folder = _folder(root, scene_id)
    try:
        bundle = json.loads((folder / "manifest.json").read_text())
        if bundle["schema_version"] != "tessera_ingestion_v1":
            raise ValueError("Unsupported catalog schema version")
        source_data = bundle["source"]
        source = SceneRecord.model_validate(
            {key: value for key, value in source_data.items() if key != "bbox"}
        )
        if source.model_dump(mode="json") != source_data:
            raise ValueError("Invalid original source record")
        scene = inspect_scene(folder / "image.tif", **_metadata(bundle["scene"]))
        preserved = (
            *SourceMetadata.model_fields,
            "width",
            "height",
            "count",
            "crs",
            "gsd",
            "transform",
            "footprint",
            "scales",
            "offsets",
            "nodata",
        )
        if any(getattr(source, field) != getattr(scene, field) for field in preserved):
            raise ValueError("Source provenance does not match prepared scene")
        if scene.scene_id != scene_id or scene.model_dump(mode="json") != bundle["scene"]:
            raise ValueError("Catalog scene integrity mismatch")
        patches = [p.model_dump(mode="json") for p in extract_patches(scene, bundle["patch_size"])]
        if patches != bundle["patches"]:
            raise ValueError("Catalog patch integrity mismatch")
        expected = scene_item(scene, cog_prepared=True)
        if json.loads((folder / "item.json").read_text()) != expected:
            raise ValueError("Catalog STAC integrity mismatch")
        return bundle
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Cannot read valid catalog bundle") from error


def ingest_scene(path: str | Path, root: str | Path, *, patch_size: int = 256, **metadata) -> dict:
    """Prepare a COG and publish a complete bundle; identical retries are idempotent.

    Source and prepared checksums are both retained. A changed source, metadata or
    patch policy under the same scene ID is a conflict, never an overwrite.
    """
    if type(patch_size) is not int or patch_size <= 0:
        raise ValueError("patch_size must be a positive integer")
    source = inspect_scene(path, **metadata)
    source_data = source.model_dump(mode="json")
    folder = _folder(root, source.scene_id)
    if folder.exists():
        existing = load_scene(root, source.scene_id)
        if existing["source"] != source_data or existing["patch_size"] != patch_size:
            raise ValueError("Scene ID conflict: source, metadata or patch policy changed")
        return existing
    folder.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ingest-", dir=folder.parent))
    try:
        scene = prepare_cog(path, staging / "image.tif", **metadata)
        patches = extract_patches(scene, patch_size)
        scene = scene.model_copy(update={"asset_path": str(folder / "image.tif")})
        bundle = {
            "schema_version": "tessera_ingestion_v1",
            "source": source_data,
            "scene": scene.model_dump(mode="json"),
            "patch_size": patch_size,
            "patches": [p.model_dump(mode="json") for p in patches],
            "cog_validation": "gdal_generated_and_pixel_verified_not_full_spec_validation",
        }
        for name, value in (
            ("manifest.json", bundle),
            ("item.json", scene_item(scene, cog_prepared=True)),
        ):
            (staging / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
        # A published bundle is nonempty: rename cannot replace another completed writer.
        try:
            os.rename(staging, folder)
        except OSError:
            if folder.exists():
                return ingest_scene(path, root, patch_size=patch_size, **metadata)
            raise
        return bundle
    finally:
        if staging.exists():
            shutil.rmtree(staging)
