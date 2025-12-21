"""Core data types for swing analysis."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Bar:
    """Single OHLC bar"""
    index: int
    timestamp: int
    open: float
    high: float
    low: float
    close: float

    @property
    def date(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)
