"""
OAuth authentication router for multi-tenant mode.

Provides Google and GitHub OAuth authentication flows with JWT cookie session
management. Authentication is only enforced when MULTI_TENANT=true.
"""

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from ..db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# JWT cookie settings
COOKIE_NAME = "auth_token"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds

# OAuth state for CSRF protection
_oauth_states: dict[str, float] = {}


def get_jwt_secret() -> str:
    """Get the JWT signing secret from environment or generate one."""
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        # In development, use a deterministic secret
        # In production, JWT_SECRET must be set
        if is_multi_tenant():
            logger.warning("JWT_SECRET not set in multi-tenant mode! Using insecure default.")
        secret = "dev-secret-do-not-use-in-production"
    return secret


def get_serializer() -> URLSafeTimedSerializer:
    """Get the URL-safe timed serializer for JWT tokens."""
    return URLSafeTimedSerializer(get_jwt_secret())


def is_multi_tenant() -> bool:
    """Check if running in multi-tenant mode."""
    return os.environ.get("MULTI_TENANT", "").lower() in ("true", "1", "yes")


def create_auth_token(user_id: str, email: str) -> str:
    """
    Create a signed auth token containing user information.

    Args:
        user_id: The user's unique ID.
        email: The user's email address.

    Returns:
        Signed token string.
    """
    serializer = get_serializer()
    data = {
        "user_id": user_id,
        "email": email,
        "exp": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    }
    return serializer.dumps(data)


def verify_auth_token(token: str) -> Optional[dict]:
    """
    Verify and decode an auth token.

    Args:
        token: The signed token string.

    Returns:
        Decoded token data or None if invalid/expired.
    """
    serializer = get_serializer()
    try:
        # Max age is 7 days in seconds
        data = serializer.loads(token, max_age=COOKIE_MAX_AGE)
        # Check if token is expired
        exp = datetime.fromisoformat(data.get("exp", ""))
        if exp < datetime.now(timezone.utc):
            return None
        return data
    except (BadSignature, SignatureExpired, ValueError):
        return None


def get_or_create_user(email: str, provider: str) -> str:
    """
    Get existing user or create new one.

    Args:
        email: User's email address.
        provider: OAuth provider (google/github).

    Returns:
        User ID.
    """
    # Generate consistent user ID from email
    user_id = hashlib.sha256(email.lower().encode()).hexdigest()[:16]

    conn = get_db()
    try:
        # Check if user exists
        cursor = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()

        if row is None:
            # Create new user
            conn.execute(
                "INSERT INTO users (id, email, created_at) VALUES (?, ?, ?)",
                (user_id, email, datetime.now(timezone.utc).isoformat())
            )
            conn.commit()
            logger.info(f"Created new user: {email} via {provider}")
        else:
            logger.info(f"Existing user login: {email} via {provider}")

        return user_id
    finally:
        conn.close()


def generate_oauth_state() -> str:
    """Generate a secure random state for OAuth CSRF protection."""
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = datetime.now(timezone.utc).timestamp()
    # Clean up old states (older than 10 minutes)
    cutoff = datetime.now(timezone.utc).timestamp() - 600
    for old_state in list(_oauth_states.keys()):
        if _oauth_states[old_state] < cutoff:
            del _oauth_states[old_state]
    return state


def verify_oauth_state(state: str) -> bool:
    """Verify that the OAuth state is valid and not expired."""
    if state not in _oauth_states:
        return False
    created = _oauth_states.pop(state)
    # State is valid for 10 minutes
    return (datetime.now(timezone.utc).timestamp() - created) < 600


# ============================================================================
# OAuth Configuration
# ============================================================================


