import numpy as np
import pytest
import rasterio
from rasterio import Affine

from tessera_x.ingestion import inspect_scene


def test_stac_preserves_geometry_time_and_local_asset(tmp_path):
    from tessera_x.ingestion.stac import scene_item

    path = tmp_path / "source.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="uint16",
        crs="EPSG:32644",
        transform=Affine(10, 0, 500000, 0, -10, 1400000),
    ) as dst:
        dst.write(np.ones((1, 4, 4), dtype="uint16"))
    scene = inspect_scene(
        path,
        scene_id="example",
        platform="sentinel-2b",
        sensor="MSI",
        acquisition_time="2024-01-01T00:00:00Z",
        ingestion_release="test",
        cloud_cover=0.25,
    )
    item = scene_item(scene)
    assert item["stac_version"] == "1.0.0"
    assert item["type"] == "Feature"
    assert item["id"] == scene.scene_id
    assert item["geometry"] == scene.footprint.model_dump(mode="json")
    assert item["bbox"] == list(scene.bbox)
    assert item["properties"]["datetime"] == "2024-01-01T00:00:00Z"
    assert item["properties"]["eo:cloud_cover"] == 25
    assert item["properties"]["proj:epsg"] == 32644
    assert item["properties"]["proj:shape"] == [4, 4]
    assert item["assets"]["image"]["href"] == path.as_uri()
    assert item["assets"]["image"]["tessera:sha256"] == scene.checksum
    assert "cloud-optimized" not in item["assets"]["image"]["type"]
    unknown = scene.model_copy(update={"cloud_cover": None})
    assert "eo:cloud_cover" not in scene_item(unknown)["properties"]
    with pytest.raises(ValueError):
        scene_item(scene, cog_prepared=True)
