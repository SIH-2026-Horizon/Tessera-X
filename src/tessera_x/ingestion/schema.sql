-- Phase 1 additive bootstrap, not a migration mechanism for incompatible schemas.
-- Run in a caller-controlled schema/search_path with CREATE privileges.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS tessera_scenes (
    scene_id TEXT PRIMARY KEY CHECK (length(btrim(scene_id)) > 0),
    checksum TEXT NOT NULL CHECK (checksum ~ '^[0-9a-fA-F]{64}$'),
    platform TEXT NOT NULL,
    sensor TEXT NOT NULL,
    acquisition_time TIMESTAMPTZ NOT NULL,
    ingestion_release TEXT NOT NULL,
    cloud_cover DOUBLE PRECISION CHECK (cloud_cover >= 0 AND cloud_cover <= 1),
    width BIGINT NOT NULL CHECK (width > 0),
    height BIGINT NOT NULL CHECK (height > 0),
    footprint geometry(Polygon, 4326) NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CHECK (ST_IsValid(footprint) AND NOT ST_IsEmpty(footprint) AND ST_Area(footprint) > 0),
    CHECK (ST_CoveredBy(footprint, ST_MakeEnvelope(-180, -90, 180, 90, 4326))),
    -- The composite key lets patch checks use parent dimensions without a trigger.
    UNIQUE (scene_id, checksum, width, height, sensor, acquisition_time)
);

CREATE INDEX IF NOT EXISTS tessera_scenes_footprint_gist
    ON tessera_scenes USING GIST (footprint);
CREATE INDEX IF NOT EXISTS tessera_scenes_sensor_time_idx
    ON tessera_scenes (sensor, acquisition_time);

CREATE TABLE IF NOT EXISTS tessera_patches (
    patch_id TEXT PRIMARY KEY CHECK (length(btrim(patch_id)) > 0),
    scene_id TEXT NOT NULL,
    scene_checksum TEXT NOT NULL,
    scene_width BIGINT NOT NULL,
    scene_height BIGINT NOT NULL,
    sensor TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    pixel_col BIGINT NOT NULL CHECK (pixel_col >= 0),
    pixel_row BIGINT NOT NULL CHECK (pixel_row >= 0),
    pixel_width BIGINT NOT NULL CHECK (pixel_width > 0),
    pixel_height BIGINT NOT NULL CHECK (pixel_height > 0),
    quality_score DOUBLE PRECISION NOT NULL CHECK (quality_score >= 0 AND quality_score <= 1),
    footprint geometry(Polygon, 4326) NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    CHECK (pixel_col <= scene_width - pixel_width),
    CHECK (pixel_row <= scene_height - pixel_height),
    CHECK (ST_IsValid(footprint) AND NOT ST_IsEmpty(footprint) AND ST_Area(footprint) > 0),
    CHECK (ST_CoveredBy(footprint, ST_MakeEnvelope(-180, -90, 180, 90, 4326))),
    FOREIGN KEY (scene_id, scene_checksum, scene_width, scene_height, sensor, timestamp)
        REFERENCES tessera_scenes (scene_id, checksum, width, height, sensor, acquisition_time)
        ON DELETE RESTRICT ON UPDATE RESTRICT
);

CREATE INDEX IF NOT EXISTS tessera_patches_scene_idx ON tessera_patches (scene_id);
CREATE INDEX IF NOT EXISTS tessera_patches_footprint_gist
    ON tessera_patches USING GIST (footprint);
CREATE INDEX IF NOT EXISTS tessera_patches_sensor_time_idx
    ON tessera_patches (sensor, timestamp);
CREATE INDEX IF NOT EXISTS tessera_patches_quality_idx ON tessera_patches (quality_score);
