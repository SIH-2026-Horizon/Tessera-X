"""Patch extraction contracts against real local GeoTIFFs."""

import importlib
import importlib.util
import json
from datetime import UTC, datetime

import numpy as np
import pytest
import rasterio
from pydantic import ValidationError
from rasterio import Affine
from rasterio.warp import transform as reproject
from rasterio.windows import Window

from tessera_x.ingestion import inspect_scene


@pytest.fixture
def patches_api():
    name = "tessera_x.ingestion.patches"
    assert importlib.util.find_spec(name) is not None, "Patch extraction module is missing"
    return importlib.import_module(name)


@pytest.fixture
def make_scene(tmp_path):
    def create(*, width=5, height=3, rotation=0, invalid=False):
        path = tmp_path / "scene.tif"
        affine = (
            Affine.translation(500000, 2000000) @ Affine.rotation(rotation) @ Affine.scale(10, -10)
        )
        data = np.arange(2 * width * height, dtype="float32").reshape(2, height, width)
        if invalid:
            data[0, 0, 0] = -9999
            data[1, 0, 1] = np.nan
            data[0, 1, 0] = np.inf
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=width,
            height=height,
            count=2,
            dtype="float32",
            crs="EPSG:32643",
            transform=affine,
            nodata=-9999,
        ) as dataset:
            dataset.write(data)
            dataset.scales = (0.1, 0.2)
            dataset.offsets = (-1.0, -2.0)
        scene = inspect_scene(
            path,
            scene_id="scene-1",
            platform="test-platform",
            sensor="test-sensor",
            acquisition_time="2026-01-01T00:00:00Z",
            ingestion_release="test-1",
            cloud_cover=0.9,
        )
        return scene, data, affine

    return create


@pytest.mark.parametrize("rotation", [0, 30])
def test_windows_pixels_and_geography_reconstruct(patches_api, make_scene, rotation):
    scene, data, affine = make_scene(rotation=rotation)
    patches = patches_api.extract_patches(scene, patch_size=2)
    assert [patch.window for patch in patches] == [
        (0, 0, 2, 2),
        (2, 0, 2, 2),
        (4, 0, 1, 2),
        (0, 2, 2, 1),
        (2, 2, 2, 1),
        (4, 2, 1, 1),
    ]
    reconstructed = np.empty_like(data)
    coverage = np.zeros((scene.height, scene.width), dtype=int)
    for patch in patches:
        col, row, width, height = patch.window
        assert all(type(value) is int for value in patch.window)
        actual = patches_api.read_patch(scene, patch)
        assert isinstance(actual, np.ma.MaskedArray)
        assert actual.shape == (scene.count, height, width)
        assert actual.dtype == data.dtype
        np.testing.assert_array_equal(actual, data[:, row : row + height, col : col + width])
        reconstructed[:, row : row + height, col : col + width] = actual
        coverage[row : row + height, col : col + width] += 1
        with rasterio.open(scene.asset_path) as dataset:
            window_affine = dataset.window_transform(Window(*patch.window))
        assert window_affine @ (0, 0) == pytest.approx(affine @ (col, row))
        ring = patch.footprint.coordinates[0]
        assert len(ring) == 85
        corners = [(col, row), (col + width, row), (col + width, row + height), (col, row + height)]
        for index, pixel in enumerate(corners):
            x, y = affine @ pixel
            lon, lat = reproject(scene.crs, "EPSG:4326", [x], [y])
            assert ring[21 * index] == pytest.approx((lon[0], lat[0]))
        x, y = affine @ (col + width / 21, row)
        lon, lat = reproject(scene.crs, "EPSG:4326", [x], [y])
        assert ring[1] == pytest.approx((lon[0], lat[0]))
        xs, ys = zip(*ring, strict=True)
        assert patch.bbox == (min(xs), min(ys), max(xs), max(ys))
        assert patch.scene_id == scene.scene_id
        assert patch.scene_checksum == scene.checksum
        assert patch.acquisition_time == datetime(2026, 1, 1, tzinfo=UTC)
        assert patch.sensor == scene.sensor
        assert patch.gsd == scene.gsd
    np.testing.assert_array_equal(reconstructed, data)
    np.testing.assert_array_equal(coverage, 1)


