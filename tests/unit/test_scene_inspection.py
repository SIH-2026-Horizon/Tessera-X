import hashlib
import json
import subprocess
import sys
from datetime import UTC, date, datetime

import numpy as np
import pytest
import rasterio
from pydantic import ValidationError
from rasterio import Affine
from rasterio.errors import NotGeoreferencedWarning
from rasterio.warp import transform as reproject

import tessera_x.ingestion as ingestion


@pytest.fixture
def metadata():
    return {
        "scene_id": "scene-1",
        "platform": "local-platform",
        "sensor": "local-sensor",
        "acquisition_time": "2026-01-02T03:04:05+05:30",
        "ingestion_release": "inspection-1",
    }


@pytest.fixture
def raster(tmp_path):
    def create(**overrides):
        path = tmp_path / "asset.tif"
        profile = {
            "driver": "GTiff",
            "width": 32,
            "height": 48,
            "count": 2,
            "dtype": "float32",
            "crs": "EPSG:32643",
            "transform": Affine(10, 0, 500000, 0, -10, 2000000),
            "nodata": float("nan"),
            "tiled": True,
            "blockxsize": 16,
            "blockysize": 16,
        }
        profile.update(overrides)
        with rasterio.open(path, "w", **profile) as dataset:
            dataset.write(np.ones((profile["count"], 48, 32), dtype="float32"))
            dataset.scales = (0.1,) * profile["count"]
            dataset.offsets = (-1.0,) * profile["count"]
        return path

    return create


def test_public_api():
    assert callable(getattr(ingestion, "inspect_scene", None))
    assert hasattr(ingestion, "SceneRecord")
    assert hasattr(ingestion, "InspectionError")


def test_inspection_record(raster, metadata):
    path = raster()
    before = path.read_bytes()
    record = ingestion.inspect_scene(path, **metadata)
    result = json.loads(record.model_dump_json())
    assert result["checksum"] == hashlib.sha256(before).hexdigest()
    assert result["asset_path"] == str(path.resolve())
    assert (result["width"], result["height"], result["count"]) == (32, 48, 2)
    assert result["gsd"] == 10
    assert result["crs"] == "EPSG:32643"
    assert result["transform"] == [10, 0, 500000, 0, -10, 2000000]
    assert result["scales"] == [0.1, 0.1]
    assert result["offsets"] == [-1, -1]
    assert result["nodata"] == [None, None]
    assert result["cloud_cover"] is None
    assert result["acquisition_time"] == "2026-01-01T21:34:05Z"
    for key in ("scene_id", "platform", "sensor", "ingestion_release"):
        assert result[key] == metadata[key]
    assert result["tiled"] is True
    assert result["cog_layout_hint"] is False
    assert "cog_validated" not in result
    ring = result["footprint"]["coordinates"][0]
    assert len(ring) == 85
    assert ring[0] == ring[-1]
    xs, ys = zip(*ring, strict=True)
    assert result["bbox"] == [min(xs), min(ys), max(xs), max(ys)]
    expected_x, expected_y = reproject("EPSG:32643", "EPSG:4326", [500000], [2000000])
    assert ring[0] == pytest.approx([expected_x[0], expected_y[0]])
    json.dumps(record.model_dump(mode="json"), allow_nan=False)
    assert path.read_bytes() == before
    assert sorted(p.name for p in path.parent.iterdir()) == ["asset.tif"]
    with pytest.raises(ValidationError):
        record.scene_id = "changed"
    with pytest.raises(ValidationError):
        ingestion.SceneRecord.model_validate({**result, "extra": True})


def test_rotated_perimeter(raster, metadata):
    affine = Affine.translation(500000, 2000000) @ Affine.rotation(30) @ Affine.scale(10, -10)
    result = ingestion.inspect_scene(raster(transform=affine), **metadata)
    ring = result.footprint.coordinates[0]
    pixels = [(0, 0), (32, 0), (32, 48), (0, 48)]
    for index, pixel in enumerate(pixels):
        x, y = affine @ pixel
        lon, lat = reproject("EPSG:32643", "EPSG:4326", [x], [y])
        assert ring[index * 21] == pytest.approx((lon[0], lat[0]))
    x, y = affine @ (32 / 21, 0)
    lon, lat = reproject("EPSG:32643", "EPSG:4326", [x], [y])
    assert ring[1] == pytest.approx((lon[0], lat[0]))
    assert result.gsd == pytest.approx(10)


@pytest.mark.parametrize("count,tiled", [(1, False), (3, True)])
def test_single_asset_band_counts(raster, metadata, count, tiled):
    record = ingestion.inspect_scene(raster(count=count, tiled=tiled, nodata=-9999), **metadata)
    assert record.count == count
    assert record.nodata == (-9999,) * count
    assert record.tiled is tiled


@pytest.mark.parametrize(
    "value",
    [
        1700000000,
        1700000000.0,
        "1700000000",
        "2026-01-01",
        "2026-01-01T12:00:00",
        "nonsense",
        date(2026, 1, 1),
        datetime(2026, 1, 1),
    ],
)
def test_bad_timestamp(raster, metadata, value):
    metadata["acquisition_time"] = value
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(raster(), **metadata)
    assert error.value.code == "invalid_metadata"


