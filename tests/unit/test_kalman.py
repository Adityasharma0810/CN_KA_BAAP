"""Unit tests for the 1-D Kalman capacity estimator."""

from __future__ import annotations

import math

import pytest

from ml.estimator.kalman import KalmanCapacityFilter


def test_estimate_is_none_before_any_sample():
    kf = KalmanCapacityFilter()
    est = kf.estimate()
    assert est.capacity_mbps is None
    assert est.uncertainty_mbps is None
    assert est.samples_seen == 0
    assert est.available is False


def test_ignores_none_and_non_finite_inputs():
    kf = KalmanCapacityFilter()
    kf.update_throughput(None)
    kf.update_throughput(float("nan"))
    kf.update_throughput(-5.0)
    assert kf.estimate().samples_seen == 0


def test_converges_to_consistent_high_throughput():
    kf = KalmanCapacityFilter(process_noise=1.0, measurement_noise=4.0)
    for _ in range(40):
        kf.update_throughput(100.0)
    est = kf.estimate()
    assert est.available
    assert est.capacity_mbps == pytest.approx(100.0, abs=1.0)
    # Uncertainty should be much smaller than the capacity.
    assert est.uncertainty_mbps is not None
    assert est.uncertainty_mbps < 5.0


def test_low_throughput_keeps_higher_uncertainty():
    kf = KalmanCapacityFilter(process_noise=1.0, measurement_noise=4.0)
    for _ in range(40):
        kf.update_throughput(10.0)
    est = kf.estimate()
    # With only low throughput (far below any plausible capacity) the
    # estimate stays near 10 but uncertainty stays meaningful.
    assert est.capacity_mbps == pytest.approx(10.0, abs=2.0)
    assert est.uncertainty_mbps is not None
    assert est.uncertainty_mbps > 1.0


def test_bottleneck_is_precise_measurement():
    kf = KalmanCapacityFilter(process_noise=0.5)
    kf.update_bottleneck(50.0)
    for _ in range(40):
        kf.update_throughput(48.0)
    est = kf.estimate()
    assert est.capacity_mbps == pytest.approx(49.0, abs=2.0)
    # A declared bottleneck should pull uncertainty down quickly.
    assert est.uncertainty_mbps is not None
    assert est.uncertainty_mbps < 5.0


def test_tracks_step_change_in_capacity():
    kf = KalmanCapacityFilter(process_noise=25.0, measurement_noise=400.0)
    # High capacity phase: throughput reveals capacity is ~100.
    for _ in range(30):
        kf.update_throughput(100.0)
    assert kf.estimate().capacity_mbps == pytest.approx(100.0, abs=10.0)
    # Capacity drops: the declared bottleneck drives the estimate down
    # (throughput alone cannot prove capacity fell, only the bottleneck can).
    for _ in range(5):
        kf.update_bottleneck(20.0)
    for _ in range(30):
        kf.update_throughput(20.0)
    est = kf.estimate()
    assert est.capacity_mbps is not None
    assert est.capacity_mbps < 60.0
    assert est.capacity_mbps > 5.0


def test_high_throughput_pulls_estimate_up():
    kf = KalmanCapacityFilter()
    for _ in range(10):
        kf.update_throughput(20.0)
    early = kf.estimate()
    for _ in range(10):
        kf.update_throughput(95.0)
    late = kf.estimate()
    assert late.capacity_mbps > early.capacity_mbps
