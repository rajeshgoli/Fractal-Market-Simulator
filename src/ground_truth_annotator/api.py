"""
FastAPI backend for Replay View.

Minimal server for:
- Serving OHLC bars for chart display
- Replay calibration and advance endpoints
- Playback feedback collection
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .storage import PlaybackFeedbackStorage
from .schemas import BarResponse
from ..data.ohlc_loader import load_ohlc
from ..swing_analysis.bar_aggregator import BarAggregator
from ..swing_analysis.types import Bar
from ..swing_analysis.dag import LegDetector, HierarchicalDetector

logger = logging.getLogger(__name__)


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
    calibration_bar_count: Optional[int] = None
    playback_feedback_storage: Optional[PlaybackFeedbackStorage] = None
    # Leg detector for incremental processing
    hierarchical_detector: Optional[LegDetector] = None
    # Visualization mode: 'calibration' or 'dag'
    mode: str = "calibration"


# Global state
state: Optional[AppState] = None

app = FastAPI(
    title="Replay View Server",
    description="Backend for Replay View swing detection",
    version="0.2.0",
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


# ============================================================================
# Static Page Routes
# ============================================================================


@app.get("/", response_class=HTMLResponse)
async def root():
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
    s = get_state()
    return {
        "session_id": "replay-session",
        "data_file": s.data_file or "",
        "resolution": f"{s.resolution_minutes}m",
        "window_size": len(s.source_bars),
        "window_offset": s.window_offset,
        "total_source_bars": s.total_source_bars,
        "calibration_bar_count": s.calibration_bar_count,
        "scale": "S",  # Default scale
        "created_at": "",
        "annotation_count": 0,
        "completed_scales": [],
    }


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
    mode: str = "calibration"
):
    """
    Initialize the application with data file.

    Args:
        data_file: Path to OHLC CSV data file
        resolution_minutes: Source data resolution in minutes
        window_size: Total bars to load for calibration
        target_bars: Target number of bars to display
        window_offset: Offset into source data
        cached_df: Optional cached DataFrame
        mode: Visualization mode ('calibration' or 'dag')
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

    # Initialize playback feedback storage
    playback_storage = PlaybackFeedbackStorage()

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
        playback_feedback_storage=playback_storage,
        mode=mode,
    )

    logger.info(f"Initialized Replay View with {len(source_bars)} bars")


# ============================================================================
# Wire up routers
# ============================================================================

from .routers import replay_router

app.include_router(replay_router)


# ============================================================================
# Static file mounts
# ============================================================================

# Mount React frontend assets
project_root = Path(__file__).parent.parent.parent
react_dist_dir = project_root / "frontend" / "dist"
react_assets_dir = react_dist_dir / "assets"
if react_assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(react_assets_dir)), name="react-assets")


@app.get("/vite.svg")
async def vite_svg():
    """Serve vite.svg for React frontend."""
    svg_path = react_dist_dir / "vite.svg"
    if svg_path.exists():
        return FileResponse(str(svg_path), media_type="image/svg+xml")
    return HTMLResponse(content="", status_code=404)
