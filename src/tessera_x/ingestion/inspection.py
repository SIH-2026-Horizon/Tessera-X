import hashlib
import math
import warnings
from datetime import datetime
from pathlib import Path

import rasterio
from pydantic import ValidationError
from rasterio._err import CPLE_BaseError
from rasterio.errors import CRSError, NotGeoreferencedWarning, RasterioError
from rasterio.warp import transform as reproject

from .record import Footprint, SceneRecord, SourceMetadata, finite_or_none, local_path


class InspectionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _grid(dataset) -> float:
    crs = dataset.crs
    if crs is None or not crs:
        raise InspectionError("invalid_crs", "A valid embedded CRS is required")
    if not crs.is_projected or crs.to_epsg() is None:
        raise InspectionError("unsupported_grid", "Only EPSG projected metre grids are supported")
    if crs.linear_units_factor[1] != 1:
        raise InspectionError("unsupported_grid", "CRS units must be metres")
    affine = dataset.transform
    if (
        not all(math.isfinite(value) for value in affine[:6])
        or affine.is_identity
        or not math.isfinite(affine.determinant)
        or affine.determinant == 0
    ):
        raise InspectionError(
            "invalid_transform", "A finite nonsingular georeferenced affine is required"
        )
    x_size = math.hypot(affine.a, affine.d)
    y_size = math.hypot(affine.b, affine.e)
    if not all(math.isfinite(size) and size > 0 for size in (x_size, y_size)):
        raise InspectionError("invalid_transform", "Pixel sizes must be finite and positive")
    dot = (affine.a / x_size) * (affine.b / y_size) + (affine.d / x_size) * (affine.e / y_size)
    if not math.isclose(x_size, y_size, rel_tol=1e-9) or abs(dot) > 1e-9:
        raise InspectionError(
            "unsupported_grid", "Only square orthogonal pixel grids are supported"
        )
    return x_size


def _footprint(dataset) -> Footprint:
    corners = [(0, 0), (dataset.width, 0), (dataset.width, dataset.height), (0, dataset.height)]
    perimeter = []
    for start, end in zip(corners, [*corners[1:], corners[0]], strict=True):
        for step in range(21):
            fraction = step / 21
            pixel = (
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            )
            perimeter.append(dataset.transform @ pixel)
    perimeter.append(perimeter[0])
    xs, ys = zip(*perimeter, strict=True)
    try:
        longitudes, latitudes = reproject(dataset.crs, "EPSG:4326", xs, ys)
        return Footprint(coordinates=(tuple(zip(longitudes, latitudes, strict=True)),))
    except (CPLE_BaseError, RasterioError, ValueError, OverflowError) as error:
        raise InspectionError(
            "invalid_footprint", "Cannot form a valid non-antimeridian footprint"
        ) from error


def inspect_scene(
    path: str | Path,
    *,
    scene_id: str,
    platform: str,
    sensor: str,
    acquisition_time: str | datetime,
    ingestion_release: str,
    cloud_cover: float | None = None,
) -> SceneRecord:
    try:
        source = SourceMetadata(
            scene_id=scene_id,
            platform=platform,
            sensor=sensor,
            acquisition_time=acquisition_time,
            ingestion_release=ingestion_release,
            cloud_cover=cloud_cover,
        )
    except (ValidationError, OverflowError) as error:
        raise InspectionError("invalid_metadata", "Invalid explicit source metadata") from error
    try:
        asset = local_path(path)
    except ValueError as error:
        raise InspectionError("nonlocal_path", str(error)) from error
    try:
        asset = asset.resolve(strict=True)
        if not asset.is_file():
            raise InspectionError("invalid_path", "Asset must be a regular local file")
        with (
            warnings.catch_warnings(),
            rasterio.Env(
                GDAL_PAM_ENABLED="NO",
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                GTIFF_SRS_SOURCE="EPSG",
            ),
        ):
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with rasterio.open(asset, driver="GTiff", GEOREF_SOURCES="INTERNAL") as dataset:
                gsd = _grid(dataset)
                footprint = _footprint(dataset)
                for band in dataset.indexes:
                    for _, window in dataset.block_windows(band):
                        dataset.read(band, window=window)
                extracted = {
                    "footprint": footprint,
                    "crs": dataset.crs.to_string(),
                    "gsd": gsd,
                    "width": dataset.width,
                    "height": dataset.height,
                    "count": dataset.count,
                    "transform": tuple(dataset.transform[:6]),
                    "scales": dataset.scales,
                    "offsets": dataset.offsets,
                    "nodata": tuple(finite_or_none(value) for value in dataset.nodatavals),
                    "tiled": dataset.profile.get("tiled", False),
                    "cog_layout_hint": dataset.tags(ns="IMAGE_STRUCTURE").get("LAYOUT") == "COG",
                }
        digest = hashlib.sha256()
        with asset.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return SceneRecord(
            **source.model_dump(),
            **extracted,
            asset_path=str(asset),
            checksum=digest.hexdigest(),
        )
    except FileNotFoundError as error:
        raise InspectionError("missing_file", "Local asset does not exist") from error
    except CRSError as error:
        raise InspectionError("invalid_crs", "Invalid embedded CRS") from error
    except (OSError, RasterioError) as error:
        raise InspectionError("unreadable_raster", "Cannot fully read the local GeoTIFF") from error
    except ValidationError as error:
        raise InspectionError(
            "invalid_raster_metadata", "Raster metadata is invalid or nonfinite"
        ) from error
