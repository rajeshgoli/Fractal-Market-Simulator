"""
FastAPI backend for the Ground Truth Annotator.

Provides REST API endpoints for:
- Serving aggregated bars for chart display
- Creating, listing, and deleting annotations
- Session state management
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .models import AnnotationSession, SwingAnnotation
from .storage import AnnotationStorage
from ..data.ohlc_loader import load_ohlc
from ..swing_analysis.bar_aggregator import BarAggregator
from ..swing_analysis.bull_reference_detector import Bar

logger = logging.getLogger(__name__)


# Pydantic models for API
class BarResponse(BaseModel):
    """A single OHLC bar for chart display."""
    index: int
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    source_start_index: int
    source_end_index: int


class AnnotationCreate(BaseModel):
    """Request to create a new annotation."""
    start_bar_index: int
    end_bar_index: int


class AnnotationResponse(BaseModel):
    """An annotation returned by the API."""
    annotation_id: str
    scale: str
    direction: str
    start_bar_index: int
    end_bar_index: int
    start_source_index: int
    end_source_index: int
    start_price: str
    end_price: str
    created_at: str
    window_id: str


class SessionResponse(BaseModel):
    """Session state returned by the API."""
    session_id: str
    data_file: str
    resolution: str
    window_size: int
    scale: str
    created_at: str
    annotation_count: int
    completed_scales: List[str]


@dataclass
class AppState:
    """Application state."""
    source_bars: List[Bar]
    aggregated_bars: List[Bar]
    aggregation_map: dict  # aggregated_index -> (source_start, source_end)
    storage: AnnotationStorage
    session: AnnotationSession
    scale: str
    target_bars: int


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


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "initialized": state is not None,
    }


@app.get("/api/bars", response_model=List[BarResponse])
async def get_bars():
    """
    Get aggregated bars for chart display.

    Returns bars aggregated to the target count for efficient visualization.
    """
    s = get_state()

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


@app.post("/api/annotations", response_model=AnnotationResponse)
async def create_annotation(request: AnnotationCreate):
    """
    Create a new swing annotation.

    Direction is inferred from price movement:
    - If start.high > end.high -> bull reference (downswing)
    - If start.low < end.low -> bear reference (upswing)
    """
    s = get_state()

    # Validate indices
    if request.start_bar_index < 0 or request.start_bar_index >= len(s.aggregated_bars):
        raise HTTPException(status_code=400, detail="Invalid start_bar_index")
    if request.end_bar_index < 0 or request.end_bar_index >= len(s.aggregated_bars):
        raise HTTPException(status_code=400, detail="Invalid end_bar_index")
    if request.start_bar_index == request.end_bar_index:
        raise HTTPException(status_code=400, detail="start and end must be different")

    start_bar = s.aggregated_bars[request.start_bar_index]
    end_bar = s.aggregated_bars[request.end_bar_index]

    # Get source indices
    start_source_start, start_source_end = s.aggregation_map.get(
        request.start_bar_index, (request.start_bar_index, request.start_bar_index)
    )
    end_source_start, end_source_end = s.aggregation_map.get(
        request.end_bar_index, (request.end_bar_index, request.end_bar_index)
    )

    # Infer direction from price movement
    # Bull reference = the swing before an upward move (swing went down)
    # Bear reference = the swing before a downward move (swing went up)
    if start_bar.high > end_bar.high:
        # Price went down: bull reference (downswing)
        direction = "bull"
        start_price = Decimal(str(start_bar.high))
        end_price = Decimal(str(end_bar.low))
    else:
        # Price went up: bear reference (upswing)
        direction = "bear"
        start_price = Decimal(str(start_bar.low))
        end_price = Decimal(str(end_bar.high))

    # Create annotation
    annotation = SwingAnnotation.create(
        scale=s.scale,
        direction=direction,
        start_bar_index=request.start_bar_index,
        end_bar_index=request.end_bar_index,
        start_source_index=start_source_start,
        end_source_index=end_source_end,
        start_price=start_price,
        end_price=end_price,
        window_id=s.session.session_id
    )

    # Save annotation
    s.storage.save_annotation(s.session.session_id, annotation)

    # Reload session to get updated annotation list
    s.session = s.storage.get_session(s.session.session_id)

    return AnnotationResponse(
        annotation_id=annotation.annotation_id,
        scale=annotation.scale,
        direction=annotation.direction,
        start_bar_index=annotation.start_bar_index,
        end_bar_index=annotation.end_bar_index,
        start_source_index=annotation.start_source_index,
        end_source_index=annotation.end_source_index,
        start_price=str(annotation.start_price),
        end_price=str(annotation.end_price),
        created_at=annotation.created_at.isoformat(),
        window_id=annotation.window_id
    )


@app.get("/api/annotations", response_model=List[AnnotationResponse])
async def list_annotations():
    """List all annotations for current scale."""
    s = get_state()

    annotations = s.storage.get_annotations(s.session.session_id, scale=s.scale)

    return [
        AnnotationResponse(
            annotation_id=ann.annotation_id,
            scale=ann.scale,
            direction=ann.direction,
            start_bar_index=ann.start_bar_index,
            end_bar_index=ann.end_bar_index,
            start_source_index=ann.start_source_index,
            end_source_index=ann.end_source_index,
            start_price=str(ann.start_price),
            end_price=str(ann.end_price),
            created_at=ann.created_at.isoformat(),
            window_id=ann.window_id
        )
        for ann in annotations
    ]


@app.delete("/api/annotations/{annotation_id}")
async def delete_annotation(annotation_id: str):
    """Delete an annotation by ID."""
    s = get_state()

    success = s.storage.delete_annotation(s.session.session_id, annotation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Reload session
    s.session = s.storage.get_session(s.session.session_id)

    return {"status": "ok", "annotation_id": annotation_id}


@app.get("/api/session", response_model=SessionResponse)
async def get_session():
    """Get current session state."""
    s = get_state()

    return SessionResponse(
        session_id=s.session.session_id,
        data_file=s.session.data_file,
        resolution=s.session.resolution,
        window_size=s.session.window_size,
        scale=s.scale,
        created_at=s.session.created_at.isoformat(),
        annotation_count=len(s.session.annotations),
        completed_scales=s.session.completed_scales
    )


def init_app(
    data_file: str,
    storage_dir: str = "annotation_sessions",
    resolution_minutes: int = 1,
    window_size: int = 50000,
    scale: str = "S",
    target_bars: int = 200
):
    """
    Initialize the application with data file.

    Args:
        data_file: Path to OHLC CSV data file
        storage_dir: Directory for storing annotation sessions
        resolution_minutes: Source data resolution in minutes
        window_size: Total bars to load
        scale: Scale to annotate (S, M, L, XL)
        target_bars: Target number of bars to display
    """
    global state

    logger.info(f"Loading data from {data_file}...")

    # Load source data
    df, gaps = load_ohlc(data_file)

    # Limit to window size
    if len(df) > window_size:
        df = df.head(window_size)
        logger.info(f"Limited to {window_size} bars")

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

    # Aggregate bars for display
    aggregator = BarAggregator(source_bars, resolution_minutes)
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

    # Initialize storage
    storage = AnnotationStorage(storage_dir)

    # Create or get session
    resolution_str = f"{resolution_minutes}m"
    session = storage.create_session(
        data_file=data_file,
        resolution=resolution_str,
        window_size=len(source_bars)
    )
    logger.info(f"Created session {session.session_id}")

    state = AppState(
        source_bars=source_bars,
        aggregated_bars=aggregated_bars,
        aggregation_map=aggregation_map,
        storage=storage,
        session=session,
        scale=scale,
        target_bars=target_bars
    )

    logger.info(f"Initialized annotator with {len(source_bars)} bars, scale={scale}")


# Mount static files directory
module_dir = Path(__file__).parent
static_dir = module_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
