import math
import re
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    field_validator,
    model_validator,
)
from rasterio.crs import CRS
from rasterio.errors import CRSError
from shapely.geometry import Polygon

Identity = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, strict=True)]
PositiveMetres = Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)]
Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False, strict=True)]
StrictFiniteFloat = Annotated[float, Field(allow_inf_nan=False, strict=True)]
Point = tuple[StrictFiniteFloat, StrictFiniteFloat]
StrictBool = Annotated[bool, Field(strict=True)]


def local_path(value: str | Path) -> Path:
    text = str(value)
    if (
        not text.strip()
        or "\x00" in text
        or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", text)
        or text.startswith(("/vsi", "//", "\\\\"))
    ):
        raise ValueError("Only local filesystem paths are supported")
    return Path(text)


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scene_id: Identity
    platform: Identity
    sensor: Identity
    acquisition_time: datetime
    ingestion_release: Identity
    cloud_cover: Fraction | None = None

    @field_validator("acquisition_time", mode="before")
    @classmethod
    def explicit_timestamp(cls, value: object) -> datetime:
        if isinstance(value, str):
            if not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})",
                value,
            ):
                raise ValueError("Use an ISO timestamp with seconds and an explicit timezone")
            if value.endswith("-00:00") or (
                not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59)
            ):
                raise ValueError("Timezone offset must be known and valid")
            value = datetime.fromisoformat(value)
        if not isinstance(value, datetime) or value.utcoffset() is None:
            raise ValueError("An explicit timezone-aware acquisition timestamp is required")
        return value.astimezone(UTC)


class Footprint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["Polygon"] = "Polygon"
    coordinates: tuple[tuple[Point, ...]]

    @model_validator(mode="after")
    def valid_perimeter(self) -> Self:
        ring = self.coordinates[0]
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("Footprint must be a closed ring")
        if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in ring):
            raise ValueError("Footprint coordinates are outside EPSG:4326 bounds")
        if any(abs(a[0] - b[0]) > 180 for a, b in pairwise(ring)):
            raise ValueError("Antimeridian footprints are unsupported")
        polygon = Polygon(ring)
        if not polygon.is_valid or polygon.is_empty or polygon.area <= 0:
            raise ValueError("Footprint must be a valid nonempty polygon")
        if polygon.bounds[2] - polygon.bounds[0] > 180:
            raise ValueError("Footprints spanning more than 180 degrees are unsupported")
        return self


class SceneRecord(SourceMetadata):
    footprint: Footprint
    crs: Identity
    gsd: PositiveMetres
    asset_path: Annotated[str, Field(strict=True)]
    checksum: Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")]
    width: Annotated[int, Field(gt=0, strict=True)]
    height: Annotated[int, Field(gt=0, strict=True)]
    count: Annotated[int, Field(gt=0, strict=True)]
    transform: tuple[
        StrictFiniteFloat,
        StrictFiniteFloat,
        StrictFiniteFloat,
        StrictFiniteFloat,
        StrictFiniteFloat,
        StrictFiniteFloat,
    ]
    scales: tuple[StrictFiniteFloat, ...]
    offsets: tuple[StrictFiniteFloat, ...]
    nodata: tuple[StrictFiniteFloat | None, ...]
    tiled: StrictBool
    cog_layout_hint: StrictBool

    @field_validator("crs")
    @classmethod
    def validate_crs(cls, value: str) -> str:
        try:
            crs = CRS.from_user_input(value)
            if not crs.is_projected or crs.to_epsg() is None or crs.linear_units_factor[1] != 1:
                raise ValueError("Only EPSG projected metre CRSs are supported")
        except CRSError as error:
            raise ValueError("Invalid CRS") from error
        return crs.to_string()

    @field_validator("asset_path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return str(local_path(value))

    @model_validator(mode="after")
    def band_metadata_lengths(self) -> Self:
        if any(len(values) != self.count for values in (self.scales, self.offsets, self.nodata)):
            raise ValueError("Band metadata lengths must match count")
        return self

    @computed_field
    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs, ys = zip(*self.footprint.coordinates[0], strict=True)
        return min(xs), min(ys), max(xs), max(ys)


def finite_or_none(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) else None
