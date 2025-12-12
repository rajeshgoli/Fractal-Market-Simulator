"""
FastAPI backend for the lightweight swing validator.

Provides REST API endpoints for:
- Sampling random intervals
- Recording votes
- Retrieving session statistics
- Exporting results
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

logger = logging.getLogger(__name__)

# Global instances (initialized on startup)
sampler: Optional[IntervalSampler] = None
storage: Optional[VoteStorage] = None

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


def init_app(data_file: str, storage_dir: str = "validation_results", seed: Optional[int] = None):
    """
    Initialize the application with data file.

    Args:
        data_file: Path to OHLC CSV data file
        storage_dir: Directory for storing validation results
        seed: Random seed for reproducible sampling
    """
    global sampler, storage

    config = SamplerConfig(data_file=data_file)
    sampler = IntervalSampler(config, seed=seed)
    storage = VoteStorage(storage_dir=storage_dir)

    logger.info(f"Initialized validator with data from {data_file}")


# Mount static files directory
module_dir = Path(__file__).parent
static_dir = module_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
