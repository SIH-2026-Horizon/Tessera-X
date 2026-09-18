"""Real-PostGIS round trip; skipped unless TESSERA_X_TEST_DB_URL is set."""

import json
import os
import uuid

import pytest

pytest.importorskip("psycopg")
pytestmark = pytest.mark.skipif(
    not os.environ.get("TESSERA_X_TEST_DB_URL"), reason="TESSERA_X_TEST_DB_URL not set"
)


@pytest.fixture
def connection():
    import psycopg
    from psycopg import sql

    from tessera_x.ingestion import postgis

    # DDL and test rows are rolled back, including on assertion failures. Never
    # touch pre-existing application tables or rely on their contents.
    with (
        psycopg.connect(os.environ["TESSERA_X_TEST_DB_URL"]) as connection,
        connection.transaction(force_rollback=True),
    ):
        namespace = "tessera_test_" + uuid.uuid4().hex
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(namespace)))
        connection.execute(
            sql.SQL("SET LOCAL search_path TO {}, public").format(sql.Identifier(namespace))
        )
        postgis.initialize_database(connection)
        postgis.initialize_database(connection)
        yield connection


@pytest.fixture
def scene():
    from tessera_x.ingestion.record import SceneRecord

    return SceneRecord(
        scene_id=f"integration-{uuid.uuid4().hex}",
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


class DumpPatch:
    def __init__(self, payload):
        self.payload = payload

    def model_dump(self, *, mode):
        assert mode == "json"
        return dict(self.payload)


@pytest.fixture
def patch(scene):
    payload = scene.model_dump(mode="json")
    payload.update(
        {
            "patch_id": "integration-patch",
            "scene_id": scene.scene_id,
            "scene_checksum": scene.checksum,
            "pixel_window": (0, 0, 16, 16),
            "timestamp": payload["acquisition_time"],
            "quality_score": 0.75,
        }
    )
    return DumpPatch(payload)


def count_scenes(connection, scene_id):
    cursor = connection.execute(
        "SELECT count(*) FROM tessera_scenes WHERE scene_id = %s", (scene_id,)
    )
    return cursor.fetchone()[0]


def count_patches(connection, scene_id):
    cursor = connection.execute(
        "SELECT count(*) FROM tessera_patches WHERE scene_id = %s", (scene_id,)
    )
    return cursor.fetchone()[0]


@pytest.mark.parametrize("rotation", [0, 17])
def test_real_extraction_roundtrip(connection, tmp_path, rotation):
    import numpy as np
    import rasterio
    from rasterio import Affine

    from tessera_x.ingestion import postgis
    from tessera_x.ingestion.inspection import inspect_scene
    from tessera_x.ingestion.patches import PatchRecord, extract_patches, read_patch

    path = tmp_path / "source.tif"
    values = np.arange(1, 2 * 19 * 17 + 1, dtype="uint16").reshape(2, 19, 17)
    values[0, 0, 0] = 0
    values[1, 0, 1] = 0
    values[:, 16:, 16:] = 0
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=17,
        height=19,
        count=2,
        dtype="uint16",
        nodata=0,
        crs="EPSG:32644",
        transform=Affine.translation(500000, 1400000)
        @ Affine.rotation(rotation)
        @ Affine.scale(10, -10),
    ) as destination:
        destination.write(values)
    scene = inspect_scene(
        path,
        scene_id=f"extracted-{uuid.uuid4().hex}",
        platform="test-platform",
        sensor="test-sensor",
        acquisition_time="2026-01-01T05:30:00.123456+05:30",
        ingestion_release="v1",
    )
    patches = extract_patches(scene, patch_size=8)
    assert [patch.window for patch in patches] == [
        (0, 0, 8, 8),
        (8, 0, 8, 8),
        (16, 0, 1, 8),
        (0, 8, 8, 8),
        (8, 8, 8, 8),
        (16, 8, 1, 8),
        (0, 16, 8, 3),
        (8, 16, 8, 3),
        (16, 16, 1, 3),
    ]
    assert patches[0].quality_score == 62 / 64
    assert patches[-1].quality_score == 0
    # Exercise the extractor's actual field names, not the legacy test doubles.
    assert "window" in patches[0].model_dump(mode="json")
    assert "pixel_window" not in patches[0].model_dump(mode="json")
    assert "timestamp" not in patches[0].model_dump(mode="json")
    assert postgis.register_scene(connection, scene, patches) is True
    assert (
        postgis.register_scene(
            connection, scene, list(reversed(extract_patches(scene, patch_size=8)))
        )
        is False
    )
    assert count_scenes(connection, scene.scene_id) == 1
    assert count_patches(connection, scene.scene_id) == 9
    assert connection.execute(
        "SELECT payload FROM tessera_scenes WHERE scene_id = %s", (scene.scene_id,)
    ).fetchone()[0] == scene.model_dump(mode="json")

    rows = connection.execute(
        "SELECT payload, pixel_col, pixel_row, pixel_width, pixel_height, timestamp,"
        " quality_score, scene_checksum, sensor, scene_width, scene_height,"
        " ST_AsGeoJSON(footprint, 15), ST_SRID(footprint), GeometryType(footprint),"
        " ST_IsValid(footprint) FROM tessera_patches WHERE scene_id = %s"
        " ORDER BY pixel_row, pixel_col",
        (scene.scene_id,),
    ).fetchall()
    for row, patch in zip(rows, patches, strict=True):
        assert row[0] == patch.model_dump(mode="json")
        assert row[1:5] == patch.window
        assert row[5] == scene.acquisition_time
        assert row[6] == patch.quality_score
        assert row[7:11] == (scene.checksum, scene.sensor, 17, 19)
        geometry = json.loads(row[11])
        assert geometry["type"] == "Polygon"
        assert len(geometry["coordinates"]) == 1
        for actual, expected in zip(
            geometry["coordinates"][0], patch.footprint.coordinates[0], strict=True
        ):
            assert actual == pytest.approx(expected, abs=1e-12, rel=0)
        assert row[12:] == (4326, "POLYGON", True)

        # Persisted JSON can reconstruct a real PatchRecord and its masked pixels.
        restored = PatchRecord.model_validate_json(
            json.dumps({key: value for key, value in row[0].items() if key != "bbox"})
        )
        assert restored == patch
        pixels = read_patch(scene, restored)
        col, top, width, height = patch.window
        expected_pixels = values[:, top : top + height, col : col + width]
        np.testing.assert_array_equal(pixels.data, expected_pixels)
        np.testing.assert_array_equal(np.ma.getmaskarray(pixels), expected_pixels == 0)

    with pytest.raises(postgis.SceneConflictError, match="patch payloads differ"):
        postgis.register_scene(connection, scene, patches[:-1])
    assert count_patches(connection, scene.scene_id) == 9