@pytest.mark.parametrize("value", ["2026-01-01T00:00:00Z", datetime(2026, 1, 1, tzinfo=UTC)])
def test_aware_timestamp(raster, metadata, value):
    metadata["acquisition_time"] = value
    assert ingestion.inspect_scene(raster(), **metadata).acquisition_time.tzinfo == UTC


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.01, 1.01, True])
def test_bad_cloud_cover(raster, metadata, value):
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(raster(), **metadata, cloud_cover=value)
    assert error.value.code == "invalid_metadata"


@pytest.mark.parametrize("value", [None, 0, 0.5, 1])
def test_cloud_cover(raster, metadata, value):
    assert ingestion.inspect_scene(raster(), **metadata, cloud_cover=value).cloud_cover == value


@pytest.mark.parametrize("field", ["scene_id", "platform", "sensor", "ingestion_release"])
def test_empty_identity(raster, metadata, field):
    metadata[field] = "  "
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(raster(), **metadata)
    assert error.value.code == "invalid_metadata"


@pytest.mark.parametrize(
    "crs,code",
    [(None, "invalid_crs"), ("EPSG:4326", "unsupported_grid"), ("EPSG:2277", "unsupported_grid")],
)
def test_crs_policy(raster, metadata, crs, code):
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(raster(crs=crs), **metadata)
    assert error.value.code == code


@pytest.mark.filterwarnings("ignore::rasterio.errors.NotGeoreferencedWarning")
@pytest.mark.parametrize(
    "affine,code",
    [
        (Affine.identity(), "invalid_transform"),
        (Affine(10, 20, 500000, 20, 40, 2000000), "invalid_transform"),
        (Affine(10, 0, float("nan"), 0, -10, 2000000), "invalid_transform"),
        (Affine(10, 0, 500000, 0, -20, 2000000), "unsupported_grid"),
        (Affine(10, 2, 500000, 0, -10, 2000000), "unsupported_grid"),
    ],
)
def test_transform_policy(raster, metadata, affine, code):
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(raster(transform=affine), **metadata)
    assert error.value.code == code


@pytest.mark.parametrize(
    "path,code",
    [
        ("missing.tif", "missing_file"),
        ("https://example.invalid/a.tif", "nonlocal_path"),
        ("s3://bucket/a.tif", "nonlocal_path"),
        ("/vsicurl/a.tif", "nonlocal_path"),
        ("file:///tmp/a.tif", "nonlocal_path"),
    ],
)
def test_path_errors(metadata, path, code):
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(path, **metadata)
    assert error.value.code == code


def test_corrupt_file(tmp_path, metadata):
    path = tmp_path / "bad.tif"
    path.write_bytes(b"not a tiff")
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(path, **metadata)
    assert error.value.code == "unreadable_raster"


def test_corrupt_last_band_block(raster, metadata):
    path = raster(interleave="band", compress="deflate")
    with rasterio.open(path) as dataset:
        offset = int(dataset.get_tag_item("BLOCK_OFFSET_1_2", "TIFF", bidx=2))
    with path.open("r+b") as stream:
        stream.seek(offset)
        stream.write(b"\x00" * 16)
    with rasterio.open(path) as dataset:
        dataset.read(1, window=((0, 16), (0, 16)))
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(path, **metadata)
    assert error.value.code == "unreadable_raster"


def test_non_gtiff(tmp_path, metadata):
    path = tmp_path / "not-tiff.tif"
    with (
        pytest.warns(NotGeoreferencedWarning),
        rasterio.open(
            path, "w", driver="PNG", width=2, height=2, count=1, dtype="uint8"
        ) as dataset,
    ):
        dataset.write(np.ones((1, 2, 2), dtype="uint8"))
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(path, **metadata)
    assert error.value.code == "unreadable_raster"


def test_antimeridian_rejected(raster, metadata):
    path = raster(crs="EPSG:32660", transform=Affine(1000, 0, 830000, 0, -1000, 1000000))
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(path, **metadata)
    assert error.value.code == "invalid_footprint"


def test_invalid_projected_coordinates(raster, metadata):
    path = raster(transform=Affine(10, 0, 1e30, 0, -10, 1e30))
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(path, **metadata)
    assert error.value.code == "invalid_footprint"


@pytest.mark.parametrize(
    "field,value",
    [
        ("gsd", float("nan")),
        ("gsd", 0),
        ("gsd", -1),
        ("checksum", "x" * 64),
        ("checksum", "a" * 63),
        ("asset_path", "https://example.invalid/a.tif"),
    ],
)
def test_record_validation(raster, metadata, field, value):
    data = ingestion.inspect_scene(raster(), **metadata).model_dump(exclude={"bbox"})
    data[field] = value
    with pytest.raises(ValidationError):
        ingestion.SceneRecord.model_validate(data)


