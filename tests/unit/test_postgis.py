"""SQL-contract tests using a recording fake, NOT PostGIS integration tests."""

import json
from contextlib import contextmanager
from copy import deepcopy
from importlib import import_module, resources

import pytest

from tessera_x.ingestion.record import SceneRecord


class DumpRecord:
    """Patch serializer stand-in, independent of the patch extractor's raster I/O."""

    def __init__(self, payload):
        self.payload = payload

    def model_dump(self, *, mode):
        assert mode == "json"
        return deepcopy(self.payload)


class RecordingConnection:
    def __init__(self, results=(), fail_on=None):
        self.calls = []
        self.results = iter(results)
        self.events = []
        self.fail_on = fail_on

    @contextmanager
    def transaction(self):
        self.events.append("begin")
        try:
            yield
        except Exception:
            self.events.append("rollback")
            raise
        else:
            self.events.append("commit")

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("database write failed")
        return self

    def fetchone(self):
        return next(self.results)

    def fetchall(self):
        return next(self.results)


@pytest.fixture
def scene():
    return SceneRecord(
        scene_id="scene-'quoted'",
        platform="test-platform",
        sensor="test-sensor",
        acquisition_time="2026-01-01T00:00:00Z",
        ingestion_release="v1",
        cloud_cover=0.2,
        footprint={
            "coordinates": (((75.0, 18.0), (75.1, 18.0), (75.1, 18.1), (75.0, 18.1), (75.0, 18.0)),)
        },
        crs="EPSG:32643",
        gsd=10.0,
        asset_path="/local/test.tif",
        checksum="a" * 64,
        width=32,
        height=48,
        count=1,
        transform=(10.0, 0.0, 500000.0, 0.0, -10.0, 2000000.0),
        scales=(1.0,),
        offsets=(0.0,),
        nodata=(None,),
        tiled=True,
        cog_layout_hint=False,
    )


@pytest.fixture
def patch(scene):
    data = scene.model_dump(mode="json")
    return DumpRecord(
        {
            "patch_id": "patch-1",
            "scene_id": scene.scene_id,
            "scene_checksum": scene.checksum,
            "pixel_window": [0, 0, 16, 16],
            "footprint": data["footprint"],
            "bbox": data["bbox"],
            "timestamp": data["acquisition_time"],
            "quality_score": 0.75,
        }
    )


def adapter():
    return import_module("tessera_x.ingestion.postgis")


def test_initialize_uses_packaged_schema_and_transaction():
    connection = RecordingConnection()
    adapter().initialize_database(connection)
    schema = resources.files("tessera_x.ingestion").joinpath("schema.sql").read_text()
    assert connection.calls == [(schema, None)]
    assert connection.events == ["begin", "commit"]
    assert "DROP " not in schema.upper()
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in schema
    assert schema.count("geometry(Polygon, 4326)") == 2
    assert schema.count("USING GIST (footprint)") == 2
    assert "REFERENCES tessera_scenes" in schema
    assert "pixel_col <= scene_width - pixel_width" in schema
    assert "pixel_row <= scene_height - pixel_height" in schema
    assert "TIMESTAMPTZ" in schema and "quality_score" in schema


def test_register_parameterizes_full_payloads(scene, patch):
    connection = RecordingConnection(results=[(scene.scene_id,)])
    assert adapter().register_scene(connection, scene, [patch]) is True
    assert connection.events == ["begin", "commit"]
    scene_sql, scene_params = connection.calls[0]
    assert "INSERT INTO tessera_scenes" in scene_sql
    assert "ON CONFLICT (scene_id) DO NOTHING" in scene_sql
    assert scene.scene_id not in scene_sql
    assert json.loads(scene_params["payload"]) == scene.model_dump(mode="json")
    assert json.loads(scene_params["footprint"]) == scene.model_dump(mode="json")["footprint"]
    patch_sql, patch_params = connection.calls[1]
    assert "INSERT INTO tessera_patches" in patch_sql
    assert "ST_GeomFromGeoJSON" in patch_sql
    assert patch_params["pixel_col"] == 0
    assert patch_params["pixel_width"] == 16
    assert patch_params["scene_width"] == 32
    assert patch_params["sensor"] == scene.sensor
    assert json.loads(patch_params["payload"]) == patch.model_dump(mode="json")


