"""Offline STAC 1.0 Item serialization; no network schema resolution."""

from pathlib import Path

from rasterio.crs import CRS

from .record import SceneRecord


def scene_item(scene: SceneRecord, *, cog_prepared: bool = False) -> dict:
    """Serialize explicit source metadata, without mistaking a layout hint for validation."""
    if cog_prepared and not scene.cog_layout_hint:
        raise ValueError("Prepared COG must have a COG layout")
    properties = {
        "datetime": scene.acquisition_time.isoformat().replace("+00:00", "Z"),
        "platform": scene.platform,
        "instruments": [scene.sensor],
        "gsd": scene.gsd,
        "proj:epsg": CRS.from_user_input(scene.crs).to_epsg(),
        "proj:shape": [scene.height, scene.width],
        "proj:transform": [*scene.transform, 0, 0, 1],
        "tessera:ingestion_release": scene.ingestion_release,
        "tessera:cog_prepared": cog_prepared,
    }
    if scene.cloud_cover is not None:
        properties["eo:cloud_cover"] = scene.cloud_cover * 100
    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/projection/v1.1.0/schema.json",
            "https://stac-extensions.github.io/eo/v1.1.0/schema.json",
        ],
        "id": scene.scene_id,
        "geometry": scene.footprint.model_dump(mode="json"),
        "bbox": list(scene.bbox),
        "properties": properties,
        "links": [],
        "assets": {
            "image": {
                "href": Path(scene.asset_path).resolve().as_uri(),
                "type": "image/tiff; application=geotiff",
                "roles": ["data"],
                "tessera:sha256": scene.checksum,
                "tessera:scales": list(scene.scales),
                "tessera:offsets": list(scene.offsets),
                "tessera:nodata": list(scene.nodata),
            }
        },
    }
