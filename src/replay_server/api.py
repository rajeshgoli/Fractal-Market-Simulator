"""
FastAPI backend for Replay View.

Minimal server for:
- Serving OHLC bars for chart display
- Replay calibration and advance endpoints
- Playback feedback collection
"""

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .schemas import BarResponse
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    init_db()
    yield
    # Shutdown (nothing to clean up)
from ..data.ohlc_loader import load_ohlc
from ..swing_analysis.bar_aggregator import BarAggregator
from ..swing_analysis.types import Bar
from ..swing_analysis.dag import LegDetector, HierarchicalDetector

logger = logging.getLogger(__name__)

# Data directory (set by main.py)
_data_dir: Optional[str] = None


def set_data_dir(path: str) -> None:
    """Set the data directory for file discovery."""
    global _data_dir
    _data_dir = path
    logger.info(f"Data directory set to: {path}")


def get_data_dir() -> Path:
    """Get the configured data directory."""
    if _data_dir is None:
        # Fallback to test_data in project root (for backwards compatibility)
        project_root = Path(__file__).parent.parent.parent
        return project_root / "test_data"
    return Path(_data_dir)


def is_multi_tenant() -> bool:
    """Check if running in multi-tenant mode."""
    return os.environ.get("MULTI_TENANT", "").lower() in ("true", "1", "yes")


@dataclass
class AppState:
    """Application state for Replay View."""
    source_bars: List[Bar]
    aggregated_bars: List[Bar]
    aggregation_map: dict
    aggregator: Optional[BarAggregator] = None
    # Session info
    data_file: Optional[str] = None
    resolution_minutes: int = 1
    total_source_bars: int = 0
    window_offset: int = 0
    # Cached DataFrame
    cached_dataframe: Optional[pd.DataFrame] = None
    # Replay state
    playback_index: Optional[int] = None
    # Leg detector for incremental processing
    hierarchical_detector: Optional[LegDetector] = None
    # Visualization mode: 'dag'
    mode: str = "dag"


# Global state
state: Optional[AppState] = None

app = FastAPI(
    title="Replay View Server",
    description="Backend for Replay View swing detection",
    version="0.2.0",
    lifespan=lifespan,
)


# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Auth middleware for protected routes
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """
    Middleware to check authentication for protected API routes.

    Only enforced when MULTI_TENANT=true. Allows:
    - /auth/* routes (for login flow)
    - /api/health (for health checks)
    - /api/mode (for frontend mode detection)
    - /login (login page)
    - Static assets
    """
    from starlette.responses import JSONResponse

    path = request.url.path

    # Skip auth check for non-multi-tenant mode
    if not is_multi_tenant():
        return await call_next(request)

    # Skip auth check for public routes
    public_paths = [
        "/auth/",
        "/login",
        "/api/health",
        "/api/mode",
        "/assets/",
        "/vite.svg",
    ]

    for public_path in public_paths:
        if path.startswith(public_path) or path == public_path.rstrip("/"):
            return await call_next(request)

    # For API routes, check authentication
    if path.startswith("/api/"):
        from .routers.auth import get_current_user
        user = get_current_user(request)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )
        # Store user in request state for downstream use
        request.state.user_id = user["id"]

    return await call_next(request)


def get_state() -> AppState:
    """Get the application state."""
    if state is None:
        raise HTTPException(
            status_code=500,
            detail="Application not initialized. Start server with --data flag."
        )
    return state


# ============================================================================
# Static Page Routes
# ============================================================================