def test_default_size_and_clipped_edges(patches_api, make_scene):
    scene, _, _ = make_scene(width=259, height=257)
    assert [p.window for p in patches_api.extract_patches(scene)] == [
        (0, 0, 256, 256),
        (256, 0, 3, 256),
        (0, 256, 256, 1),
        (256, 256, 3, 1),
    ]


def test_quality_uses_all_band_finite_valid_pixels_not_clouds(patches_api, make_scene):
    scene, data, _ = make_scene(invalid=True)
    patches = patches_api.extract_patches(scene, 2)
    assert patches[0].quality_score == 0.25
    assert all(p.quality_score == 1 for p in patches[1:])
    assert all(p.quality_method == "valid_fraction_v1" for p in patches)
    result = patches_api.read_patch(scene, patches[0])
    expected_mask = (data[:, :2, :2] == -9999) | ~np.isfinite(data[:, :2, :2])
    np.testing.assert_array_equal(np.ma.getmaskarray(result), expected_mask)
    np.testing.assert_array_equal(result.data, data[:, :2, :2])


def test_all_nodata_quality_is_zero(patches_api, make_scene):
    scene, _, _ = make_scene()
    with rasterio.open(scene.asset_path, "r+") as dataset:
        dataset.write(np.full((2, 3, 5), -9999, dtype="float32"))
    scene = reinspect(scene)
    assert all(p.quality_score == 0 for p in patches_api.extract_patches(scene, 2))


def reinspect(scene):
    return inspect_scene(
        scene.asset_path,
        **{
            key: getattr(scene, key)
            for key in (
                "scene_id",
                "platform",
                "sensor",
                "acquisition_time",
                "ingestion_release",
                "cloud_cover",
            )
        },
    )


def test_ids_are_stable_bound_to_scene_and_window_path_independent(
    patches_api, make_scene, tmp_path
):
    scene, _, _ = make_scene()
    patches = patches_api.extract_patches(scene, 2)
    assert patches == patches_api.extract_patches(scene, 2)
    assert len({p.patch_id for p in patches}) == len(patches)
    moved = tmp_path / "copy.tif"
    moved.write_bytes((tmp_path / "scene.tif").read_bytes())
    relocated = scene.model_copy(update={"asset_path": str(moved)})
    assert patches == patches_api.extract_patches(relocated, 2)
    np.testing.assert_array_equal(
        patches_api.read_patch(relocated, patches[0]), patches_api.read_patch(scene, patches[0])
    )
    renamed = scene.model_copy(update={"scene_id": "scene-2"})
    assert patches_api.extract_patches(renamed, 2)[0].patch_id != patches[0].patch_id
    with rasterio.open(scene.asset_path, "r+") as dataset:
        dataset.write(np.full((2, 3, 5), 100, dtype="float32"))
    changed = reinspect(scene)
    assert patches_api.extract_patches(changed, 2)[0].patch_id != patches[0].patch_id


@pytest.mark.parametrize("size", [True, False, 2.0, "2", 0, -1, None])
def test_invalid_patch_sizes(patches_api, make_scene, size):
    scene, _, _ = make_scene()
    with pytest.raises(ValueError, match="patch_size"):
        patches_api.extract_patches(scene, size)


@pytest.mark.parametrize("operation", ["extract", "read"])
def test_stale_source_rejected(patches_api, make_scene, operation):
    scene, _, _ = make_scene()
    patch = patches_api.extract_patches(scene, 2)[0]
    with rasterio.open(scene.asset_path, "r+") as dataset:
        dataset.write(np.full((2, 3, 5), 999, dtype="float32"))
    with pytest.raises(ValueError, match="match"):
        if operation == "extract":
            patches_api.extract_patches(scene, 2)
        else:
            patches_api.read_patch(scene, patch)


