"""
FastAPI backend for the Ground Truth Annotator.

Provides REST API endpoints for:
- Serving aggregated bars for chart display
- Creating, listing, and deleting annotations
- Session state management
- Cascade workflow (XL -> L -> M -> S scale progression)

This module contains:
- Application state (AppState dataclass)
- Core functions (get_state, get_or_create_session, init_app)
- Static page routes (/, /review, /replay)
- Core API endpoints (/api/health, /api/bars)

Domain-specific endpoints are in the routers/ package.
"""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .cascade_controller import CascadeController
from .comparison_analyzer import ComparisonResult
from .models import AnnotationSession
from .review_controller import ReviewController
from .storage import AnnotationStorage, ReviewStorage, PlaybackFeedbackStorage
from .schemas import BarResponse
from ..data.ohlc_loader import load_ohlc
from ..discretization import DiscretizationLog
from ..swing_analysis.bar_aggregator import BarAggregator
from ..swing_analysis.types import Bar

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    """Application state."""
    source_bars: List[Bar]
    aggregated_bars: List[Bar]
    aggregation_map: dict  # aggregated_index -> (source_start, source_end)
    storage: AnnotationStorage
    session: Optional[AnnotationSession]  # Lazy: created on first annotation
    scale: str
    target_bars: int
    cascade_controller: Optional[CascadeController] = None
    aggregator: Optional[BarAggregator] = None
    comparison_report: Optional[dict] = None  # Latest comparison report
    review_storage: Optional[ReviewStorage] = None
    review_controller: Optional[ReviewController] = None
    comparison_results: Optional[Dict[str, ComparisonResult]] = None  # Cached comparison
    # Fields for session/next endpoint
    data_file: Optional[str] = None
    storage_dir: Optional[str] = None
    resolution_minutes: int = 1
    total_source_bars: int = 0  # Total bars in file (before offset/windowing)
    window_offset: int = 0  # Offset into source data (for lazy session creation)
    cascade_enabled: bool = False
    # Cached DataFrame to avoid re-reading file on next window
    cached_dataframe: Optional[pd.DataFrame] = None
    # Background precomputation tracking
    precompute_in_progress: bool = False
    precompute_thread: Optional[threading.Thread] = None
    # Discretization state
    discretization_log: Optional[DiscretizationLog] = None
    # Replay playback state (backend-controlled data boundary)
    playback_index: Optional[int] = None  # Current visible bar index (None = full dataset)
    calibration_bar_count: Optional[int] = None  # Bars loaded for calibration
    # Playback feedback storage
    playback_feedback_storage: Optional[PlaybackFeedbackStorage] = None


# Global state
state: Optional[AppState] = None

