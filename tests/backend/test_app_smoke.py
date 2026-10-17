import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app():
    module = importlib.import_module("app.main")
    return module.app


@pytest.mark.backend
def test_app_exposes_openapi_schema(app):
    client = TestClient(app)

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["openapi"].startswith("3.")
