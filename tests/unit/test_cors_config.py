from backend.app.main import _allowed_origins


def test_cors_origins_keep_defaults_and_accept_environment_values(monkeypatch):
    monkeypatch.setenv(
        "EB_CORS_ORIGINS",
        " http://192.168.56.101:5173/ ,https://dashboard.example ",
    )

    origins = _allowed_origins()

    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:5173" in origins
    assert "http://192.168.56.101:5173" in origins
    assert "https://dashboard.example" in origins