def test_geometry_roundtrip_duplicate_and_rollback(connection, scene, patch):
    from tessera_x.ingestion import postgis

    with connection.transaction():
        assert postgis.register_scene(connection, scene, [patch]) is True

    with connection.transaction():
        assert postgis.register_scene(connection, scene, [patch]) is False
        assert count_scenes(connection, scene.scene_id) == 1
        assert count_patches(connection, scene.scene_id) == 1

    cursor = connection.execute(
        "SELECT ST_AsGeoJSON(footprint) FROM tessera_scenes WHERE scene_id = %s",
        (scene.scene_id,),
    )
    ring = json.loads(cursor.fetchone()[0])["coordinates"][0]
    expected = [list(point) for point in scene.footprint.coordinates[0]]
    for (actual_x, actual_y), (x, y) in zip(ring, expected, strict=True):
        assert (actual_x, actual_y) == pytest.approx((x, y), rel=1e-12)

    cursor = connection.execute(
        "SELECT ST_SRID(footprint), GeometryType(footprint) FROM tessera_scenes"
        " WHERE scene_id = %s",
        (scene.scene_id,),
    )
    assert cursor.fetchone() == (4326, "POLYGON")
    row = connection.execute(
        "SELECT ST_AsGeoJSON(footprint, 15), ST_SRID(footprint), payload, quality_score"
        " FROM tessera_patches WHERE scene_id = %s",
        (scene.scene_id,),
    ).fetchone()
    assert json.loads(row[0]) == scene.footprint.model_dump(mode="json")
    assert row[1] == 4326
    assert row[2] == json.loads(json.dumps(patch.model_dump(mode="json")))
    assert row[3] == 0.75
    assert connection.execute(
        "SELECT payload FROM tessera_scenes WHERE scene_id = %s", (scene.scene_id,)
    ).fetchone()[0] == scene.model_dump(mode="json")

    with pytest.raises(postgis.SceneConflictError):
        postgis.register_scene(connection, scene, [])

    with pytest.raises(postgis.SceneConflictError), connection.transaction():
        postgis.register_scene(connection, scene.model_copy(update={"cloud_cover": 0.5}), [patch])
    with connection.transaction():
        cursor = connection.execute("SELECT count(*) FROM tessera_scenes WHERE cloud_cover = 0.5")
        assert cursor.fetchone()[0] == 0

    with pytest.raises(ValueError, match="outside scene dimensions"), connection.transaction():
        bad = DumpPatch(patch.payload | {"pixel_window": [40, 40, 16, 16]})
        postgis.register_scene(connection, scene, [bad])
    with connection.transaction():
        assert count_patches(connection, scene.scene_id) == 1

    # A patch primary-key violation happens after a new scene INSERT. Both must
    # roll back, while the original registered scene remains intact.
    import psycopg

    second = scene.model_copy(update={"scene_id": scene.scene_id + "-second"})
    colliding = DumpPatch(patch.payload | {"scene_id": second.scene_id})
    with pytest.raises(psycopg.errors.UniqueViolation):
        postgis.register_scene(connection, second, [colliding])
    assert count_scenes(connection, second.scene_id) == 0
    assert count_patches(connection, second.scene_id) == 0
    assert count_scenes(connection, scene.scene_id) == 1
    assert count_patches(connection, scene.scene_id) == 1

    with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
        connection.execute(
            "UPDATE tessera_patches SET pixel_col = 32 WHERE scene_id = %s",
            (scene.scene_id,),
        )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), connection.transaction():
        connection.execute(
            "UPDATE tessera_patches SET scene_checksum = %s WHERE scene_id = %s",
            ("b" * 64, scene.scene_id),
        )
