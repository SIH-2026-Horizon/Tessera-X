"""Caller-owned psycopg 3-style persistence; importing this module needs no driver.

Tables are resolved through the caller's trusted search_path. Bootstrap is additive,
not a schema migrator. Registration never opens an asset or a network connection.
"""

from __future__ import annotations

import json
import math
from importlib import resources
from typing import TYPE_CHECKING

from shapely.geometry import shape

from .record import Footprint, SceneRecord, SourceMetadata

if TYPE_CHECKING:
    from .patches import PatchRecord


class SceneConflictError(ValueError):
    """A scene ID already exists with different scene or patch content."""


_SCENE_INSERT = """
INSERT INTO tessera_scenes
    (scene_id, checksum, platform, sensor, acquisition_time, ingestion_release,
     cloud_cover, width, height, footprint, payload)
VALUES
    (%(scene_id)s, %(checksum)s, %(platform)s, %(sensor)s, %(acquisition_time)s,
     %(ingestion_release)s, %(cloud_cover)s, %(width)s, %(height)s,
     ST_SetSRID(ST_GeomFromGeoJSON(%(footprint)s), 4326), %(payload)s::jsonb)
ON CONFLICT (scene_id) DO NOTHING
RETURNING scene_id
"""

_PATCH_INSERT = """
INSERT INTO tessera_patches
    (patch_id, scene_id, scene_checksum, scene_width, scene_height, sensor,
     timestamp, pixel_col, pixel_row, pixel_width, pixel_height,
     quality_score, footprint, payload)
VALUES
    (%(patch_id)s, %(scene_id)s, %(scene_checksum)s, %(scene_width)s,
     %(scene_height)s, %(sensor)s, %(timestamp)s, %(pixel_col)s, %(pixel_row)s,
     %(pixel_width)s, %(pixel_height)s, %(quality_score)s,
     ST_SetSRID(ST_GeomFromGeoJSON(%(footprint)s), 4326), %(payload)s::jsonb)
"""


def initialize_database(connection) -> None:
    """Install packaged tables/indexes and PostGIS without deleting existing data.

    Requires CREATE privileges (or PostGIS already installed). The caller owns
    connection lifetime, credentials, search_path and any enclosing transaction.
    """
    schema = resources.files("tessera_x.ingestion").joinpath("schema.sql").read_text("utf-8")
    with connection.transaction():
        connection.execute(schema)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _window(value: object, scene: SceneRecord) -> tuple[int, int, int, int]:
    # JSON model dumps turn the preferred (col, row, width, height) tuple into a list.
    if isinstance(value, dict) and set(value) == {"col", "row", "width", "height"}:
        value = tuple(value[key] for key in ("col", "row", "width", "height"))
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        raise ValueError("pixel_window must contain col, row, width, height")
    if any(type(number) is not int for number in value):
        raise ValueError("pixel_window values must be integers, not booleans or fractions")
    col, row, width, height = value
    if (
        col < 0
        or row < 0
        or width <= 0
        or height <= 0
        or col > scene.width - width
        or row > scene.height - height
    ):
        raise ValueError("pixel_window is outside scene dimensions")
    return col, row, width, height