app = FastAPI(
    title="Ground Truth Annotator",
    description="Two-click swing annotation tool",
    version="0.1.0",
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_state() -> AppState:
    """Get the application state."""
    if state is None:
        raise HTTPException(
            status_code=500,
            detail="Application not initialized. Start server with --data flag."
        )
    return state


def get_or_create_session(s: AppState) -> AnnotationSession:
    """
    Get the current session or create one if it doesn't exist.

    Sessions are created lazily to avoid orphan session files when using
    the server for replay-only mode (which doesn't need sessions).

    Args:
        s: The application state

    Returns:
        The annotation session (creating one if necessary)
    """
    if s.session is not None:
        return s.session

    # Create session on first access
    resolution_str = f"{s.resolution_minutes}m"
    session = s.storage.create_session(
        data_file=s.data_file,
        resolution=resolution_str,
        window_size=len(s.source_bars),
        window_offset=s.window_offset
    )
    logger.info(f"Lazily created session {session.session_id}")

    # Store in state
    s.session = session

    # Initialize cascade controller's session reference if in cascade mode
    if s.cascade_controller:
        s.cascade_controller._session = session

    return session


# Re-export start_precomputation_if_ready from comparison router for use by annotations router
def start_precomputation_if_ready(s: AppState) -> None:
    """Start background precomputation if conditions are met."""
    from .routers.comparison import start_precomputation_if_ready as _start_precomputation
    _start_precomputation(s)


# ============================================================================
# Static Page Routes
# ============================================================================


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the annotation UI."""
    module_dir = Path(__file__).parent
    index_path = module_dir / "static" / "index.html"

    if not index_path.exists():
        return HTMLResponse(
            content="<h1>Ground Truth Annotator</h1><p>Frontend not found. Place index.html in static/</p>",
            status_code=200
        )

    with open(index_path, 'r') as f:
        return HTMLResponse(content=f.read())


@app.get("/review", response_class=HTMLResponse)
async def review_page():
    """Serve the Review Mode UI."""
    module_dir = Path(__file__).parent
    review_path = module_dir / "static" / "review.html"

    if not review_path.exists():
        return HTMLResponse(
            content="<h1>Review Mode</h1><p>review.html not found. Place review.html in static/</p>",
            status_code=200
        )

    with open(review_path, 'r') as f:
        return HTMLResponse(content=f.read())


@app.get("/replay", response_class=HTMLResponse)
async def replay_page():
    """Serve the Replay View UI - React frontend."""
    project_root = Path(__file__).parent.parent.parent
    react_index = project_root / "frontend" / "dist" / "index.html"

    if react_index.exists():
        with open(react_index, 'r') as f:
            return HTMLResponse(content=f.read())

    return HTMLResponse(
        content="<h1>Replay View</h1><p>React build not found. Run 'npm run build' in frontend/</p>",
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
    }


@app.get("/api/bars", response_model=List[BarResponse])
async def get_bars(
    scale: Optional[str] = Query(None, description="Scale to get bars for (XL, L, M, S)"),
    limit: Optional[int] = Query(None, description="Limit to first N source bars (for calibration window)")
):
    """
    Get aggregated bars for chart display.

    Returns bars aggregated to the target count for efficient visualization.
    Scale options: S (source), M (~800 bars), L (~200 bars), XL (~50 bars)

    If limit is specified, only bars derived from the first N source bars are returned.
    This is used during calibration to avoid loading bars beyond the calibration window.

    When playback_index is set (via /api/replay/calibrate or /api/replay/advance),
    it takes precedence over limit for determining the maximum visible source bar.
    """
    s = get_state()

    # Compute effective limit based on playback_index (backend-controlled data boundary)
    # playback_index is the last visible bar index, so effective_limit = playback_index + 1
    effective_limit = limit
    if s.playback_index is not None:
        playback_limit = s.playback_index + 1
        if effective_limit is not None:
            effective_limit = min(effective_limit, playback_limit)
        else:
            effective_limit = playback_limit
    # Use effective_limit instead of limit for all filtering below
    limit = effective_limit

    # If scale specified and cascade controller available, use cascade bars
    if scale and s.cascade_controller:
        try:
            scale_bars = s.cascade_controller.get_bars_for_scale(scale)
            agg_map = s.cascade_controller.get_aggregation_map(scale)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        bars = []
        for agg_bar in scale_bars:
            source_start, source_end = agg_map.get(agg_bar.index, (agg_bar.index, agg_bar.index))
            # Apply limit: only include bars where source_end_index < limit
            if limit is not None and source_end > limit - 1:
                break
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

    # Handle scale without cascade controller (e.g., Replay View)
    if scale and s.aggregator:
        # Scale target bar counts (matching CascadeController.SCALE_TARGET_BARS)
        scale_targets = {"XL": 50, "L": 200, "M": 800, "S": None}
        target = scale_targets.get(scale.upper())

        if scale.upper() == "S" or target is None:
            # S scale: return source bars directly with 1:1 mapping
            bars = []
            source_bars_to_use = s.source_bars[:limit] if limit is not None else s.source_bars
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
        else:
            # Aggregate to target bar count
            # If limit specified, create a temporary aggregator for the limited source bars
            if limit is not None:
                limited_bars = s.source_bars[:limit]
                temp_aggregator = BarAggregator(limited_bars)
                agg_bars = temp_aggregator.aggregate_to_target_bars(target)
                source_bar_count = limit
            else:
                agg_bars = s.aggregator.aggregate_to_target_bars(target)
                source_bar_count = len(s.source_bars)

            bars_per_candle = source_bar_count // target if source_bar_count > target else 1
            bars = []
            for i, agg_bar in enumerate(agg_bars):
                source_start = i * bars_per_candle
                source_end = min(source_start + bars_per_candle - 1, source_bar_count - 1)
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
    storage_dir: str = "annotation_sessions",
    resolution_minutes: int = 1,
    window_size: int = 50000,
    scale: str = "S",
    target_bars: int = 200,
    cascade: bool = False,
    window_offset: int = 0,
    cached_df: Optional[pd.DataFrame] = None
):
    """
    Initialize the application with data file.

    Args:
        data_file: Path to OHLC CSV data file
        storage_dir: Directory for storing annotation sessions
        resolution_minutes: Source data resolution in minutes
        window_size: Total bars to load
        scale: Scale to annotate (S, M, L, XL) - ignored if cascade=True
        target_bars: Target number of bars to display - ignored if cascade=True
        cascade: Enable XL -> L -> M -> S cascade workflow
        window_offset: Offset into source data (for random window selection)
        cached_df: Optional cached DataFrame to avoid re-reading file from disk
    """
    global state

    # Load source data (use cache if available)
    if cached_df is not None:
        logger.info(f"Using cached DataFrame ({len(cached_df)} bars)")
        df = cached_df
    else:
        logger.info(f"Loading data from {data_file}...")
        df, gaps = load_ohlc(data_file)

    # Store total bars before any slicing (for session/next random offset)
    total_source_bars = len(df)

    # Keep a reference to the full DataFrame for caching
    full_df = df

    # Apply offset and limit to window size
    # Load extra bars beyond calibration window for forward playback in replay mode
    # The calibration window uses window_size bars, and we load an additional buffer
    # for streaming playback beyond calibration
    playback_buffer = window_size  # Load same amount extra for playback (2x total)
    total_bars_to_load = window_size + playback_buffer

    if window_offset > 0:
        df = df.iloc[window_offset:]
        logger.info(f"Applied offset of {window_offset} bars")

    if len(df) > total_bars_to_load:
        df = df.head(total_bars_to_load)
        logger.info(f"Limited to {total_bars_to_load} bars (calibration: {window_size}, playback buffer: {playback_buffer})")

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

    # Initialize storage
    storage = AnnotationStorage(storage_dir)

    # Session creation is lazy for non-cascade mode (replay-only won't create orphan sessions)
    # Cascade mode requires session immediately for CascadeController
    session = None
    cascade_controller = None
    if cascade:
        # Cascade mode: create session immediately (annotation workflow)
        resolution_str = f"{resolution_minutes}m"
        session = storage.create_session(
            data_file=data_file,
            resolution=resolution_str,
            window_size=len(source_bars),
            window_offset=window_offset
        )
        logger.info(f"Created session {session.session_id} (cascade mode)")
        cascade_controller = CascadeController(
            session=session,
            source_bars=source_bars,
            aggregator=aggregator
        )
        # Use cascade's current scale and bars
        scale = cascade_controller.get_current_scale()
        aggregated_bars = cascade_controller.get_bars_for_scale(scale)
        aggregation_map = cascade_controller.get_aggregation_map(scale)
        logger.info(f"Cascade mode enabled, starting at scale {scale}")
    else:
        # Non-cascade mode: use fixed aggregation
        aggregated_bars = aggregator.aggregate_to_target_bars(target_bars)
        logger.info(f"Aggregated to {len(aggregated_bars)} display bars")

        # Build aggregation map (agg_index -> source indices range)
        aggregation_map = {}
        if len(source_bars) > target_bars:
            bars_per_candle = len(source_bars) // target_bars
            for agg_idx in range(len(aggregated_bars)):
                source_start = agg_idx * bars_per_candle
                source_end = min(source_start + bars_per_candle - 1, len(source_bars) - 1)
                aggregation_map[agg_idx] = (source_start, source_end)
        else:
            # No aggregation - 1:1 mapping
            for i in range(len(source_bars)):
                aggregation_map[i] = (i, i)

    # Initialize review storage (controller created lazily on /api/review/start)
    review_storage = ReviewStorage(storage_dir)

    state = AppState(
        source_bars=source_bars,
        aggregated_bars=aggregated_bars,
        aggregation_map=aggregation_map,
        storage=storage,
        session=session,
        scale=scale,
        target_bars=target_bars,
        cascade_controller=cascade_controller,
        aggregator=aggregator,
        review_storage=review_storage,
        # Fields for session/next endpoint
        data_file=data_file,
        storage_dir=storage_dir,
        resolution_minutes=resolution_minutes,
        total_source_bars=total_source_bars,
        window_offset=window_offset,
        cascade_enabled=cascade,
        # Cache full DataFrame to avoid re-reading on next window
        cached_dataframe=full_df
    )

    session_mode = "cascade" if cascade else "lazy"
    logger.info(f"Initialized annotator with {len(source_bars)} bars, scale={scale}, session={session_mode}")


# ============================================================================
# Wire up routers
# ============================================================================

from .routers import (
    annotations_router,
    session_router,
    cascade_router,
    comparison_router,
    review_router,
    discretization_router,
    replay_router,
)

app.include_router(annotations_router)
app.include_router(session_router)
app.include_router(cascade_router)
app.include_router(comparison_router)
app.include_router(review_router)
app.include_router(discretization_router)
app.include_router(replay_router)


# ============================================================================
# Static file mounts
# ============================================================================

# Mount React frontend assets (from Vite build)
project_root = Path(__file__).parent.parent.parent
react_dist_dir = project_root / "frontend" / "dist"
react_assets_dir = react_dist_dir / "assets"
if react_assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(react_assets_dir)), name="react-assets")


# Serve vite.svg (React favicon)
@app.get("/vite.svg")
async def vite_svg():
    """Serve vite.svg for React frontend."""
    svg_path = react_dist_dir / "vite.svg"
    if svg_path.exists():
        return FileResponse(str(svg_path), media_type="image/svg+xml")
    return HTMLResponse(content="", status_code=404)


# Mount static files directory (legacy vanilla JS)
module_dir = Path(__file__).parent
static_dir = module_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
