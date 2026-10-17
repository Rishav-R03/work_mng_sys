import importlib

import pytest
from authlib.integrations.base_client.errors import MismatchingStateError
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app():
    module = importlib.import_module("app.main")
    return module.app


@pytest.fixture
def auth_module():
    return importlib.import_module("app.routers.auth")


@pytest.mark.backend
def test_github_callback_state_mismatch_returns_client_error(app, auth_module, monkeypatch):
    callback_path = next(
        (
            route.path
            for route in app.routes
            if "github" in route.path.lower() and "callback" in route.path.lower()
        ),
        None,
    )
    if callback_path is None:
        pytest.skip("No GitHub OAuth callback route is registered.")

    async def raise_state_mismatch(request):
        raise MismatchingStateError()

    monkeypatch.setattr(
        auth_module.oauth.github,
        "authorize_access_token",
        raise_state_mismatch,
    )

    client = TestClient(app)
    response = client.get(f"{callback_path}?code=fake-code&state=fake-state")

    assert response.status_code == 400
    assert "state" in response.json()["detail"].lower()