def cli(path, metadata, *extra):
    args = [sys.executable, "-m", "tessera_x.ingestion", "inspect", str(path)]
    for key, value in metadata.items():
        args.extend(["--" + key.replace("_", "-"), str(value)])
    return subprocess.run([*args, *extra], capture_output=True, text=True, check=False)


def test_cli_success(raster, metadata):
    result = cli(raster(), metadata, "--cloud-cover", "0.3")
    assert result.returncode == 0
    assert result.stderr == ""
    data = json.loads(result.stdout)
    assert data["cloud_cover"] == 0.3
    assert data["acquisition_time"] == "2026-01-01T21:34:05Z"


@pytest.mark.parametrize(
    "extra,code",
    [
        ((), "missing_file"),
        (("--cloud-cover", "nan"), "invalid_metadata"),
        (("--cloud-cover", "garbage"), "invalid_arguments"),
        (("--unknown", "x"), "invalid_arguments"),
    ],
)
def test_cli_failure(tmp_path, metadata, extra, code):
    result = cli(tmp_path / "missing.tif", metadata, *extra)
    assert result.returncode != 0
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == code
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("crs", ["garbage", "EPSG:999999", "EPSG:4326", "EPSG:2277"])
def test_record_crs_validation(raster, metadata, crs):
    data = ingestion.inspect_scene(raster(), **metadata).model_dump(exclude={"bbox"})
    data["crs"] = crs
    with pytest.raises(ValidationError):
        ingestion.SceneRecord.model_validate(data)


def test_unknown_projected_crs(raster, metadata):
    crs = "+proj=tmerc +lat_0=12.345 +lon_0=73.123 +k=0.987 +datum=WGS84 +units=m"
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(raster(crs=crs), **metadata)
    assert error.value.code == "unsupported_grid"


@pytest.mark.parametrize(
    "ring",
    [
        ((181, 1), (182, 1), (182, 2), (181, 1)),
        ((1, 91), (2, 91), (2, 92), (1, 91)),
        ((0, 0), (1, 1), (0, 1), (1, 0), (0, 0)),
        ((0, 0), (1, 1), (2, 2), (0, 0)),
    ],
)
def test_record_invalid_footprint(raster, metadata, ring):
    data = ingestion.inspect_scene(raster(), **metadata).model_dump(exclude={"bbox"})
    data["footprint"]["coordinates"] = (ring,)
    with pytest.raises(ValidationError):
        ingestion.SceneRecord.model_validate(data)


@pytest.mark.parametrize("value", ["2026-01-01T00:00:00+00:99", "2026-01-01T00:00:00-00:00"])
def test_invalid_timezone_offset(raster, metadata, value):
    metadata["acquisition_time"] = value
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(raster(), **metadata)
    assert error.value.code == "invalid_metadata"


def test_cli_invalid_projection(raster, metadata):
    path = raster(transform=Affine(10, 0, 1e30, 0, -10, 1e30))
    result = cli(path, metadata)
    assert result.returncode != 0
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "invalid_footprint"


def test_cli_corruption(tmp_path, metadata):
    path = tmp_path / "bad.tif"
    path.write_bytes(b"broken")
    result = cli(path, metadata)
    assert result.returncode != 0
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "unreadable_raster"


@pytest.mark.parametrize(
    "field,value",
    [
        ("transform", ("10", "0", "500000", "0", "-10", "2000000")),
        ("scales", ("0.1", "0.1")),
        ("offsets", ("-1", "-1")),
        ("nodata", (-9999, True)),
        ("cloud_cover", True),
        ("tiled", "true"),
        ("cog_layout_hint", 1),
        ("width", 32.0),
        ("height", True),
        ("gsd", "10"),
        ("asset_path", b"/tmp/a.tif"),
    ],
)
def test_record_strict_types(raster, metadata, field, value):
    data = ingestion.inspect_scene(raster(), **metadata).model_dump(exclude={"bbox"})
    data[field] = value
    with pytest.raises(ValidationError):
        ingestion.SceneRecord.model_validate(data)


@pytest.mark.parametrize(
    "coordinates", [((0, "1"), (1, 1), (1, 2), (0, 0)), ((0, True), (1, 1), (1, 2), (0, 0))]
)
def test_record_strict_footprint(raster, metadata, coordinates):
    data = ingestion.inspect_scene(raster(), **metadata).model_dump(exclude={"bbox"})
    data["footprint"]["coordinates"] = (coordinates,)
    with pytest.raises(ValidationError):
        ingestion.SceneRecord.model_validate(data)


def test_nonfinite_calibration(raster, metadata):
    path = raster()
    with rasterio.open(path, "r+") as dataset:
        dataset.scales = (float("nan"), 1)
    with pytest.raises(ingestion.InspectionError) as error:
        ingestion.inspect_scene(path, **metadata)
    assert error.value.code == "invalid_raster_metadata"


def test_cli_required_metadata(tmp_path):
    result = cli(tmp_path / "missing.tif", {})
    assert result.returncode != 0
    assert result.stdout == ""
    assert json.loads(result.stderr)["error"]["code"] == "invalid_arguments"
