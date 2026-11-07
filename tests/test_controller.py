from gateway.controller import decide


def test_no_contention_means_no_limits():
    t = decide(100, {1: 10, 2: 20}, {1: None, 2: None}, {1: "call", 2: "download"})
    assert t == {1: None, 2: None}


def test_call_stays_unlimited_and_download_is_capped():
    t = decide(100, {1: 4, 2: 5000}, {1: None, 2: None}, {1: "call", 2: "download"})
    assert t == {1: None, 2: 85}


def test_weighted_split_when_both_heavy():
    t = decide(100, {1: 5000, 2: 5000}, {1: None, 2: None}, {1: "streaming", 2: "download"})
    assert t == {1: 72, 2: 18}


def test_leaves_headroom_below_link_rate():
    t = decide(100, {1: 5000, 2: 5000}, {1: None, 2: None}, {})
    assert sum(t.values()) <= 90


def test_small_changes_are_ignored():
    t = decide(100, {1: 66, 2: 19}, {1: 70, 2: 20}, {1: "streaming", 2: "download"})
    assert t == {1: 70, 2: 20}


def test_limits_released_when_demand_drops():
    t = decide(100, {1: 4, 2: 30}, {1: 5, 2: 95}, {1: "call", 2: "download"})
    assert t == {1: None, 2: None}