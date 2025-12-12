"""
FastAPI backend for the lightweight swing validator.

Provides REST API endpoints for:
- Sampling random intervals
- Recording votes
- Retrieving session statistics
- Exporting results
- Progressive loading window management
"""

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .models import (
    OHLCBar,
    Scale,
    SamplerConfig,
    SessionStats,
    SwingCandidate,
    ValidationSample,
    VoteRequest,
)
from .sampler import IntervalSampler
from .storage import VoteStorage
from .progressive_loader import ProgressiveLoader, DataWindow

logger = logging.getLogger(__name__)

# Global instances (initialized on startup)
sampler: Optional[IntervalSampler] = None
storage: Optional[VoteStorage] = None
progressive_loader: Optional[ProgressiveLoader] = None

app = FastAPI(
    title="Lightweight Swing Validator",
    description="Human-in-the-loop validation tool for swing detection",
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


def get_sampler() -> IntervalSampler:
    """Get the sampler instance."""
    if sampler is None:
        raise HTTPException(
            status_code=500,
            detail="Sampler not initialized. Start server with --data flag."
        )
    return sampler


def get_storage() -> VoteStorage:
    """Get the storage instance."""
    if storage is None:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    return storage


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main validation UI."""
    # Look for index.html in the same directory as this file
    module_dir = Path(__file__).parent
    index_path = module_dir / "static" / "index.html"

    if not index_path.exists():
        return HTMLResponse(
            content="<h1>Lightweight Swing Validator</h1><p>Frontend not found. Place index.html in static/</p>",
            status_code=200
        )

    with open(index_path, 'r') as f:
        return HTMLResponse(content=f.read())


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "sampler_initialized": sampler is not None,
        "storage_initialized": storage is not None,
    }


@app.get("/api/sample", response_model=ValidationSample)
async def get_sample(scale: Optional[Scale] = Query(None, description="Specific scale to sample")):
    """
    Get a random validation sample.

    Returns a random time interval with detected swing candidates for validation.
    """
    s = get_sampler()
    try:
        sample = s.sample(scale)
        return sample
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Error generating sample")
        raise HTTPException(status_code=500, detail=f"Failed to generate sample: {e}")


@app.post("/api/vote")
async def submit_vote(request: VoteRequest):
    """
    Submit validation votes for a sample.

    Records votes for individual swings and overall assessment.
    """
    st = get_storage()

    # We need sample metadata - for now, store minimal info
    # In a more robust implementation, we'd cache recent samples
    try:
        result = st.record_vote(
            request,
            sample_scale=Scale.S,  # TODO: Pass actual scale
            interval_start=0,
            interval_end=0,
        )
        return {"status": "ok", "sample_id": result.sample_id}
    except Exception as e:
        logger.exception("Error recording vote")
        raise HTTPException(status_code=500, detail=f"Failed to record vote: {e}")


@app.get("/api/stats", response_model=SessionStats)
async def get_stats():
    """Get current session statistics."""
    st = get_storage()
    return st.get_stats()


@app.get("/api/data-summary")
async def get_data_summary():
    """Get summary of loaded market data."""
    s = get_sampler()
    return s.get_data_summary()


@app.get("/api/export/csv")
async def export_csv():
    """Export validation results to CSV."""
    st = get_storage()
    try:
        filepath = st.export_csv(f"validation_results/export_{st.session_id}.csv")
        return FileResponse(
            filepath,
            media_type="text/csv",
            filename=f"validation_export_{st.session_id}.csv"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


@app.get("/api/export/json")
async def export_json():
    """Export validation results to JSON."""
    st = get_storage()
    try:
        filepath = st.export_json(f"validation_results/export_{st.session_id}.json")
        return FileResponse(
            filepath,
            media_type="application/json",
            filename=f"validation_export_{st.session_id}.json"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


@app.get("/api/sessions")
async def list_sessions():
    """List available validation sessions."""
    return VoteStorage.list_sessions()


@app.get("/api/windows")
async def list_windows():
    """
    List all data windows (for progressive loading).

    Returns list of windows with their status and date ranges.
    """
    if progressive_loader is None:
        return {"windows": [], "is_progressive": False}

    return {
        "windows": progressive_loader.list_windows(),
        "is_progressive": progressive_loader.is_large_file,
        "current_window_id": progressive_loader.current_window_id
    }


@app.get("/api/windows/{window_id}")
async def switch_window(window_id: str):
    """
    Switch to a different data window.

    Args:
        window_id: ID of the window to activate.

    Returns:
        Updated data summary for the new window.
    """
    global sampler

    if progressive_loader is None:
        raise HTTPException(status_code=400, detail="Progressive loading not enabled")

    if not progressive_loader.set_current_window(window_id):
        raise HTTPException(status_code=404, detail=f"Window {window_id} not found or not ready")

    # Create new sampler for the window
    window = progressive_loader.get_current_window()
    if window is None:
        raise HTTPException(status_code=500, detail="Failed to get window")

    config = SamplerConfig(data_file=progressive_loader.filepath)
    sampler = IntervalSampler.from_bars(
        bars=window.bars,
        scale_config=window.scale_config,
        config=config,
        window_id=window.window_id,
        window_start=window.start_timestamp,
        window_end=window.end_timestamp
    )

    return {
        "status": "ok",
        "window_id": window_id,
        "data_summary": sampler.get_data_summary()
    }


@app.post("/api/windows/next")
async def next_window():
    """
    Switch to the next available data window.

    Rotates through windows to cover diverse market regimes.
    """
    global sampler

    if progressive_loader is None:
        raise HTTPException(status_code=400, detail="Progressive loading not enabled")

    window = progressive_loader.get_next_window()
    if window is None:
        raise HTTPException(status_code=404, detail="No more windows available")

    config = SamplerConfig(data_file=progressive_loader.filepath)
    sampler = IntervalSampler.from_bars(
        bars=window.bars,
        scale_config=window.scale_config,
        config=config,
        window_id=window.window_id,
        window_start=window.start_timestamp,
        window_end=window.end_timestamp
    )

    return {
        "status": "ok",
        "window_id": window.window_id,
        "data_summary": sampler.get_data_summary()
    }


@app.get("/api/loading-status")
async def loading_status():
    """
    Get current loading progress for progressive loading.

    Returns progress information including loaded bars and windows.
    """
    if progressive_loader is None:
        return {
            "is_progressive": False,
            "is_complete": True,
            "percent_complete": 100
        }

    progress = progressive_loader.get_loading_progress()
    return {
        "is_progressive": progressive_loader.is_large_file,
        **progress.to_dict()
    }


def init_app(
    data_file: str,
    storage_dir: str = "validation_results",
    seed: Optional[int] = None,
    resolution_minutes: int = 1,
    calibration_window: Optional[int] = None
):
    """
    Initialize the application with data file.

    For large files (>100k bars), uses progressive loading for fast startup.

    Args:
        data_file: Path to OHLC CSV data file
        storage_dir: Directory for storing validation results
        seed: Random seed for reproducible sampling
        resolution_minutes: Source data resolution in minutes (default: 1)
        calibration_window: Calibration window size in bars (default: auto)
    """
    global sampler, storage, progressive_loader

    # Initialize progressive loader (will determine if file is large)
    progressive_loader = ProgressiveLoader(
        filepath=data_file,
        seed=seed,
        resolution_minutes=resolution_minutes,
        calibration_window=calibration_window
    )

    # Load initial window (fast for large files)
    window = progressive_loader.load_initial_window()

    # Create sampler from the loaded window
    config = SamplerConfig(data_file=data_file)

    if progressive_loader.is_large_file:
        # Use window-based sampler
        sampler = IntervalSampler.from_bars(
            bars=window.bars,
            scale_config=window.scale_config,
            config=config,
            seed=seed,
            window_id=window.window_id,
            window_start=window.start_timestamp,
            window_end=window.end_timestamp
        )
        # Start background loading of additional windows
        progressive_loader.start_background_loading()
    else:
        # Small file - sampler has all data
        sampler = IntervalSampler.from_bars(
            bars=window.bars,
            scale_config=window.scale_config,
            config=config,
            seed=seed
        )

    storage = VoteStorage(storage_dir=storage_dir)

    logger.info(f"Initialized validator with data from {data_file}")


# Mount static files directory
module_dir = Path(__file__).parent
static_dir = module_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
