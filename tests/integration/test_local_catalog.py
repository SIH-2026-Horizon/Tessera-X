import json

import numpy as np
import pytest
import rasterio
from rasterio import Affine


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=17,
        height=19,
        count=1,
        dtype="uint16",
        crs="EPSG:32644",
        transform=Affine(10, 0, 500000, 0, -10, 1400000),
    ) as dst:
        dst.write(np.arange(323, dtype="uint16").reshape(1, 19, 17))
    return path


@pytest.fixture
def metadata():
    return {
        "scene_id": "scene/../one",
        "platform": "sentinel-2b",
        "sensor": "MSI",
        "acquisition_time": "2024-01-01T00:00:00Z",
        "ingestion_release": "test",
    }


def test_ingest_roundtrip_idempotence_and_stac(tmp_path, source, metadata):
    from tessera_x.ingestion.catalog import ingest_scene, load_scene

    root = tmp_path / "archive"
    before = source.read_bytes()
    result = ingest_scene(source, root, patch_size=8, **metadata)
    assert len(result["patches"]) == 9
    assert result["source"]["asset_path"] == str(source)
    assert result["scene"]["scene_id"] == metadata["scene_id"]
    assert result["scene"]["cog_layout_hint"]
    assert result["source"]["checksum"] != result["scene"]["checksum"]
    assert source.read_bytes() == before
    assert load_scene(root, metadata["scene_id"]) == result
    assert ingest_scene(source, root, patch_size=8, **metadata) == result
    assert len(list(root.iterdir())) == 1
    folder = next(root.iterdir())
    item = json.loads((folder / "item.json").read_text())
    assert item["geometry"] == result["scene"]["footprint"]
    assert item["assets"]["image"]["href"].endswith("/image.tif")
    with pytest.raises(ValueError, match="conflict"):
        ingest_scene(source, root, patch_size=16, **metadata)
    with pytest.raises(ValueError, match="conflict"):
        ingest_scene(source, root, patch_size=8, **{**metadata, "sensor": "other"})


@pytest.mark.parametrize("field", ["schema_version", "source"])
def test_catalog_rejects_invalid_provenance(tmp_path, source, metadata, field):
    from tessera_x.ingestion.catalog import ingest_scene, load_scene

    root = tmp_path / "archive"
    ingest_scene(source, root, patch_size=8, **metadata)
    manifest = next(root.iterdir()) / "manifest.json"
    bundle = json.loads(manifest.read_text())
    if field == "schema_version":
        bundle[field] = "unknown-v2"
    else:
        bundle[field]["sensor"] = "different"
    manifest.write_text(json.dumps(bundle))
    with pytest.raises(ValueError):
        load_scene(root, metadata["scene_id"])


def test_catalog_detects_corrupt_artifact(tmp_path, source, metadata):
    from tessera_x.ingestion.catalog import ingest_scene, load_scene

    root = tmp_path / "archive"
    ingest_scene(source, root, patch_size=8, **metadata)
    (next(root.iterdir()) / "image.tif").write_bytes(b"corrupt")
    with pytest.raises(ValueError):
        load_scene(root, metadata["scene_id"])


def test_extracted_patch_matches_postgis_contract(source, metadata):
    from tessera_x.ingestion import inspect_scene
    from tessera_x.ingestion.patches import extract_patches
    from tessera_x.ingestion.postgis import _patch_params

    scene = inspect_scene(source, **metadata)
    patch = extract_patches(scene, 8)[0]
    params = _patch_params(patch.model_dump(mode="json"), scene)
    assert params["timestamp"] == scene.acquisition_time
    assert (
        params["pixel_col"],
        params["pixel_row"],
        params["pixel_width"],
        params["pixel_height"],
    ) == patch.window


def test_bad_ingest_does_not_publish(tmp_path, source, metadata):
    from tessera_x.ingestion.catalog import ingest_scene

    root = tmp_path / "archive"
    with pytest.raises(ValueError):
        ingest_scene(source, root, patch_size=0, **metadata)
    assert not root.exists() or not list(root.iterdir())
