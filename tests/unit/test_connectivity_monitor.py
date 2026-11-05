
from types import SimpleNamespace

from network.telemetry import connectivity_monitor as monitor


def test_online_connection(monkeypatch):
    monkeypatch.setattr(
        monitor,
        "get_adapter_status",
        lambda name: True
    )

    monkeypatch.setattr(
        monitor,
        "probe_internet",
        lambda timeout: (True, 2, 2)
    )

    result = monitor.collect_connectivity("Wi-Fi")

    assert result["adapter_up"] is True
    assert result["internet_reachable"] is True
    assert result["status"] == "online"


def test_internet_unreachable(monkeypatch):
    monkeypatch.setattr(
        monitor,
        "get_adapter_status",
        lambda name: True
    )

    monkeypatch.setattr(
        monitor,
        "probe_internet",
        lambda timeout: (False, 0, 2)
    )

    result = monitor.collect_connectivity("Wi-Fi")

    assert result["adapter_up"] is True
    assert result["internet_reachable"] is False
    assert result["status"] == "internet_unreachable"


def test_adapter_down(monkeypatch):
    monkeypatch.setattr(
        monitor,
        "get_adapter_status",
        lambda name: False
    )

    def should_not_probe(timeout):
        raise AssertionError("Internet probe should not run")

    monkeypatch.setattr(
        monitor,
        "probe_internet",
        should_not_probe
    )

    result = monitor.collect_connectivity("Wi-Fi")

    assert result["status"] == "adapter_down"
    assert result["internet_reachable"] is False


def test_outage_duration():
    tracker = monitor.OutageTracker()

    assert tracker.update(False, now=10)["outage_duration_seconds"] == 0
    assert tracker.update(False, now=15)["outage_duration_seconds"] == 5

    recovery = tracker.update(True, now=22)

    assert recovery["outage_recovered"] is True
    assert recovery["last_outage_duration_seconds"] == 12


def test_no_outage():
    tracker = monitor.OutageTracker()

    result = tracker.update(True, now=10)

    assert result["outage_recovered"] is False
    assert result["outage_duration_seconds"] == 0