def get_static_dir() -> Optional[Path]:
    """Get the static files directory (production or development)."""
    project_root = Path(__file__).parent.parent.parent

    # Production: /app/static (Docker)
    prod_static = project_root / "static"
    if prod_static.exists() and (prod_static / "index.html").exists():
        return prod_static

    # Development: frontend/dist
    dev_static = project_root / "frontend" / "dist"
    if dev_static.exists() and (dev_static / "index.html").exists():
        return dev_static

    return None


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the React frontend - let React router handle auth-based routing."""
    static_dir = get_static_dir()

    if static_dir:
        index_path = static_dir / "index.html"
        with open(index_path, 'r') as f:
            return HTMLResponse(content=f.read())

    return HTMLResponse(
        content="<h1>Replay View</h1><p>React build not found. Run 'npm run build' in frontend/</p>",
        status_code=200
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page."""
    # If already authenticated, redirect to home
    if is_multi_tenant():
        from .routers.auth import get_current_user
        user = get_current_user(request)
        if user:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/", status_code=302)

    # Check which OAuth providers are configured
    from .routers.auth import get_google_config, get_github_config
    google_available = get_google_config() is not None
    github_available = get_github_config() is not None

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Login - Market Structure Analyzer</title>
        <style>
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            body {{
                font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
                color: #c9d1d9;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            .container {{
                text-align: center;
                padding: 3rem;
                background: #21262d;
                border-radius: 12px;
                border: 1px solid #30363d;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
                max-width: 400px;
                width: 90%;
            }}
            .logo {{
                font-size: 2rem;
                font-weight: 700;
                color: #58a6ff;
                margin-bottom: 0.5rem;
            }}
            .tagline {{
                font-size: 0.875rem;
                color: #8b949e;
                margin-bottom: 2rem;
            }}
            h1 {{
                font-size: 1.5rem;
                font-weight: 600;
                margin-bottom: 1.5rem;
                color: #f0f6fc;
            }}
            .buttons {{
                display: flex;
                flex-direction: column;
                gap: 1rem;
            }}
            .btn {{
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 0.75rem;
                padding: 0.875rem 1.5rem;
                border: 1px solid #30363d;
                border-radius: 8px;
                font-size: 1rem;
                font-weight: 500;
                cursor: pointer;
                text-decoration: none;
                transition: all 0.2s ease;
            }}
            .btn-google {{
                background: #fff;
                color: #1f2328;
            }}
            .btn-google:hover {{
                background: #f6f8fa;
                border-color: #8b949e;
            }}
            .btn-github {{
                background: #238636;
                color: #fff;
                border-color: #238636;
            }}
            .btn-github:hover {{
                background: #2ea043;
                border-color: #2ea043;
            }}
            .btn:disabled {{
                opacity: 0.5;
                cursor: not-allowed;
            }}
            .divider {{
                display: flex;
                align-items: center;
                margin: 1.5rem 0;
                color: #8b949e;
                font-size: 0.875rem;
            }}
            .divider::before,
            .divider::after {{
                content: '';
                flex: 1;
                height: 1px;
                background: #30363d;
            }}
            .divider::before {{ margin-right: 1rem; }}
            .divider::after {{ margin-left: 1rem; }}
            .footer {{
                margin-top: 2rem;
                font-size: 0.75rem;
                color: #8b949e;
            }}
            svg {{
                width: 20px;
                height: 20px;
            }}
            .not-configured {{
                padding: 1rem;
                background: #161b22;
                border-radius: 8px;
                color: #8b949e;
                font-size: 0.875rem;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">📊 Market Structure</div>
            <div class="tagline">Fractal Market Analysis Tool</div>

            <h1>Sign in to continue</h1>

            <div class="buttons">
                {'<a href="/auth/login/google" class="btn btn-google"><svg viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>Continue with Google</a>' if google_available else '<div class="not-configured">Google OAuth not configured</div>'}

                {'<a href="/auth/login/github" class="btn btn-github"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>Continue with GitHub</a>' if github_available else '<div class="not-configured">GitHub OAuth not configured</div>'}
            </div>

            <div class="footer">
                By signing in, you agree to our Terms of Service and Privacy Policy.
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@app.get("/replay", response_class=HTMLResponse)
async def replay_redirect():
    """Redirect /replay to / for backwards compatibility."""
    return HTMLResponse(
        content='<html><head><meta http-equiv="refresh" content="0; url=/" /></head></html>',
        status_code=200
    )


# ============================================================================
# Core API Endpoints
# ============================================================================


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "initialized": state is not None,
        "version": "0.2.0",  # HierarchicalDetector version
    }


# ============================================================================
# File Discovery Endpoint (#325)
# ============================================================================


def infer_resolution_from_data(file_path: str) -> int:
    """
    Infer resolution by reading the first few rows and calculating time difference.

    This is more reliable than filename parsing since it uses actual data.

    Args:
        file_path: Path to the OHLC CSV file.

    Returns:
        Resolution in minutes (e.g., 5, 30, 60). Defaults to 5 if detection fails.
    """
    from ..data.ohlc_loader import load_ohlc

    try:
        df, _ = load_ohlc(file_path)
        if len(df) < 2:
            return 5  # Default

        # Calculate time difference between first two rows
        time_diff = df.index[1] - df.index[0]
        minutes = int(time_diff.total_seconds() / 60)

        # Validate it's a reasonable resolution
        valid_resolutions = [1, 5, 15, 30, 60, 240, 1440]  # 1m to 1d
        if minutes in valid_resolutions:
            return minutes

        # Find closest valid resolution
        closest = min(valid_resolutions, key=lambda x: abs(x - minutes))
        return closest

    except Exception as e:
        logger.debug(f"Failed to infer resolution from data: {e}")
        return 5  # Default


def minutes_to_resolution_string(minutes: int) -> str:
    """Convert minutes to resolution string (e.g., 60 -> '1h')."""
    if minutes >= 1440:
        return f"{minutes // 1440}d"
    elif minutes >= 60:
        return f"{minutes // 60}h"
    else:
        return f"{minutes}m"


def infer_resolution_from_filename(filename: str) -> str:
    """
    Infer resolution from filename patterns like es-5m.csv, es-1h.csv, es-30m-from-2023.csv.

    Returns resolution string (e.g., '5m', '1h', '1d') or 'unknown'.
    Note: Prefer infer_resolution_from_data() for more reliable detection.
    """
    import re
    # Match patterns like -5m., -1h., -30m., -1d., -1w., -1mo.
    # Also match when followed by hyphen (e.g., es-30m-from-2023.csv)
    match = re.search(r'-(\d+[mhdw]|1mo)[-.]', filename.lower())
    if match:
        return match.group(1)
    return 'unknown'


@app.get("/api/files")
async def list_data_files():
    """
    List available CSV data files for selection.

    Scans the configured data directory for CSV files and returns metadata
    including bar count and date range. Files that fail to parse are
    silently skipped.

    Returns:
        List of file info objects with path, name, total_bars, resolution,
        start_date, and end_date.
    """
    from ..data.ohlc_loader import get_file_metrics

    data_dir = get_data_dir()

    files = []

    if not data_dir.exists():
        return files

    for csv_file in sorted(data_dir.glob("*.csv")):
        # Skip subdirectories and hidden files
        if not csv_file.is_file() or csv_file.name.startswith('.'):
            continue

        try:
            metrics = get_file_metrics(str(csv_file))
            resolution = infer_resolution_from_filename(csv_file.name)

            file_info = {
                "path": str(csv_file),
                "name": csv_file.name,
                "total_bars": metrics.total_bars,
                "resolution": resolution,
                "start_date": metrics.first_timestamp.isoformat() if metrics.first_timestamp else None,
                "end_date": metrics.last_timestamp.isoformat() if metrics.last_timestamp else None,
            }
            files.append(file_info)
        except (FileNotFoundError, ValueError, OSError) as e:
            # Skip files that fail to parse
            logger.debug(f"Skipping {csv_file.name}: {e}")
            continue

    return files


@app.get("/api/mode")
async def get_mode():
    """Get the server mode (multi-tenant or local)."""
    return {
        "multi_tenant": is_multi_tenant(),
        "data_dir": str(get_data_dir()),
    }


@app.get("/api/config")
async def get_config():
    """Get application configuration including mode."""
    s = get_state()
    return {
        "mode": s.mode,
    }


@app.get("/api/session")
async def get_session():
    """Get current session info."""
    if state is None:
        # No session initialized yet - return empty state
        return {
            "session_id": "",
            "data_file": "",
            "resolution": "",
            "window_size": 0,
            "window_offset": 0,
            "total_source_bars": 0,
            "current_bar_index": None,
            "scale": "S",
            "created_at": "",
            "annotation_count": 0,
            "completed_scales": [],
            "initialized": False,
        }
    s = state
    return {
        "session_id": "replay-session",
        "data_file": s.data_file or "",
        "resolution": minutes_to_resolution_string(s.resolution_minutes),
        "window_size": len(s.source_bars),
        "window_offset": s.window_offset,
        "total_source_bars": s.total_source_bars,
        "current_bar_index": s.playback_index,
        "scale": "S",  # Default scale
        "created_at": "",
        "annotation_count": 0,
        "completed_scales": [],
        "initialized": True,
    }


# ============================================================================
# Session Restart Endpoint (#326, #327)
# ============================================================================


from pydantic import BaseModel


class SessionRestartRequest(BaseModel):
    """Request to restart session with new settings."""
    data_file: str
    start_date: Optional[str] = None  # ISO date string (YYYY-MM-DD)


@app.post("/api/session/restart")
async def restart_session(request: SessionRestartRequest):
    """
    Restart session with new data file and/or start date.

    Reinitializes the application state with the specified file and
    optionally starts from a specific date. This clears all existing
    detection state.

    Args:
        request: SessionRestartRequest with data_file and optional start_date.

    Returns:
        New session info after restart.
    """
    from datetime import datetime
    from ..data.ohlc_loader import load_ohlc, get_file_metrics

    global state

    data_file = request.data_file
    start_date_str = request.start_date

    # Validate file exists
    if not Path(data_file).exists():
        raise HTTPException(status_code=400, detail=f"Data file not found: {data_file}")

    try:
        # Infer resolution from actual data (more reliable than filename)
        resolution_minutes = infer_resolution_from_data(data_file)
        logger.info(f"Detected resolution: {resolution_minutes}m from data")

        # Get file metrics
        metrics = get_file_metrics(data_file)

        # Calculate offset from start date if provided
        offset = 0
        if start_date_str:
            try:
                start_date = datetime.fromisoformat(start_date_str)
                # Load data to find offset
                df, _ = load_ohlc(data_file)

                if df.index.tz is not None:
                    start_dt = pd.Timestamp(start_date, tz='UTC')
                else:
                    start_dt = pd.Timestamp(start_date)

                mask = df.index >= start_dt
                if mask.any():
                    first_match_idx = df.index.get_indexer([df.index[mask][0]])[0]
                    offset = int(first_match_idx)
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"No data found at or after {start_date_str}. "
                               f"Data range: {df.index.min()} to {df.index.max()}"
                    )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")

        # Initialize the application with new settings
        init_app(
            data_file=data_file,
            resolution_minutes=resolution_minutes,
            window_size=50000,
            target_bars=200,
            window_offset=offset,
            mode="dag"  # Always DAG mode
        )

        logger.info(f"Session restarted: {data_file}, offset={offset}")

        # Return new session info
        return {
            "success": True,
            "session_id": "replay-session",
            "data_file": data_file,
            "resolution": minutes_to_resolution_string(resolution_minutes),
            "window_size": len(state.source_bars),
            "window_offset": offset,
            "total_source_bars": metrics.total_bars,
            "start_date": start_date_str,
        }

    except (FileNotFoundError, ValueError, OSError, pd.errors.ParserError) as e:
        raise HTTPException(status_code=400, detail=f"Failed to load data: {e}")