def get_google_config() -> Optional[dict]:
    """Get Google OAuth configuration from environment."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
        "scope": "openid email profile",
    }


def get_github_config() -> Optional[dict]:
    """Get GitHub OAuth configuration from environment."""
    client_id = os.environ.get("GITHUB_CLIENT_ID")
    client_secret = os.environ.get("GITHUB_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "emails_url": "https://api.github.com/user/emails",
        "scope": "user:email",
    }


def get_redirect_uri(request: Request, provider: str) -> str:
    """Build the OAuth callback redirect URI."""
    # Use the request's base URL
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc)
    return f"{scheme}://{host}/auth/callback/{provider}"


# ============================================================================
# Auth Status Endpoint
# ============================================================================


@router.get("/status")
async def auth_status(request: Request):
    """
    Get current authentication status.

    Returns user info if authenticated, or auth requirements if not.
    """
    # Check if multi-tenant mode
    multi_tenant = is_multi_tenant()

    if not multi_tenant:
        # In local mode, no auth required
        return {
            "authenticated": True,
            "multi_tenant": False,
            "user": None,
        }

    # Check for auth cookie
    token = request.cookies.get(COOKIE_NAME)
    if token:
        data = verify_auth_token(token)
        if data:
            return {
                "authenticated": True,
                "multi_tenant": True,
                "user": {
                    "id": data["user_id"],
                    "email": data["email"],
                },
            }

    # Not authenticated
    google_config = get_google_config()
    github_config = get_github_config()

    return {
        "authenticated": False,
        "multi_tenant": True,
        "user": None,
        "providers": {
            "google": google_config is not None,
            "github": github_config is not None,
        },
    }


# ============================================================================
# Login Routes
# ============================================================================


@router.get("/login/google")
async def login_google(request: Request):
    """Redirect to Google OAuth login."""
    config = get_google_config()
    if not config:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    state = generate_oauth_state()
    redirect_uri = get_redirect_uri(request, "google")

    params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": config["scope"],
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }

    query = "&".join(f"{k}={v}" for k, v in params.items())
    auth_url = f"{config['authorize_url']}?{query}"

    return RedirectResponse(url=auth_url)


@router.get("/login/github")
async def login_github(request: Request):
    """Redirect to GitHub OAuth login."""
    config = get_github_config()
    if not config:
        raise HTTPException(status_code=503, detail="GitHub OAuth not configured")

    state = generate_oauth_state()
    redirect_uri = get_redirect_uri(request, "github")

    params = {
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "scope": config["scope"],
        "state": state,
    }

    query = "&".join(f"{k}={v}" for k, v in params.items())
    auth_url = f"{config['authorize_url']}?{query}"

    return RedirectResponse(url=auth_url)


# ============================================================================
# Callback Routes
# ============================================================================


@router.get("/callback/google")
async def callback_google(request: Request, code: str = "", state: str = "", error: str = ""):
    """Handle Google OAuth callback."""
    import httpx

    if error:
        return _auth_error_response(f"Google login failed: {error}")

    if not code or not state:
        return _auth_error_response("Invalid callback parameters")

    if not verify_oauth_state(state):
        return _auth_error_response("Invalid or expired state")

    config = get_google_config()
    if not config:
        return _auth_error_response("Google OAuth not configured")

    redirect_uri = get_redirect_uri(request, "google")

    try:
        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                config["token_url"],
                data={
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            token_response.raise_for_status()
            tokens = token_response.json()

            # Get user info
            userinfo_response = await client.get(
                config["userinfo_url"],
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            userinfo_response.raise_for_status()
            userinfo = userinfo_response.json()

        email = userinfo.get("email")
        if not email:
            return _auth_error_response("Could not get email from Google")

        # Create or get user
        user_id = get_or_create_user(email, "google")

        # Create auth token and set cookie
        auth_token = create_auth_token(user_id, email)

        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key=COOKIE_NAME,
            value=auth_token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="lax",
        )
        return response

    except httpx.HTTPError as e:
        logger.error(f"Google OAuth error: {e}")
        return _auth_error_response("Failed to authenticate with Google")


@router.get("/callback/github")
async def callback_github(request: Request, code: str = "", state: str = "", error: str = ""):
    """Handle GitHub OAuth callback."""
    import httpx

    if error:
        return _auth_error_response(f"GitHub login failed: {error}")

    if not code or not state:
        return _auth_error_response("Invalid callback parameters")

    if not verify_oauth_state(state):
        return _auth_error_response("Invalid or expired state")

    config = get_github_config()
    if not config:
        return _auth_error_response("GitHub OAuth not configured")

    redirect_uri = get_redirect_uri(request, "github")

    try:
        async with httpx.AsyncClient() as client:
            # Exchange code for tokens
            token_response = await client.post(
                config["token_url"],
                data={
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            token_response.raise_for_status()
            tokens = token_response.json()

            access_token = tokens.get("access_token")
            if not access_token:
                return _auth_error_response("No access token from GitHub")

            # Get user info
            userinfo_response = await client.get(
                config["userinfo_url"],
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            userinfo_response.raise_for_status()
            userinfo = userinfo_response.json()

            # GitHub doesn't always return email in user profile
            # Need to fetch from emails endpoint
            email = userinfo.get("email")
            if not email:
                emails_response = await client.get(
                    config["emails_url"],
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
                emails_response.raise_for_status()
                emails = emails_response.json()

                # Find primary email
                for email_obj in emails:
                    if email_obj.get("primary") and email_obj.get("verified"):
                        email = email_obj.get("email")
                        break

                if not email:
                    return _auth_error_response("Could not get email from GitHub")

        # Create or get user
        user_id = get_or_create_user(email, "github")

        # Create auth token and set cookie
        auth_token = create_auth_token(user_id, email)

        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key=COOKIE_NAME,
            value=auth_token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="lax",
        )
        return response

    except httpx.HTTPError as e:
        logger.error(f"GitHub OAuth error: {e}")
        return _auth_error_response("Failed to authenticate with GitHub")


# ============================================================================
# Logout Route
# ============================================================================


@router.post("/logout")
async def logout(response: Response):
    """
    Log out the current user.

    Clears the auth cookie.
    """
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key=COOKIE_NAME)
    return response


@router.get("/logout")
async def logout_get():
    """
    Log out the current user (GET method for direct navigation).

    Clears the auth cookie.
    """
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key=COOKIE_NAME)
    return response


# ============================================================================
# Auth Middleware
# ============================================================================


def get_current_user(request: Request) -> Optional[dict]:
    """
    Get the current authenticated user from the request.

    Args:
        request: The FastAPI request object.

    Returns:
        User dict with id and email, or None if not authenticated.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    data = verify_auth_token(token)
    if not data:
        return None
    return {"id": data["user_id"], "email": data["email"]}


async def require_auth(request: Request) -> Optional[dict]:
    """
    Middleware dependency to require authentication.

    Only enforced in multi-tenant mode.

    Args:
        request: The FastAPI request object.

    Returns:
        User dict if authenticated.

    Raises:
        HTTPException: If not authenticated in multi-tenant mode.
    """
    if not is_multi_tenant():
        return None

    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Store user in request state for downstream use
    request.state.user_id = user["id"]
    return user


# ============================================================================
# Helper Functions
# ============================================================================


def _auth_error_response(message: str) -> HTMLResponse:
    """Return an HTML error page for auth failures."""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Authentication Error</title>
        <style>
            body {{
                font-family: system-ui, -apple-system, sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
                background: #0d1117;
                color: #c9d1d9;
            }}
            .container {{
                text-align: center;
                padding: 2rem;
            }}
            h1 {{ color: #f85149; }}
            a {{
                color: #58a6ff;
                text-decoration: none;
            }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Authentication Error</h1>
            <p>{message}</p>
            <p><a href="/login">Try again</a></p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=400)
