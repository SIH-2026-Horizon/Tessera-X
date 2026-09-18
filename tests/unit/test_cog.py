import hashlib
import json
from datetime import UTC

import numpy as np
import pytest
import rasterio
import rasterio.shutil
from rasterio import Affine
from rasterio.errors import RasterioError

from tessera_x.ingestion.cog import COGError, prepare_cog

METADATA = {
    "scene_id": "scene-1",
    "platform": "local-platform",
    "sensor": "local-sensor",
    "acquisition_time": "2026-01-02T03:04:05+05:30",
    "ingestion_release": "cog-1",
}


@pytest.fixture
def source(tmp_path):
    def create(name="source.tif", **overrides):
        profile = {
            "driver": "GTiff",
            "width": 64,
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
        fill = 7.5 if profile["dtype"].startswith("float") else 3
        data = np.full(
            (profile["count"], profile["height"], profile["width"]), fill, dtype=profile["dtype"]
        )
        if profile["dtype"].startswith("float"):
            data[0, :4, :4] = np.nan
            data[-1, -4:, -2:] = -9999.0
        path = tmp_path / name
        with rasterio.open(path, "w", **profile) as dataset:
            dataset.write(data)
            dataset.scales = (0.1,) * profile["count"]
            dataset.offsets = (-1.0,) * profile["count"]
        return path

    return create


def test_prepare_cog_record(source, tmp_path):
    path = source()
    before = path.read_bytes()
    record = prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    result = json.loads(record.model_dump_json())
    assert result["scene_id"] == METADATA["scene_id"]
    assert result["platform"] == METADATA["platform"]
    assert result["sensor"] == METADATA["sensor"]
    assert result["ingestion_release"] == METADATA["ingestion_release"]
    assert result["acquisition_time"] == "2026-01-01T21:34:05Z"
    assert result["cloud_cover"] is None
    assert result["asset_path"] == str((tmp_path / "scene.tif").resolve())
    assert result["checksum"] == hashlib.sha256((tmp_path / "scene.tif").read_bytes()).hexdigest()
    assert (result["width"], result["height"], result["count"]) == (64, 48, 2)
    assert result["crs"] == "EPSG:32643"
    assert result["transform"] == [10, 0, 500000, 0, -10, 2000000]
    assert result["gsd"] == 10
    assert result["nodata"] == [None, None]
    assert result["tiled"] is True
    assert result["cog_layout_hint"] is True
    assert "cog_validated" not in result
    json.dumps(record.model_dump(mode="json"), allow_nan=False)
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["scene.tif", "source.tif"]


def test_prepare_cog_pixels_masks_calibration(source, tmp_path):
    path = source()
    record = prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    with rasterio.open(path) as origin, rasterio.open(record.asset_path) as staged:
        assert np.array_equal(origin.read(), staged.read(), equal_nan=True)
        assert np.array_equal(origin.read_masks(), staged.read_masks())
        assert staged.read_masks().min() == 0
        assert staged.scales == origin.scales
        assert staged.offsets == origin.offsets
        assert all(np.isnan(value) for value in staged.nodatavals)
        assert staged.crs == origin.crs
        assert staged.transform == origin.transform
        assert staged.dtypes == origin.dtypes
        assert staged.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") == "COG"


def test_prepare_cog_mask_only(source, tmp_path):
    path = source(dtype="uint8", count=1, nodata=None)
    mask = np.where(np.arange(48 * 64).reshape(48, 64) % 5 == 0, 0, 255).astype("uint8")
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK="YES"), rasterio.open(path, "r+") as dataset:
        dataset.write_mask(mask)
    record = prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    with rasterio.open(path) as origin, rasterio.open(record.asset_path) as staged:
        assert np.array_equal(origin.read_masks(), staged.read_masks())
        assert np.array_equal(origin.read(), staged.read())
        assert staged.nodatavals == (None,)


@pytest.mark.parametrize("count,tiled,nodata", [(1, False, None), (3, True, -9999)])
def test_prepare_cog_shapes(source, tmp_path, count, tiled, nodata):
    path = source(count=count, tiled=tiled, nodata=nodata)
    record = prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    assert record.count == count
    assert record.tiled is True
    expected_nodata = (float(nodata),) * count if nodata is not None else (None,) * count
    assert record.nodata == expected_nodata


def test_prepare_cog_int16_stripe(source, tmp_path):
    path = source(dtype="int16", count=1, nodata=-32768)
    with rasterio.open(path, "r+") as dataset:
        dataset.write(np.arange(48 * 64, dtype="int16").reshape(1, 48, 64))
    record = prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    with rasterio.open(path) as origin, rasterio.open(record.asset_path) as staged:
        assert np.array_equal(origin.read(), staged.read())
        assert staged.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") == "COG"


