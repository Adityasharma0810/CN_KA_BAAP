from gateway.controller import decide


def test_no_contention_means_no_limits():
    t = decide(100, {1: 10, 2: 20}, {1: None, 2: None}, {1: "call", 2: "download"})
    assert t == {1: None, 2: None}


def test_call_protected_from_download():
    t = decide(100, {1: 4, 2: 5000}, {1: None, 2: None}, {1: "call", 2: "download"})
    assert t == {1: 5, 2: 95}


def test_weighted_split_when_both_heavy():
    t = decide(100, {1: 5000, 2: 5000}, {1: None, 2: None}, {1: "streaming", 2: "download"})
    assert t == {1: 80, 2: 20}


def test_small_changes_are_ignored():
    t = decide(100, {1: 4, 2: 90}, {1: 5, 2: 92}, {1: "call", 2: "download"})
    assert t == {1: 5, 2: 92}


def test_limits_released_when_demand_drops():
    t = decide(100, {1: 4, 2: 30}, {1: 5, 2: 95}, {1: "call", 2: "download"})
    assert t == {1: None, 2: None}