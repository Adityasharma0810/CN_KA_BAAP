from backend.app.main import app


def test_scenario_and_qoe_routes_are_documented():
    schema = app.openapi()

    assert "/api/v1/scenarios" in schema["paths"]
    assert "/api/v1/scenarios/{scenario_id}/start" in schema["paths"]
    assert "/api/v1/scenarios/stop" in schema["paths"]
    assert "/api/v1/scenarios/status" in schema["paths"]
    assert "/api/v1/qoe/current" in schema["paths"]
    assert "/api/v1/qoe/history" in schema["paths"]
    assert "ScenarioCatalogResponse" in schema["components"]["schemas"]
    assert "QoECurrentResponse" in schema["components"]["schemas"]
