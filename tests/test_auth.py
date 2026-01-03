"""
Tests for OAuth authentication module.

Tests cover:
- JWT token creation and verification
- Auth status endpoint
- Multi-tenant mode detection
- OAuth state management
"""

import os
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.replay_server.api import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_multi_tenant():
    """Mock multi-tenant mode being enabled."""
    with patch.dict(os.environ, {"MULTI_TENANT": "true"}):
        yield


@pytest.fixture
def mock_local_mode():
    """Mock local mode (multi-tenant disabled)."""
    with patch.dict(os.environ, {"MULTI_TENANT": "false"}):
        yield


class TestAuthStatus:
    """Tests for /auth/status endpoint."""

    def test_auth_status_local_mode_always_authenticated(self, client, mock_local_mode):
        """In local mode, /auth/status returns authenticated=true without user."""
        response = client.get("/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["multi_tenant"] is False
        assert data["user"] is None

    def test_auth_status_multi_tenant_not_authenticated(self, client, mock_multi_tenant):
        """In multi-tenant mode without cookie, returns authenticated=false."""
        response = client.get("/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["multi_tenant"] is True
        assert data["user"] is None
        assert "providers" in data


class TestJWTTokens:
    """Tests for JWT token creation and verification."""

    def test_create_auth_token_contains_user_info(self):
        """Auth token contains user_id and email."""
        from src.replay_server.routers.auth import create_auth_token, verify_auth_token

        token = create_auth_token("user123", "test@example.com")
        data = verify_auth_token(token)

        assert data is not None
        assert data["user_id"] == "user123"
        assert data["email"] == "test@example.com"

    def test_verify_auth_token_invalid_signature(self):
        """Invalid token returns None."""
        from src.replay_server.routers.auth import verify_auth_token

        result = verify_auth_token("invalid.token.here")
        assert result is None

    def test_verify_auth_token_empty(self):
        """Empty token returns None."""
        from src.replay_server.routers.auth import verify_auth_token

        result = verify_auth_token("")
        assert result is None


class TestOAuthState:
    """Tests for OAuth state (CSRF protection)."""

    def test_generate_oauth_state_unique(self):
        """Each generated state is unique."""
        from src.replay_server.routers.auth import generate_oauth_state

        states = [generate_oauth_state() for _ in range(10)]
        assert len(set(states)) == 10  # All unique

    def test_verify_oauth_state_valid(self):
        """Valid state passes verification."""
        from src.replay_server.routers.auth import generate_oauth_state, verify_oauth_state

        state = generate_oauth_state()
        assert verify_oauth_state(state) is True

    def test_verify_oauth_state_invalid(self):
        """Invalid state fails verification."""
        from src.replay_server.routers.auth import verify_oauth_state

        assert verify_oauth_state("invalid-state") is False

    def test_verify_oauth_state_consumed(self):
        """State is consumed after verification (single-use)."""
        from src.replay_server.routers.auth import generate_oauth_state, verify_oauth_state

        state = generate_oauth_state()
        assert verify_oauth_state(state) is True
        assert verify_oauth_state(state) is False  # Second use fails


class TestGetOrCreateUser:
    """Tests for user creation/retrieval."""

    def test_get_or_create_user_creates_new(self, tmp_path):
        """Creates a new user when email doesn't exist."""
        from src.replay_server.routers.auth import get_or_create_user
        from src.replay_server.db import set_db_path, init_db

        # Use temp database
        db_path = tmp_path / "test.db"
        set_db_path(db_path)
        init_db()

        user_id = get_or_create_user("new@example.com", "google")
        assert user_id is not None
        assert len(user_id) == 16  # Truncated SHA256

    def test_get_or_create_user_returns_same_id(self, tmp_path):
        """Returns same user_id for same email."""
        from src.replay_server.routers.auth import get_or_create_user
        from src.replay_server.db import set_db_path, init_db

        # Use temp database
        db_path = tmp_path / "test.db"
        set_db_path(db_path)
        init_db()

        user_id1 = get_or_create_user("same@example.com", "google")
        user_id2 = get_or_create_user("same@example.com", "github")

        assert user_id1 == user_id2

    def test_get_or_create_user_case_insensitive(self, tmp_path):
        """Email comparison is case-insensitive."""
        from src.replay_server.routers.auth import get_or_create_user
        from src.replay_server.db import set_db_path, init_db

        # Use temp database
        db_path = tmp_path / "test.db"
        set_db_path(db_path)
        init_db()

        user_id1 = get_or_create_user("Test@Example.com", "google")
        user_id2 = get_or_create_user("test@example.com", "google")

        assert user_id1 == user_id2


class TestOAuthConfigDetection:
    """Tests for OAuth configuration detection."""

    def test_google_config_missing_returns_none(self):
        """Returns None when Google OAuth not configured."""
        from src.replay_server.routers.auth import get_google_config

        with patch.dict(os.environ, {}, clear=True):
            config = get_google_config()
            assert config is None

    def test_github_config_missing_returns_none(self):
        """Returns None when GitHub OAuth not configured."""
        from src.replay_server.routers.auth import get_github_config

        with patch.dict(os.environ, {}, clear=True):
            config = get_github_config()
            assert config is None

    def test_google_config_returns_dict_when_configured(self):
        """Returns config dict when Google OAuth is configured."""
        from src.replay_server.routers.auth import get_google_config

        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
        }):
            config = get_google_config()
            assert config is not None
            assert config["client_id"] == "test-id"
            assert config["client_secret"] == "test-secret"

    def test_github_config_returns_dict_when_configured(self):
        """Returns config dict when GitHub OAuth is configured."""
        from src.replay_server.routers.auth import get_github_config

        with patch.dict(os.environ, {
            "GITHUB_CLIENT_ID": "test-id",
            "GITHUB_CLIENT_SECRET": "test-secret",
        }):
            config = get_github_config()
            assert config is not None
            assert config["client_id"] == "test-id"
            assert config["client_secret"] == "test-secret"


