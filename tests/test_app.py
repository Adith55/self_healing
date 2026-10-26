from app.app import app


def test_health_returns_ok() -> None:
    """/health returns 200 and {"status": "ok"}."""
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_index_returns_200() -> None:
    """/ returns 200."""
    assert app.test_client().get("/").status_code == 200