def _patch_params(data: dict, scene: SceneRecord) -> dict:
    try:
        if data["scene_id"] != scene.scene_id or data["scene_checksum"] != scene.checksum:
            raise ValueError("Patch scene_id/checksum does not match parent scene")
        for field in ("sensor", "platform", "crs", "gsd", "ingestion_release", "asset_path"):
            if field in data and data[field] != getattr(scene, field):
                raise ValueError(f"Patch {field} does not match parent scene")
        timestamp = SourceMetadata.explicit_timestamp(
            data["timestamp"] if "timestamp" in data else data["acquisition_time"]
        )
        if timestamp != scene.acquisition_time:
            raise ValueError("Patch timestamp does not match parent scene")
        if "acquisition_time" in data and (
            SourceMetadata.explicit_timestamp(data["acquisition_time"]) != timestamp
        ):
            raise ValueError("Patch acquisition_time does not match timestamp")
        patch_id = data["patch_id"]
        if not isinstance(patch_id, str) or not patch_id.strip() or "\x00" in patch_id:
            raise ValueError("patch_id must be nonempty text")
        col, row, width, height = _window(
            data["pixel_window"] if "pixel_window" in data else data["window"], scene
        )
        quality = data["quality_score"]
        if (
            isinstance(quality, bool)
            or not isinstance(quality, (int, float))
            or not math.isfinite(quality)
            or not 0 <= quality <= 1
        ):
            raise ValueError("quality_score must be finite and between zero and one")
        footprint = Footprint.model_validate(data["footprint"])
        polygon = shape(footprint.model_dump(mode="json"))
        if tuple(data["bbox"]) != polygon.bounds:
            raise ValueError("Patch bbox does not match footprint")
        return {
            "patch_id": patch_id,
            "scene_id": scene.scene_id,
            "scene_checksum": scene.checksum,
            "scene_width": scene.width,
            "scene_height": scene.height,
            "sensor": scene.sensor,
            "timestamp": timestamp,
            "pixel_col": col,
            "pixel_row": row,
            "pixel_width": width,
            "pixel_height": height,
            "quality_score": quality,
            "footprint": _canonical(data["footprint"]),
            "payload": _canonical(data),
        }
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError("Invalid patch metadata") from error


def _payload(row):
    """Accept psycopg's default tuple rows and its optional dict row factory."""
    value = row["payload"] if isinstance(row, dict) else row[0]
    return json.loads(value) if isinstance(value, str) else value


def register_scene(connection, scene: SceneRecord, patches: list[PatchRecord]) -> bool:
    """Atomically register a scene and its complete patch set.

    Return True for an insertion, False for an identical retry (patch order is
    irrelevant). Raise SceneConflictError for an existing ID with different full
    payloads; database exceptions propagate and roll back this transaction/savepoint.
    At READ COMMITTED, ON CONFLICT serializes competing scene registrations; callers
    using stronger isolation must retry serialization failures themselves.

    Metadata checks cover parent identity/checksum/timestamp, integer windows,
    geometry validity, bbox, quality range and optional inherited fields. This is
    not proof that patches were extracted from raster bytes: use trusted extractor
    output or verify it upstream. No raster I/O or quality recomputation is done.
    """
    # Revalidate even model_copy/model_construct objects, which can bypass Pydantic.
    scene = SceneRecord.model_validate(scene.model_dump(exclude={"bbox"}))
    scene_data = scene.model_dump(mode="json")
    scene_params = {
        **scene_data,
        "payload": _canonical(scene_data),
        "footprint": _canonical(scene_data["footprint"]),
    }
    patch_params = [_patch_params(patch.model_dump(mode="json"), scene) for patch in patches]
    ids = [params["patch_id"] for params in patch_params]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate patch_id in registration")
    expected = sorted(
        (json.loads(params["payload"]) for params in patch_params),
        key=lambda data: data["patch_id"],
    )
    with connection.transaction():
        inserted = connection.execute(_SCENE_INSERT, scene_params).fetchone()
        if inserted is None:
            row = connection.execute(
                "SELECT payload FROM tessera_scenes WHERE scene_id = %s FOR UPDATE",
                (scene.scene_id,),
            ).fetchone()
            if row is None or _payload(row) != scene_data:
                raise SceneConflictError("Scene ID conflict: scene payload differs")
            rows = connection.execute(
                "SELECT payload FROM tessera_patches WHERE scene_id = %s ORDER BY patch_id",
                (scene.scene_id,),
            ).fetchall()
            # Sort in Python too: database collation may differ from Unicode ordering.
            existing = sorted((_payload(row) for row in rows), key=lambda data: data["patch_id"])
            if existing != expected:
                raise SceneConflictError("Scene ID conflict: patch payloads differ")
            return False
        for params in patch_params:
            connection.execute(_PATCH_INSERT, params)
    return True