def test_identical_full_payload_is_idempotent(scene, patch):
    connection = RecordingConnection(
        results=[
            None,
            (scene.model_dump(mode="json"),),
            [(patch.model_dump(mode="json"),)],
        ]
    )
    assert adapter().register_scene(connection, scene, [patch]) is False
    assert len(connection.calls) == 3
    assert "FOR UPDATE" in connection.calls[1][0]
    assert connection.events == ["begin", "commit"]


@pytest.mark.parametrize("field,value", [("asset_path", "/changed.tif"), ("cloud_cover", 0.3)])
def test_same_id_different_scene_payload_conflicts(scene, patch, field, value):
    previous = scene.model_dump(mode="json")
    previous[field] = value
    connection = RecordingConnection(results=[None, (previous,)])
    with pytest.raises(adapter().SceneConflictError, match="Scene ID conflict"):
        adapter().register_scene(connection, scene, [patch])
    assert connection.events == ["begin", "rollback"]


@pytest.mark.parametrize("change", ["changed", "missing", "extra"])
def test_same_scene_different_patch_set_conflicts(scene, patch, change):
    previous = patch.model_dump(mode="json")
    previous["quality_score"] = 0.25
    stored = {
        "changed": [(previous,)],
        "missing": [],
        "extra": [(patch.model_dump(mode="json"),), (previous,)],
    }[change]
    connection = RecordingConnection(results=[None, (scene.model_dump(mode="json"),), stored])
    with pytest.raises(adapter().SceneConflictError):
        adapter().register_scene(connection, scene, [patch])
    assert connection.events[-1] == "rollback"


def test_patch_database_failure_escapes_transaction(scene, patch):
    connection = RecordingConnection(
        results=[(scene.scene_id,)], fail_on="INSERT INTO tessera_patches"
    )
    with pytest.raises(RuntimeError, match="database write failed"):
        adapter().register_scene(connection, scene, [patch])
    assert connection.events == ["begin", "rollback"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("scene_id", "other"),
        ("scene_checksum", "b" * 64),
        ("timestamp", "2025-01-01T00:00:00Z"),
        ("sensor", "different-sensor"),
        ("pixel_window", [-1, 0, 16, 16]),
        ("pixel_window", [0, 40, 16, 16]),
        ("pixel_window", [20, 0, 16, 16]),
        ("pixel_window", [0, 0, 0, 16]),
        ("pixel_window", [0.5, 0, 16, 16]),
        ("pixel_window", [True, 0, 16, 16]),
        ("pixel_window", [0, 0, 16]),
        ("quality_score", float("nan")),
        ("quality_score", 1.1),
        ("quality_score", True),
        ("bbox", [0, 0, 1, 1]),
        ("patch_id", ""),
    ],
)
def test_invalid_patch_is_rejected_before_sql(scene, patch, field, value):
    patch.payload[field] = value
    connection = RecordingConnection()
    with pytest.raises(ValueError):
        adapter().register_scene(connection, scene, [patch])
    assert connection.calls == []


def test_repeated_patch_id_is_rejected_before_sql(scene, patch):
    connection = RecordingConnection()
    with pytest.raises(ValueError, match="Duplicate patch_id"):
        adapter().register_scene(connection, scene, [patch, patch])
    assert connection.calls == []


def test_tuple_and_named_pixel_window_are_explicitly_supported(scene, patch):
    for window in [(0, 0, 16, 16), {"col": 0, "row": 0, "width": 16, "height": 16}]:
        patch.payload["pixel_window"] = window
        connection = RecordingConnection(results=[(scene.scene_id,)])
        assert adapter().register_scene(connection, scene, [patch]) is True
        assert connection.calls[1][1]["pixel_width"] == 16


def test_empty_patch_set_is_valid(scene):
    connection = RecordingConnection(results=[(scene.scene_id,)])
    assert adapter().register_scene(connection, scene, []) is True
    assert len(connection.calls) == 1