# Scale code to timeframe minutes mapping - standard timeframes
SCALE_TO_MINUTES = {
    "1M": 1, "1m": 1,
    "5M": 5, "5m": 5,
    "15M": 15, "15m": 15,
    "30M": 30, "30m": 30,
    "1H": 60, "1h": 60,
    "4H": 240, "4h": 240,
    "1D": 1440, "1d": 1440,
    "1W": 10080, "1w": 10080,
}


@app.get("/api/bars", response_model=List[BarResponse])
async def get_bars(
    scale: Optional[str] = Query(None, description="Timeframe for aggregation (1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W)"),
    limit: Optional[int] = Query(None, description="Limit to first N source bars")
):
    """
    Get bars for chart display.

    Returns bars aggregated to the appropriate timeframe for visualization.
    Supported scales: 1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W.
    """
    s = get_state()

    # Compute effective limit based on playback_index
    effective_limit = limit
    if s.playback_index is not None:
        playback_limit = s.playback_index + 1
        if effective_limit is not None:
            effective_limit = min(effective_limit, playback_limit)
        else:
            effective_limit = playback_limit
    limit = effective_limit

    # DAG mode: If limit is 0 (no bars processed), return empty list (#179)
    if limit is not None and limit <= 0:
        return []

    if scale and s.aggregator:
        # Get timeframe minutes for this scale
        timeframe_minutes = SCALE_TO_MINUTES.get(scale.upper(), s.resolution_minutes)

        # Clamp to source resolution (can't aggregate to finer granularity)
        effective_timeframe = max(timeframe_minutes, s.resolution_minutes)

        # Get source bars (limited if playback is active)
        source_bars_to_use = s.source_bars[:limit] if limit is not None else s.source_bars

        if not source_bars_to_use:
            return []

        # If effective timeframe equals source resolution, return source bars directly
        if effective_timeframe == s.resolution_minutes:
            bars = []
            for i, src_bar in enumerate(source_bars_to_use):
                bars.append(BarResponse(
                    index=i,
                    timestamp=src_bar.timestamp,
                    open=src_bar.open,
                    high=src_bar.high,
                    low=src_bar.low,
                    close=src_bar.close,
                    source_start_index=i,
                    source_end_index=i,
                ))
            return bars

        # Create aggregator for the limited bars and get timeframe-aggregated bars
        if limit is not None:
            temp_aggregator = BarAggregator(source_bars_to_use, s.resolution_minutes)
            agg_bars = temp_aggregator.get_bars(effective_timeframe)
            source_to_agg_map = temp_aggregator._source_to_agg_mapping.get(effective_timeframe, {})
        else:
            agg_bars = s.aggregator.get_bars(effective_timeframe)
            source_to_agg_map = s.aggregator._source_to_agg_mapping.get(effective_timeframe, {})

        # Build inverse mapping: agg_idx -> (min_source_idx, max_source_idx)
        agg_to_source = {}
        for source_idx, agg_idx in source_to_agg_map.items():
            if agg_idx not in agg_to_source:
                agg_to_source[agg_idx] = (source_idx, source_idx)
            else:
                min_idx, max_idx = agg_to_source[agg_idx]
                agg_to_source[agg_idx] = (min(min_idx, source_idx), max(max_idx, source_idx))

        bars = []
        for i, agg_bar in enumerate(agg_bars):
            source_start, source_end = agg_to_source.get(i, (0, 0))
            bars.append(BarResponse(
                index=i,
                timestamp=agg_bar.timestamp,
                open=agg_bar.open,
                high=agg_bar.high,
                low=agg_bar.low,
                close=agg_bar.close,
                source_start_index=source_start,
                source_end_index=source_end,
            ))
        return bars

    # Default: return pre-computed aggregated bars
    bars = []
    for agg_bar in s.aggregated_bars:
        source_start, source_end = s.aggregation_map.get(agg_bar.index, (agg_bar.index, agg_bar.index))
        bars.append(BarResponse(
            index=agg_bar.index,
            timestamp=agg_bar.timestamp,
            open=agg_bar.open,
            high=agg_bar.high,
            low=agg_bar.low,
            close=agg_bar.close,
            source_start_index=source_start,
            source_end_index=source_end,
        ))

    return bars


