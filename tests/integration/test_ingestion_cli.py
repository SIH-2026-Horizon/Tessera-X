import json
import subprocess
import sys

import numpy as np
import rasterio
from rasterio import Affine


def run(*args):
    return subprocess.run(
        [sys.executable, "-m", "tessera_x.ingestion", *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_ingest_and_show_cli(tmp_path):
    path = tmp_path / "source.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=8,
        height=8,
        count=1,
        dtype="uint16",
        crs="EPSG:32644",
        transform=Affine(10, 0, 500000, 0, -10, 1400000),
    ) as dst:
        dst.write(np.ones((1, 8, 8), dtype="uint16"))
    root = tmp_path / "archive"
    result = run(
        "ingest",
        path,
        "--store",
        root,
        "--patch-size",
        4,
        "--scene-id",
        "test",
        "--platform",
        "local",
        "--sensor",
        "optical",
        "--acquisition-time",
        "2024-01-01T00:00:00Z",
        "--ingestion-release",
        "v1",
    )
    assert result.returncode == 0, result.stderr
    bundle = json.loads(result.stdout)
    assert len(bundle["patches"]) == 4
    shown = run("show", "test", "--store", root)
    assert shown.returncode == 0, shown.stderr
    assert json.loads(shown.stdout) == bundle
    missing = run("show", "missing", "--store", root)
    assert missing.returncode == 2
    assert not missing.stdout
    assert json.loads(missing.stderr)["error"]["code"] == "ingestion_failed"
    prepared = run(
        "prepare-cog",
        path,
        tmp_path / "prepared.tif",
        "--scene-id",
        "prepared",
        "--platform",
        "local",
        "--sensor",
        "optical",
        "--acquisition-time",
        "2024-01-01T00:00:00Z",
        "--ingestion-release",
        "v1",
    )
    assert prepared.returncode == 0, prepared.stderr
    assert json.loads(prepared.stdout)["cog_layout_hint"] is True
