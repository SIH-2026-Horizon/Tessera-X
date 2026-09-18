"""Deterministic, read-only patch extraction from inspected local scenes.

Windows are (column offset, row offset, width, height) in source pixels. Values
remain in source band order and dtype, without calibration or reprojection.
``valid_fraction_v1`` measures pixels valid and finite in *every* band; it is
not a cloud estimate. Footprints and bounding boxes use EPSG:4326.
"""

import hashlib
import json
from datetime import datetime
from types import SimpleNamespace
from typing import Annotated, Literal, Self

import numpy as np
import rasterio
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator
from rasterio.windows import Window

from .inspection import _footprint, inspect_scene
from .record import Footprint, Fraction, Identity, PositiveMetres, SceneRecord, SourceMetadata

Offset = Annotated[int, Field(ge=0, strict=True)]
Size = Annotated[int, Field(gt=0, strict=True)]
PixelWindow = tuple[Offset, Offset, Size, Size]
Checksum = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", strict=True)]


def _patch_id(scene_id: str, checksum: str, window: PixelWindow) -> str:
    payload = json.dumps(
        ["tessera_x.patch.v1", scene_id, checksum, window],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PatchRecord(BaseModel):
    """Immutable patch provenance; ``scene_checksum`` is the source file SHA-256."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    patch_id: Checksum
    scene_id: Identity
    scene_checksum: Checksum
    window: PixelWindow
    acquisition_time: datetime
    sensor: Identity
    gsd: PositiveMetres
    footprint: Footprint
    quality_score: Fraction
    quality_method: Literal["valid_fraction_v1"] = "valid_fraction_v1"

    @field_validator("acquisition_time", mode="before")
    @classmethod
    def explicit_timestamp(cls, value: object) -> datetime:
        return SourceMetadata.explicit_timestamp(value)

    @model_validator(mode="after")
    def identity_matches_window(self) -> Self:
        if self.patch_id != _patch_id(self.scene_id, self.scene_checksum, self.window):
            raise ValueError("Patch ID does not match scene identity, checksum and window")
        return self

    @computed_field
    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs, ys = zip(*self.footprint.coordinates[0], strict=True)
        return min(xs), min(ys), max(xs), max(ys)


def _validate_scene(scene: SceneRecord) -> SceneRecord:
    if not isinstance(scene, SceneRecord):
        raise ValueError("scene must be an inspected SceneRecord")
    # model_copy/model_construct bypass Pydantic validation, so validate anew.
    original = scene.model_dump(exclude={"bbox"}, warnings=False)
    validated = SceneRecord.model_validate(original)
    if validated.model_dump(exclude={"bbox"}) != original:
        raise ValueError("Scene does not match a validated inspected record")
    metadata = {name: getattr(validated, name) for name in SourceMetadata.model_fields}
    current = inspect_scene(validated.asset_path, **metadata)
    # Relocation of identical bytes is allowed, but every other field must match.
    if current.model_dump(exclude={"asset_path"}) != validated.model_dump(exclude={"asset_path"}):
        raise ValueError("Source does not match the inspected scene record")
    return current


def _read_pixels(dataset, window: PixelWindow) -> np.ma.MaskedArray:
    pixels = dataset.read(window=Window(*window), masked=True)
    return np.ma.masked_invalid(pixels, copy=False)


def _record(
    scene: SceneRecord, dataset, window: PixelWindow, pixels: np.ma.MaskedArray
) -> PatchRecord:
    _, _, width, height = window
    # Reuse inspection's densified (21 segments per edge) rotated-grid perimeter.
    grid = SimpleNamespace(
        width=width,
        height=height,
        transform=dataset.window_transform(Window(*window)),
        crs=dataset.crs,
    )
    all_band_valid = ~np.ma.getmaskarray(pixels).any(axis=0)
    return PatchRecord(
        patch_id=_patch_id(scene.scene_id, scene.checksum, window),
        scene_id=scene.scene_id,
        scene_checksum=scene.checksum,
        window=window,
        acquisition_time=scene.acquisition_time,
        sensor=scene.sensor,
        gsd=scene.gsd,
        footprint=_footprint(grid),
        quality_score=float(all_band_valid.mean()),
    )


def extract_patches(scene: SceneRecord, patch_size: int = 256) -> list[PatchRecord]:
    """Inspect source integrity, then return nonoverlapping row-major patches.

    Edge windows are clipped, never padded. ``patch_size`` must be a positive
    Python integer (booleans and floats are rejected). No files are written.
    A stale source or altered inspected raster metadata raises ``ValueError``.
    """
    if type(patch_size) is not int or patch_size <= 0:
        raise ValueError("patch_size must be a positive integer")
    current = _validate_scene(scene)
    patches = []
    with (
        rasterio.Env(
            GDAL_PAM_ENABLED="NO",
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            GTIFF_SRS_SOURCE="EPSG",
        ),
        rasterio.open(current.asset_path, driver="GTiff", GEOREF_SOURCES="INTERNAL") as dataset,
    ):
        for row in range(0, current.height, patch_size):
            for col in range(0, current.width, patch_size):
                window = (
                    col,
                    row,
                    min(patch_size, current.width - col),
                    min(patch_size, current.height - row),
                )
                patches.append(_record(current, dataset, window, _read_pixels(dataset, window)))
    return patches


def read_patch(scene: SceneRecord, patch: PatchRecord) -> np.ma.MaskedArray:
    """Reconstruct raw (bands, height, width) pixels with per-band validity masks.

    Re-inspect the source and recompute all patch metadata before returning data.
    Reject scene mismatches, out-of-bounds windows and altered patch records,
    including unvalidated Pydantic copies. Mask nodata and nonfinite samples.
    """
    current = _validate_scene(scene)
    if not isinstance(patch, PatchRecord):
        raise ValueError("patch must be a PatchRecord")
    original = patch.model_dump(exclude={"bbox"}, warnings=False)
    validated = PatchRecord.model_validate(original)
    if validated.model_dump(exclude={"bbox"}) != original:
        raise ValueError("Patch does not match a validated patch record")
    if validated.scene_id != current.scene_id or validated.scene_checksum != current.checksum:
        raise ValueError("Patch does not match the inspected scene")
    col, row, width, height = validated.window
    if col + width > current.width or row + height > current.height:
        raise ValueError("Patch window is outside the inspected scene")
    with (
        rasterio.Env(
            GDAL_PAM_ENABLED="NO",
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            GTIFF_SRS_SOURCE="EPSG",
        ),
        rasterio.open(current.asset_path, driver="GTiff", GEOREF_SOURCES="INTERNAL") as dataset,
    ):
        pixels = _read_pixels(dataset, validated.window)
        expected = _record(current, dataset, validated.window, pixels)
    if validated != expected:
        raise ValueError("Patch record does not match reconstructed source metadata")
    return pixels