# ============================================================================
# Application Initialization
# ============================================================================


def init_app(
    data_file: str,
    resolution_minutes: int = 1,
    window_size: int = 50000,
    target_bars: int = 200,
    window_offset: int = 0,
    cached_df: Optional[pd.DataFrame] = None,
    mode: str = "dag"
):
    """
    Initialize the application with data file.

    Args:
        data_file: Path to OHLC CSV data file
        resolution_minutes: Source data resolution in minutes
        window_size: Total bars to load for initial window
        target_bars: Target number of bars to display
        window_offset: Offset into source data
        cached_df: Optional cached DataFrame
        mode: Visualization mode ('dag')
    """
    global state

    # Load source data
    if cached_df is not None:
        logger.info(f"Using cached DataFrame ({len(cached_df)} bars)")
        df = cached_df
    else:
        logger.info(f"Loading data from {data_file}...")
        df, gaps = load_ohlc(data_file)

    total_source_bars = len(df)
    full_df = df

    # Load extra bars beyond calibration window for playback
    playback_buffer = window_size
    total_bars_to_load = window_size + playback_buffer

    if window_offset > 0:
        df = df.iloc[window_offset:]
        logger.info(f"Applied offset of {window_offset} bars")

    if len(df) > total_bars_to_load:
        df = df.head(total_bars_to_load)
        logger.info(f"Limited to {total_bars_to_load} bars")

    # Convert to Bar objects
    source_bars = []
    for idx, (timestamp, row) in enumerate(df.iterrows()):
        bar = Bar(
            index=idx,
            timestamp=int(timestamp.timestamp()),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close'])
        )
        source_bars.append(bar)

    logger.info(f"Loaded {len(source_bars)} source bars")

    # Create aggregator
    aggregator = BarAggregator(source_bars, resolution_minutes)
    aggregated_bars = aggregator.aggregate_to_target_bars(target_bars)
    logger.info(f"Aggregated to {len(aggregated_bars)} display bars")

    # Build aggregation map
    aggregation_map = {}
    if len(source_bars) > target_bars:
        bars_per_candle = len(source_bars) // target_bars
        for agg_idx in range(len(aggregated_bars)):
            source_start = agg_idx * bars_per_candle
            source_end = min(source_start + bars_per_candle - 1, len(source_bars) - 1)
            aggregation_map[agg_idx] = (source_start, source_end)
    else:
        for i in range(len(source_bars)):
            aggregation_map[i] = (i, i)

    state = AppState(
        source_bars=source_bars,
        aggregated_bars=aggregated_bars,
        aggregation_map=aggregation_map,
        aggregator=aggregator,
        data_file=data_file,
        resolution_minutes=resolution_minutes,
        total_source_bars=total_source_bars,
        window_offset=window_offset,
        cached_dataframe=full_df,
        mode=mode,
    )

    logger.info(f"Initialized Replay View with {len(source_bars)} bars")


