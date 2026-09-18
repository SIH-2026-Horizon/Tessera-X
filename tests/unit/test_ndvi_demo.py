import importlib.util
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location(
    "ndvi_demo", Path(__file__).resolve().parents[2] / "scripts" / "ndvi_demo.py"
)
ndvi_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ndvi_demo)


def test_known_calibrated_values():
    result = ndvi_demo.compute_ndvi(
        np.array([2000, 4000, 2000], dtype=np.uint16),
        np.array([4000, 2000, 2000], dtype=np.uint16),
        (0.0001, -0.1),
        (0.0001, -0.1),
    )
    np.testing.assert_allclose(result, [0.5, -0.5, 0])
    assert result.count() == 3


def test_masks_zero_denominator_and_nonfinite_values():
    red = np.ma.array([2000, 0, 2000, 1000, np.nan, 2000, 900], mask=[0, 1, 0, 0, 0, 0, 0])
    nir = np.ma.array([4000, 4000, 0, 1000, 4000, np.inf, 1100], mask=[0, 0, 1, 0, 0, 0, 0])
    with np.errstate(all="raise"):
        result = ndvi_demo.compute_ndvi(red, nir, (0.0001, -0.1), (0.0001, -0.1))
    np.testing.assert_array_equal(result.mask, [False, True, True, True, True, True, True])
    np.testing.assert_allclose(result.compressed(), [0.5])
