import pytest

from gateway.policy import allocate


def test_no_contention_everyone_gets_their_demand():
    a = allocate(100, {"a": 10, "b": 20}, {"a": 1, "b": 1})
    assert a == {"a": 10, "b": 20}


def test_equal_weights_split_evenly():
    a = allocate(90, {"a": 100, "b": 100, "c": 100}, {"a": 1, "b": 1, "c": 1})
    assert all(v == pytest.approx(30) for v in a.values())


def test_higher_weight_gets_bigger_share():
    a = allocate(100, {"call": 100, "dl": 100}, {"call": 4, "dl": 1})
    assert a["call"] == pytest.approx(80)
    assert a["dl"] == pytest.approx(20)


def test_unused_share_goes_to_others():
    a = allocate(100, {"call": 5, "dl": 500}, {"call": 8, "dl": 1})
    assert a["call"] == pytest.approx(5)
    assert a["dl"] == pytest.approx(95)


def test_total_never_exceeds_budget():
    demands = {"a": 70, "b": 40, "c": 300}
    a = allocate(100, demands, {"a": 2, "b": 4, "c": 1})
    assert sum(a.values()) <= 100 + 1e-9
    assert all(a[c] <= demands[c] + 1e-9 for c in demands)