# ============================================================================
# Wire up routers
# ============================================================================

from .routers import (
    dag_router,
    reference_router,
    feedback_router,
    auth_router,
)
from .routers.auth import get_current_user, is_multi_tenant as auth_is_multi_tenant

app.include_router(dag_router)
app.include_router(reference_router)
app.include_router(feedback_router)
app.include_router(auth_router)


# ============================================================================
# Static file mounts
# ============================================================================


def mount_static_files():
    """Mount static files from either production or development location."""
    project_root = Path(__file__).parent.parent.parent

    # Try production location first (/app/static in Docker)
    prod_static = project_root / "static"
    if prod_static.exists():
        assets_dir = prod_static / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="react-assets")
            logger.info(f"Mounted assets from production: {assets_dir}")
        return prod_static

    # Fall back to development location
    dev_static = project_root / "frontend" / "dist"
    if dev_static.exists():
        assets_dir = dev_static / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="react-assets")
            logger.info(f"Mounted assets from development: {assets_dir}")
        return dev_static

    return None


# Mount static files at module load
_static_dir = mount_static_files()


@app.get("/vite.svg")
async def vite_svg():
    """Serve vite.svg for React frontend."""
    static_dir = get_static_dir()
    if static_dir:
        svg_path = static_dir / "vite.svg"
        if svg_path.exists():
            return FileResponse(str(svg_path), media_type="image/svg+xml")
    return HTMLResponse(content="", status_code=404)


@app.get("/app-preview.png")
async def app_preview():
    """Serve app preview image for landing page."""
    static_dir = get_static_dir()
    if static_dir:
        img_path = static_dir / "app-preview.png"
        if img_path.exists():
            return FileResponse(str(img_path), media_type="image/png")
    return HTMLResponse(content="", status_code=404)


# SPA fallback: serve index.html for non-API, non-asset routes
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """
    SPA fallback handler for client-side routing.

    Serves index.html for any route that:
    - Is not an API endpoint (/api/*)
    - Is not a static asset (/assets/*)
    - Is not a known file (vite.svg, etc.)
    """
    # Don't handle API routes
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    # Don't handle asset routes (they're mounted)
    if full_path.startswith("assets/"):
        raise HTTPException(status_code=404, detail="Not found")

    # Serve index.html for SPA routing
    static_dir = get_static_dir()
    if static_dir:
        index_path = static_dir / "index.html"
        if index_path.exists():
            with open(index_path, 'r') as f:
                return HTMLResponse(content=f.read())

    raise HTTPException(status_code=404, detail="Not found")
