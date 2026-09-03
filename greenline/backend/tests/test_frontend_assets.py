from pathlib import Path

from fastapi.testclient import TestClient

from app import create_application


def _application(dist: Path):
    dist.mkdir()
    (dist / "index.html").write_text("<main>Greenline app</main>", encoding="utf-8")
    (dist / "app.js").write_text("console.log('greenline')", encoding="utf-8")
    return create_application(
        {"GREENLINE_MODE": "local", "GREENLINE_FRONTEND_DIST": str(dist)}
    )


def test_frontend_assets_preserve_api_and_health_routes(tmp_path: Path) -> None:
    application = _application(tmp_path / "dist")

    with TestClient(application) as client:
        assert client.get("/health/live").json()["status"] == "live"
        assert client.get("/api/challenges").status_code == 200
        assert client.get("/app.js").text == "console.log('greenline')"


def test_frontend_deep_links_fall_back_without_hiding_missing_assets(
    tmp_path: Path,
) -> None:
    application = _application(tmp_path / "dist")

    with TestClient(application) as client:
        navigation = client.get("/challenges/orders-service", headers={"Accept": "text/html"})
        missing_asset = client.get("/missing.js", headers={"Accept": "text/html"})

    assert navigation.status_code == 200
    assert "Greenline app" in navigation.text
    assert missing_asset.status_code == 404
