from pathlib import Path

from backend.app.services.lab_accounting_service import LabAccountingService


def test_lab_service_reports_unavailable_without_linux_interfaces(tmp_path: Path):
    service = LabAccountingService(tmp_path)

    result = service.collect()

    assert result["available"] is False
    assert result["clients"] == []
    assert result["source"] == "linux_namespace_lab"
    assert result["environment"] == "simulated_lab"
    assert result["scope"] == "client"


def test_lab_service_collects_one_result_per_available_client(tmp_path: Path):
    for index in (1, 2, 3):
        stats = tmp_path / f"veth-c{index}-br" / "statistics"
        stats.mkdir(parents=True)
        for name in ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets"):
            (stats / name).write_text("0")

    service = LabAccountingService(tmp_path)
    result = service.collect()

    assert result["available"] is True
    assert len(result["clients"]) == 3
    assert [item["observation"]["metadata"]["scope"] for item in result["clients"]] == [
        "client", "client", "client"
    ]
    assert all(item["observation"]["metadata"]["environment"] == "simulated_lab" for item in result["clients"])
    assert len({item["client_id"] for item in result["clients"]}) == 3
