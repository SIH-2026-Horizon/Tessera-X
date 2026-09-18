import argparse
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.windows import Window


def compute_ndvi(red, nir, red_calibration, nir_calibration):
    red = np.ma.asarray(red, dtype=np.float64)
    nir = np.ma.asarray(nir, dtype=np.float64)
    red_reflectance = red.data * red_calibration[0] + red_calibration[1]
    nir_reflectance = nir.data * nir_calibration[0] + nir_calibration[1]
    denominator = nir_reflectance + red_reflectance
    valid = (
        ~np.ma.getmaskarray(red)
        & ~np.ma.getmaskarray(nir)
        & np.isfinite(red_reflectance)
        & np.isfinite(nir_reflectance)
        & ~np.isclose(denominator, 0, rtol=0, atol=1e-12)
    )
    ndvi = np.zeros(red.shape, dtype=np.float64)
    np.divide(nir_reflectance - red_reflectance, denominator, out=ndvi, where=valid)
    return np.ma.array(ndvi, mask=~valid | ~np.isfinite(ndvi))


def main():
    parser = argparse.ArgumentParser(description="Windowed calibrated NDVI demo")
    parser.add_argument("--red", type=Path, default=Path("data/demo/S2B_T44PMU_20241026_B04.tif"))
    parser.add_argument("--nir", type=Path, default=Path("data/demo/S2B_T44PMU_20241026_B08.tif"))
    parser.add_argument("--output", type=Path, default=Path("data/demo/ndvi_2024.png"))
    args = parser.parse_args()
    if not args.red.is_file() or not args.nir.is_file():
        parser.error("Both inputs must be existing local raster files")
    if args.output.suffix.lower() != ".png" or not args.output.parent.is_dir():
        parser.error("Output must be a .png in an existing directory")
    with rasterio.open(args.red) as red, rasterio.open(args.nir) as nir:
        if (
            red.shape != nir.shape
            or red.crs is None
            or red.crs != nir.crs
            or red.transform != nir.transform
            or red.count != 1
            or nir.count != 1
        ):
            parser.error(
                "Inputs must be aligned single-band rasters "
                "with matching dimensions, CRS and transforms"
            )
        calibrations = [(band.scales[0], band.offsets[0]) for band in (red, nir)]
        for name, calibration in zip(("B04", "B08"), calibrations, strict=False):
            if not np.allclose(calibration, (0.0001, -0.1), rtol=0, atol=1e-12):
                parser.error(
                    f"Unexpected {name} calibration: {calibration}; expected Sentinel-2 C1 metadata"
                )
            print(
                f"{name}: reflectance = DN * {calibration[0]} + ({calibration[1]}); "
                "source=raster metadata"
            )
        width, height = min(256, red.width), min(256, red.height)
        window = Window((red.width - width) // 2, (red.height - height) // 2, width, height)
        ndvi = compute_ndvi(
            red.read(1, window=window, masked=True),
            nir.read(1, window=window, masked=True),
            *calibrations,
        )
        print(f"Window: {window}; CRS: {red.crs}; alignment verified")
    values = ndvi.compressed()
    if not values.size:
        parser.error("Window contains no valid NDVI pixels")
    gray = np.rint((np.clip(ndvi.filled(0), -1, 1) + 1) * 127.5).astype(np.uint8)
    rgba = np.stack((gray, gray, gray, (~np.ma.getmaskarray(ndvi)).astype(np.uint8) * 255), axis=-1)
    Image.fromarray(rgba).save(args.output, format="PNG")
    with Image.open(args.output) as image:
        image.verify()
    with Image.open(args.output) as image:
        image.load()
        if image.mode != "RGBA" or not np.array_equal(np.asarray(image), rgba):
            raise RuntimeError("PNG round-trip verification failed")
    print(
        f"Valid pixels: {values.size}/{ndvi.size}; min={values.min():.8f}; max={values.max():.8f}"
    )
    print(f"PNG verified: {args.output.resolve()} ({args.output.stat().st_size} bytes)")
    print(
        "Display: -1=black, 0=mid-gray, +1=white; "
        "out-of-range values clipped for display only; invalid=transparent"
    )


if __name__ == "__main__":
    main()
