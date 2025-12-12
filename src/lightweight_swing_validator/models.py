"""
Data models for the lightweight swing validator.

Defines Pydantic models for API requests/responses and internal data structures.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Scale(str, Enum):
    """Structural scale for swing detection."""
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"


class OHLCBar(BaseModel):
    """Single OHLC bar for charting."""
    timestamp: int = Field(description="Unix timestamp in seconds")
    open: float
    high: float
    low: float
    close: float


class SwingCandidate(BaseModel):
    """A detected swing candidate for validation."""
    swing_id: str = Field(description="Unique identifier for this swing")
    scale: Scale
    is_bull: bool = Field(description="True for bullish swing, False for bearish")
    high_price: float
    low_price: float
    high_timestamp: int = Field(description="Unix timestamp of swing high")
    low_timestamp: int = Field(description="Unix timestamp of swing low")
    size: float = Field(description="Swing size (high - low)")
    duration_bars: int = Field(description="Number of bars in swing")
    levels: Dict[str, float] = Field(default_factory=dict, description="Fibonacci levels")
    rank: int = Field(description="Rank among candidates (1=best)")


class ValidationSample(BaseModel):
    """A sampled interval with swing candidates for validation."""
    sample_id: str = Field(description="Unique identifier for this sample")
    scale: Scale
    interval_start: int = Field(description="Unix timestamp of interval start")
    interval_end: int = Field(description="Unix timestamp of interval end")
    bars: List[OHLCBar] = Field(description="OHLC bars for the interval")
    candidates: List[SwingCandidate] = Field(description="Top swing candidates (up to 3)")
    context_bars_before: int = Field(default=20, description="Bars shown before interval")
    context_bars_after: int = Field(default=10, description="Bars shown after interval")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class VoteType(str, Enum):
    """Vote type for swing validation."""
    UP = "up"
    DOWN = "down"
    SKIP = "skip"


class Vote(BaseModel):
    """A single vote on a swing candidate."""
    swing_id: str
    vote: VoteType
    comment: Optional[str] = None
    voted_at: datetime = Field(default_factory=datetime.utcnow)


class VoteRequest(BaseModel):
    """Request to submit votes for a sample."""
    sample_id: str
    swing_votes: List[Vote] = Field(description="Votes for individual swings")
    found_right_swings: Optional[bool] = Field(
        None, description="Did we find the right top 3 swings?"
    )
    overall_comment: Optional[str] = None


class ValidationResult(BaseModel):
    """Persisted validation result for a sample."""
    sample_id: str
    scale: Scale
    interval_start: int
    interval_end: int
    swing_votes: List[Vote]
    found_right_swings: Optional[bool]
    overall_comment: Optional[str]
    validated_at: datetime = Field(default_factory=datetime.utcnow)


class SamplerConfig(BaseModel):
    """Configuration for the interval sampler."""
    data_file: str = Field(description="Path to CSV data file")
    instrument: str = Field(default="ES", description="Instrument symbol")
    min_interval_bars: int = Field(default=50, description="Minimum bars per interval")
    max_interval_bars: int = Field(default=200, description="Maximum bars per interval")
    context_before: int = Field(default=20, description="Bars to show before interval")
    context_after: int = Field(default=10, description="Bars to show after interval")
    top_k_swings: int = Field(default=3, description="Number of top swings to show")


class SessionStats(BaseModel):
    """Statistics for the current validation session."""
    total_samples: int = 0
    samples_validated: int = 0
    swings_approved: int = 0
    swings_rejected: int = 0
    swings_skipped: int = 0
    by_scale: Dict[str, Dict[str, int]] = Field(default_factory=dict)