@pytest.mark.parametrize(
    "field,value",
    [
        ("gsd", 20.0),
        ("width", 10),
        ("scales", (1.0, 1.0)),
        ("checksum", "0" * 64),
        ("transform", (10.0, 0.0, 500001.0, 0.0, -10.0, 2000000.0)),
    ],
)
def test_altered_scene_record_rejected(patches_api, make_scene, field, value):
    scene, _, _ = make_scene()
    patch = patches_api.extract_patches(scene, 2)[0]
    altered = scene.model_copy(update={field: value})
    with pytest.raises(ValueError, match="match"):
        patches_api.extract_patches(altered, 2)
    with pytest.raises(ValueError, match="match"):
        patches_api.read_patch(altered, patch)


@pytest.mark.parametrize(
    "field,value",
    [
        ("window", (1, 0, 2, 2)),
        ("window", (0, 0, 99, 99)),
        ("window", (-1, 0, 2, 2)),
        ("window", (True, 0, 2, 2)),
        ("window", (0.0, 0, 2, 2)),
        ("patch_id", "f" * 64),
        ("scene_id", "other"),
        ("scene_checksum", "0" * 64),
        ("sensor", "other"),
        ("sensor", " test-sensor "),
        ("gsd", 20.0),
        ("quality_score", 0.5),
        ("quality_method", "cloud_score"),
        ("acquisition_time", datetime(2025, 1, 1, tzinfo=UTC)),
    ],
)
def test_altered_patch_rejected_even_with_unvalidated_copy(patches_api, make_scene, field, value):
    scene, _, _ = make_scene()
    patch = patches_api.extract_patches(scene, 2)[0]
    with pytest.raises(ValueError):
        patches_api.read_patch(scene, patch.model_copy(update={field: value}))


def test_wrong_scene_and_altered_footprint_rejected(patches_api, make_scene):
    scene, _, _ = make_scene()
    patches = patches_api.extract_patches(scene, 2)
    with pytest.raises(ValueError):
        patches_api.read_patch(scene.model_copy(update={"scene_id": "other"}), patches[0])
    with pytest.raises(ValueError):
        patches_api.read_patch(
            scene, patches[0].model_copy(update={"footprint": patches[1].footprint})
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("window", (0, 0, 0, 2)),
        ("window", (0, 0, 2.0, 2)),
        ("window", (False, 0, 2, 2)),
        ("window", (0, 0, -1, 2)),
        ("quality_score", True),
        ("quality_score", "0.5"),
        ("quality_score", float("nan")),
        ("quality_score", 1.1),
        ("gsd", "10"),
        ("scene_id", 1),
        ("sensor", b"sensor"),
        ("scene_checksum", "invalid"),
        ("patch_id", "invalid"),
        ("acquisition_time", datetime(2026, 1, 1)),
        ("unexpected", True),
    ],
)
def test_strict_patch_record(patches_api, make_scene, field, value):
    scene, _, _ = make_scene()
    patch = patches_api.extract_patches(scene, 2)[0]
    data = patch.model_dump(exclude={"bbox"})
    with pytest.raises(ValidationError):
        patches_api.PatchRecord.model_validate({**data, field: value})


def test_immutable_serializable_and_no_disk_writes(patches_api, make_scene, tmp_path):
    scene, _, _ = make_scene()
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    patch = patches_api.extract_patches(scene, 2)[0]
    patches_api.read_patch(scene, patch)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    with pytest.raises(ValidationError):
        patch.quality_score = 0.0
    with pytest.raises(ValidationError):
        patch.footprint.type = "Point"
    json.dumps(patch.model_dump(mode="json"), allow_nan=False)
    restored = patches_api.PatchRecord.model_validate_json(patch.model_dump_json(exclude={"bbox"}))
    assert restored == patch
    np.testing.assert_array_equal(
        patches_api.read_patch(scene, restored), patches_api.read_patch(scene, patch)
    )