def test_prepare_cog_explicit_metadata(source, tmp_path):
    record = prepare_cog(
        source(),
        tmp_path / "scene.tif",
        **{**METADATA, "cloud_cover": 0.3, "acquisition_time": "2026-01-01T00:00:00Z"},
    )
    assert record.cloud_cover == 0.3
    assert record.acquisition_time.tzinfo == UTC


def test_source_untouched_and_no_stray_files(source, tmp_path):
    path = source()
    before = path.read_bytes()
    nested = tmp_path / "nested"
    nested.mkdir()
    prepare_cog(path, nested / "scene.tif", **METADATA)
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["nested", "source.tif"]
    assert sorted(p.name for p in nested.iterdir()) == ["scene.tif"]


def test_reject_existing_output(source, tmp_path):
    path = source()
    output = tmp_path / "scene.tif"
    output.write_bytes(b"placeholder")
    with pytest.raises(COGError) as error:
        prepare_cog(path, output, **METADATA)
    assert error.value.code == "destination_exists"
    assert output.read_bytes() == b"placeholder"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["scene.tif", "source.tif"]


def test_reject_same_path(source):
    with pytest.raises(COGError) as error:
        prepare_cog(source(), source(), **METADATA)
    assert error.value.code == "destination_exists"


def test_reject_relative_output(source, tmp_path, monkeypatch):
    path = source()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "relative.tif").write_bytes(b"placeholder")
    with pytest.raises(COGError) as error:
        prepare_cog(path, "relative.tif", **METADATA)
    assert error.value.code == "destination_exists"


def test_missing_destination_directory(source, tmp_path):
    with pytest.raises(COGError) as error:
        prepare_cog(source(), tmp_path / "ghost" / "scene.tif", **METADATA)
    assert error.value.code == "destination_unwritable"


def test_invalid_source_metadata(source, tmp_path):
    with pytest.raises(COGError) as error:
        prepare_cog(source(), tmp_path / "scene.tif", scene_id=" ")
    assert error.value.code == "invalid_metadata"


def test_invalid_source_path(source, tmp_path):
    path = source()
    with pytest.raises(COGError) as error:
        prepare_cog(tmp_path / "missing.tif", tmp_path / "scene.tif", **METADATA)
    assert error.value.code == "missing_file"
    with pytest.raises(COGError) as error:
        prepare_cog("s3://bucket/scene.tif", tmp_path / "scene.tif", **METADATA)
    assert error.value.code == "nonlocal_path"
    with pytest.raises(COGError) as error:
        prepare_cog(path, "s3://bucket/scene.tif", **METADATA)
    assert error.value.code == "nonlocal_path"


def test_invalid_source_raster(tmp_path):
    path = tmp_path / "broken.tif"
    path.write_bytes(b"not a tiff")
    with pytest.raises(COGError) as error:
        prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    assert error.value.code == "unreadable_raster"


def test_strict_metadata_types(source, tmp_path):
    with pytest.raises(COGError) as error:
        prepare_cog(source(), tmp_path / "scene.tif", cloud_cover=True)
    assert error.value.code == "invalid_metadata"