class TestAuthMiddleware:
    """Tests for auth middleware protecting API routes."""

    def test_api_health_always_accessible(self, client, mock_multi_tenant):
        """Health endpoint is accessible without auth in multi-tenant mode."""
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_api_mode_always_accessible(self, client, mock_multi_tenant):
        """Mode endpoint is accessible without auth in multi-tenant mode."""
        response = client.get("/api/mode")
        assert response.status_code == 200

    def test_auth_endpoints_always_accessible(self, client, mock_multi_tenant):
        """Auth endpoints are accessible without auth in multi-tenant mode."""
        response = client.get("/auth/status")
        assert response.status_code == 200

    def test_protected_api_requires_auth_in_multi_tenant(self, client, mock_multi_tenant):
        """Protected API endpoints return 401 without auth in multi-tenant mode."""
        response = client.get("/api/session")
        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required"

    def test_protected_api_accessible_in_local_mode(self, client, mock_local_mode):
        """Protected API endpoints are accessible without auth in local mode."""
        response = client.get("/api/session")
        # May return 200 or error based on session state, but not 401
        assert response.status_code != 401


class TestLoginPage:
    """Tests for login page."""

    def test_login_page_accessible(self, client):
        """Login page is accessible."""
        response = client.get("/login")
        assert response.status_code == 200
        assert "Sign in to continue" in response.text

    def test_login_page_shows_google_when_configured(self, client):
        """Login page shows Google button when configured."""
        with patch.dict(os.environ, {
            "GOOGLE_CLIENT_ID": "test-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
        }):
            response = client.get("/login")
            assert response.status_code == 200
            assert "Continue with Google" in response.text

    def test_login_page_shows_not_configured_when_missing(self, client):
        """Login page shows 'not configured' when OAuth not set up."""
        with patch.dict(os.environ, {}, clear=True):
            response = client.get("/login")
            assert response.status_code == 200
            assert "not configured" in response.text.lower()


class TestLogout:
    """Tests for logout functionality."""

    def test_logout_get_redirects_to_login(self, client):
        """GET /auth/logout redirects to login page."""
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"

    def test_logout_post_redirects_to_login(self, client):
        """POST /auth/logout redirects to login page."""
        response = client.post("/auth/logout", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"
