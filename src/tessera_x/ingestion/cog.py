"""Generate local COGs and verify decoded data, not full COG specification compliance."""

import math
import os
import tempfile
from pathlib import Path

import numpy as np
import rasterio
import rasterio.shutil
from rasterio.errors import RasterioError
from rasterio.windows import Window

from .inspection import InspectionError, inspect_scene
from .record import SceneRecord, local_path

__all__ = ["COGError", "prepare_cog"]


class COGError(InspectionError):
    """Preparation failure with a machine-readable code, compatible with inspection errors."""


def _nodata_equal(left: tuple, right: tuple) -> bool:
    return len(left) == len(right) and all(
        a == b or (a is not None and b is not None and math.isnan(a) and math.isnan(b))
        for a, b in zip(left, right, strict=True)
    )


def _verify(source_path: str, staging: Path) -> None:
    """Compare every base-resolution pixel/mask in bounded windows, including masked pixels."""
    try:
        with (
            rasterio.open(source_path, driver="GTiff", GEOREF_SOURCES="INTERNAL") as origin,
            rasterio.open(staging, driver="GTiff", GEOREF_SOURCES="INTERNAL") as staged,
        ):
            if (
                staged.count != origin.count
                or staged.width != origin.width
                or staged.height != origin.height
                or staged.dtypes != origin.dtypes
                or staged.crs != origin.crs
                or staged.transform != origin.transform
                or staged.scales != origin.scales
                or staged.offsets != origin.offsets
                or not _nodata_equal(staged.nodatavals, origin.nodatavals)
            ):
                raise COGError("verify_failed", "COG metadata does not match the source raster")
            if (
                staged.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") != "COG"
                or not staged.profile.get("tiled", False)
                or set(staged.files) != {str(staging)}
            ):
                raise COGError("verify_failed", "Expected a self-contained tiled GDAL COG")
            for row in range(0, origin.height, 512):
                for col in range(0, origin.width, 512):
                    window = Window(
                        col, row, min(512, origin.width - col), min(512, origin.height - row)
                    )
                    for band in origin.indexes:
                        if not np.array_equal(
                            origin.read(band, window=window),
                            staged.read(band, window=window),
                            equal_nan=True,
                        ):
                            raise COGError("verify_failed", "Pixel data does not match the source")
                        if not np.array_equal(
                            origin.read_masks(band, window=window),
                            staged.read_masks(band, window=window),
                        ):
                            raise COGError("verify_failed", "Band masks do not match the source")
                    if not np.array_equal(
                        origin.dataset_mask(window=window), staged.dataset_mask(window=window)
                    ):
                        raise COGError("verify_failed", "Dataset mask does not match the source")
    except (RasterioError, OSError) as error:
        raise COGError("verify_failed", "Cannot decode and verify the generated COG") from error


def prepare_cog(source: str | Path, destination: str | Path, **metadata) -> SceneRecord:
    """Inspect, generate, verify and atomically publish a local COG without overwriting.

    ``metadata`` is passed to :func:`inspect_scene`; scene_id, platform, sensor,
    acquisition_time and ingestion_release are required, cloud_cover is optional.
    Source inspection happens before conversion. The source is opened read-only.
    The destination parent must exist and support hard links. Existing destination
    entries (including dangling symlinks and the source itself) are rejected.

    GDAL's COG driver writes a temporary sibling using lossless DEFLATE compression.
    Grid, CRS, dtypes, scales, offsets, raw nodata (including NaN vs absent), and
    every decoded base-resolution pixel and mask are compared before publication.
    The temporary output is inspected before an atomic, exclusive ``os.link``
    publishes it; this never replaces a concurrent writer's destination. The
    returned inspected record uses the final path and generated file's checksum.

    Validation status is deliberately limited: GDAL-generated COG plus layout
    hint and decoded-data comparison, NOT an independent full COG-spec validator.
    Overview contents/ordering and HTTP range behaviour are not independently
    validated. Callers must keep source files and destination directories stable
    during preparation; arbitrary concurrent source edits are not snapshotted.
    PAM metadata is ignored, matching inspection's embedded-metadata policy.

    On failure, staging files are removed. A cleanup failure is reported explicitly
    as ``cleanup_failure``; if publication already succeeded the valid destination
    is retained rather than risking deletion of another writer's file. Atomic
    visibility is guaranteed on a supporting filesystem, not power-loss durability.
    """
    try:
        source_record = inspect_scene(source, **metadata)
    except TypeError as error:
        raise COGError("invalid_metadata", "Missing or unknown explicit source metadata") from error
    except InspectionError as error:
        raise COGError(error.code, str(error)) from error

    try:
        destination_path = local_path(destination)
    except ValueError as error:
        raise COGError("nonlocal_path", str(error)) from error
    # Resolve only the parent: resolving the last component would follow and
    # accidentally accept an existing dangling symlink.
    try:
        output = destination_path.parent.resolve() / destination_path.name
        if os.path.lexists(output):
            raise COGError("destination_exists", f"Destination already exists: {output}")
        if not output.parent.is_dir():
            raise COGError("destination_unwritable", "Destination directory must already exist")
    except OSError as error:
        raise COGError("destination_unwritable", "Cannot access destination directory") from error

    staging = None
    try:
        handle, staging_name = tempfile.mkstemp(
            dir=output.parent, prefix=f".{output.name}.", suffix=".tif"
        )
        staging = Path(staging_name)
        os.close(handle)
        with rasterio.Env(GDAL_PAM_ENABLED="NO", GDAL_TIFF_INTERNAL_MASK=True):
            with rasterio.open(
                source_record.asset_path, driver="GTiff", GEOREF_SOURCES="INTERNAL"
            ) as origin:
                rasterio.shutil.copy(origin, staging, driver="COG", COMPRESS="DEFLATE")
            _verify(source_record.asset_path, staging)
            try:
                result = inspect_scene(staging, **metadata)
            except InspectionError as error:
                raise COGError("verify_failed", "Generated COG failed scene inspection") from error
        # Validate the final record before publication, so failed validation cannot
        # leave behind a destination. Only the path changes; hard links share bytes.
        result = SceneRecord.model_validate(
            {**result.model_dump(exclude={"bbox"}), "asset_path": str(output)}
        )
        try:
            os.link(staging, output)
        except FileExistsError as error:
            raise COGError(
                "destination_exists", "Destination appeared during preparation"
            ) from error
        return result
    except (OSError, RasterioError) as error:
        raise COGError("cog_write_failed", "Cannot generate or publish the local COG") from error
    finally:
        if staging is not None:
            # Only known GDAL sidecars belonging to our unique staging path.
            failures = []
            for path in (
                staging,
                *(Path(str(staging) + ext) for ext in (".msk", ".aux.xml", ".ovr")),
            ):
                try:
                    path.unlink(missing_ok=True)
                except OSError as error:
                    failures.append(error)
            if failures:
                raise COGError(
                    "cleanup_failure", f"Cannot fully remove staging asset {staging}"
                ) from failures[0]