def test_staging_failure(source, tmp_path, monkeypatch):
    path = source()

    def failing_mkstemp(*args, **kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr("tessera_x.ingestion.cog.tempfile.mkstemp", failing_mkstemp)
    with pytest.raises(COGError) as error:
        prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    assert error.value.code == "cog_write_failed"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source.tif"]


def test_cleanup_on_copy_failure(source, tmp_path, monkeypatch):
    path = source()

    def failing_copy(*args, **kwargs):
        raise RasterioError("copy failed")

    monkeypatch.setattr(rasterio.shutil, "copy", failing_copy)
    with pytest.raises(COGError) as error:
        prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    assert error.value.code == "cog_write_failed"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source.tif"]


def test_cleanup_failure_after_publish(source, tmp_path, monkeypatch):
    path = source()

    def failing_unlink(self, *args, **kwargs):
        raise OSError("cannot unlink")

    monkeypatch.setattr(type(tmp_path / "x"), "unlink", failing_unlink)
    with pytest.raises(COGError) as error:
        prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    monkeypatch.undo()
    assert error.value.code == "cleanup_failure"
    assert (tmp_path / "scene.tif").is_file()
    assert any(p.name.startswith(".scene.tif.") for p in tmp_path.iterdir())


def test_no_network(source, tmp_path, monkeypatch):
    import socket

    def blocked(*args, **kwargs):
        raise AssertionError("network access is not allowed")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    record = prepare_cog(source(), tmp_path / "scene.tif", **METADATA)
    assert record.cog_layout_hint is True


def test_publication_race_never_overwrites(source, tmp_path, monkeypatch):
    import os

    path = source()
    before = path.read_bytes()
    destination = tmp_path / "scene.tif"
    real_link = os.link

    def competing_link(staging, output):
        assert output == destination
        destination.write_bytes(b"concurrent writer")
        return real_link(staging, output)

    monkeypatch.setattr("tessera_x.ingestion.cog.os.link", competing_link)
    with pytest.raises(COGError) as error:
        prepare_cog(path, destination, **METADATA)
    assert error.value.code == "destination_exists"
    assert destination.read_bytes() == b"concurrent writer"
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["scene.tif", "source.tif"]


@pytest.mark.parametrize("kind", ["directory", "symlink", "dangling_symlink", "hardlink"])
def test_existing_destination_entries(source, tmp_path, kind):
    import os

    path = source()
    before = path.read_bytes()
    output = tmp_path / "scene.tif"
    if kind == "directory":
        output.mkdir()
    elif kind == "hardlink":
        os.link(path, output)
    else:
        output.symlink_to(path if kind == "symlink" else tmp_path / "absent.tif")
    with pytest.raises(COGError) as error:
        prepare_cog(path, output, **METADATA)
    assert error.value.code == "destination_exists"
    assert os.path.lexists(output)
    assert path.read_bytes() == before


@pytest.mark.parametrize("defect", ["pixels", "masks", "scales", "offsets", "nodata", "grid"])
def test_verification_rejects_changed_output(source, tmp_path, monkeypatch, defect):
    from rasterio.io import MemoryFile

    path = source()
    before = path.read_bytes()
    real_copy = rasterio.shutil.copy

    def changed_copy(origin, destination, **options):
        with MemoryFile() as memory:
            with memory.open(**origin.profile) as changed:
                changed.write(origin.read())
                changed.scales = origin.scales
                changed.offsets = origin.offsets
                if defect == "pixels":
                    pixels = changed.read(2)
                    pixels[-1, -1] = 123
                    changed.write(pixels, 2)
                elif defect == "masks":
                    changed.write_mask(np.full(origin.shape, 255, dtype="uint8"))
                elif defect == "scales":
                    changed.scales = (0.25,) * origin.count
                elif defect == "offsets":
                    changed.offsets = (42,) * origin.count
                elif defect == "nodata":
                    changed.nodata = None
                else:
                    changed.transform = origin.transform @ Affine.translation(1, 0)
            with memory.open() as changed:
                real_copy(changed, destination, **options)

    monkeypatch.setattr(rasterio.shutil, "copy", changed_copy)
    with pytest.raises(COGError) as error:
        prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    assert error.value.code == "verify_failed"
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source.tif"]


def test_copy_failure_cleans_partial_file_and_sidecars(source, tmp_path, monkeypatch):
    from pathlib import Path

    path = source()

    def partial_copy(origin, staging, **options):
        staging.write_bytes(b"partial TIFF")
        Path(str(staging) + ".msk").write_bytes(b"partial mask")
        Path(str(staging) + ".aux.xml").write_bytes(b"partial metadata")
        raise RasterioError("interrupted copy")

    monkeypatch.setattr(rasterio.shutil, "copy", partial_copy)
    with pytest.raises(COGError) as error:
        prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    assert error.value.code == "cog_write_failed"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source.tif"]


def test_output_inspection_failure_prevents_publication(source, tmp_path, monkeypatch):
    import tessera_x.ingestion.cog as cog_module
    from tessera_x.ingestion import InspectionError

    path = source()
    real_inspect = cog_module.inspect_scene
    calls = []

    def inspect_output_failure(asset, **metadata):
        calls.append(asset)
        if len(calls) == 2:
            raise InspectionError("unreadable_raster", "failed output inspection")
        return real_inspect(asset, **metadata)

    monkeypatch.setattr(cog_module, "inspect_scene", inspect_output_failure)
    with pytest.raises(COGError) as error:
        prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    assert error.value.code == "verify_failed"
    assert calls[0] == path
    assert len(calls) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source.tif"]


def test_multiple_comparison_windows_and_external_mask(source, tmp_path):
    path = source(width=517, height=523, nodata=-9999)
    mask = np.full((523, 517), 255, dtype="uint8")
    mask[-1, -1] = 0
    with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=False), rasterio.open(path, "r+") as dataset:
        dataset.write_mask(mask)
        dataset.scales = (0.1, 0.25)
        dataset.offsets = (-1, -5)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    record = prepare_cog(path, tmp_path / "scene.tif", **METADATA)
    assert record.scales == (0.1, 0.25)
    assert record.offsets == (-1, -5)
    with rasterio.open(path) as origin, rasterio.open(record.asset_path) as output:
        assert np.array_equal(origin.read(), output.read(), equal_nan=True)
        assert np.array_equal(origin.read_masks(), output.read_masks())
        assert output.dataset_mask()[-1, -1] == 0
        assert output.files == [record.asset_path]
    for name, content in before.items():
        assert (tmp_path / name).read_bytes() == content
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "scene.tif",
        "source.tif",
        "source.tif.msk",
    ]
