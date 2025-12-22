"""
Shared test fixtures and helpers for swing analysis tests.
"""

import pytest
from src.swing_analysis.types import Bar


def make_bar(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    timestamp: int = None,
) -> Bar:
    """Helper to create Bar objects for testing.

    Args:
        index: Bar index in the sequence
        open_: Opening price
        high: High price
        low: Low price
        close: Closing price
        timestamp: Unix timestamp (defaults to 1700000000 + index * 60)

    Returns:
        Bar object for use in detector tests
    """
    return Bar(
        index=index,
        timestamp=timestamp or 1700000000 + index * 60,
        open=open_,
        high=high,
        low=low,
        close=close,
    )
