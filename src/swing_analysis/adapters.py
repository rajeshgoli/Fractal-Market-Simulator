"""
Compatibility Adapters for Swing Detection

Provides conversion functions between the new hierarchical SwingNode format
and the legacy ReferenceSwing format. This enables gradual migration of
consumers to the new system.

The adapter layer allows existing code that expects ReferenceSwing and
detect_swings() to continue working while components are updated one by one.
"""

from typing import Dict, List, Optional
from decimal import Decimal

import pandas as pd

from .swing_node import SwingNode
from .swing_detector import ReferenceSwing
from .hierarchical_detector import (
    HierarchicalDetector,
    calibrate,
    calibrate_from_dataframe,
    dataframe_to_bars,
)
from .swing_config import SwingConfig


def swing_node_to_reference_swing(node: SwingNode) -> ReferenceSwing:
    """
    Convert hierarchical SwingNode to legacy ReferenceSwing.

    This allows existing consumers to work without modification.
    Some legacy fields are set to default/computed values since the
    hierarchical model doesn't track them.

    Args:
        node: SwingNode from the hierarchical detector.

    Returns:
        ReferenceSwing with equivalent data in legacy format.

    Example:
        >>> from decimal import Decimal
        >>> node = SwingNode(
        ...     swing_id="abc12345",
        ...     high_bar_index=100,
        ...     high_price=Decimal("5100.00"),
        ...     low_bar_index=150,
        ...     low_price=Decimal("5000.00"),
        ...     direction="bull",
        ...     status="active",
        ...     formed_at_bar=150,
        ... )
        >>> legacy = swing_node_to_reference_swing(node)
        >>> legacy.high_price
        5100.0
        >>> legacy.direction
        'bull'
    """
    high = float(node.high_price)
    low = float(node.low_price)
    size = high - low

    # Calculate legacy fib levels
    if node.direction == "bull":
        # Bull swing: defending low, so levels are calculated from low up
        level_0382 = low + size * 0.382
        level_2x = low + size * 2.0
    else:
        # Bear swing: defending high, so levels are calculated from high down
        level_0382 = high - size * 0.382
        level_2x = high - size * 2.0

    return ReferenceSwing(
        high_price=high,
        high_bar_index=node.high_bar_index,
        low_price=low,
        low_bar_index=node.low_bar_index,
        size=size,
        direction=node.direction,
        level_0382=level_0382,
        level_2x=level_2x,
        # Legacy ranking fields - not meaningful in hierarchical model
        rank=0,
        impulse=0.0,
        size_rank=None,
        impulse_rank=None,
        combined_score=None,
        # Legacy structural fields - computed differently in hierarchical model
        structurally_separated=True,  # Assumed true since formed
        containing_swing_id=node.parents[0].swing_id if node.parents else None,
        fib_confluence_score=0.0,
        # Legacy separation details - not tracked in hierarchical model
        separation_is_anchor=len(node.parents) == 0,
        separation_distance_fib=None,
        separation_minimum_fib=None,
        separation_from_swing_id=None,
    )


def reference_swing_to_swing_node(
    ref: ReferenceSwing,
    swing_id: Optional[str] = None,
    formed_at_bar: Optional[int] = None,
) -> SwingNode:
    """
    Convert legacy ReferenceSwing to hierarchical SwingNode.

    This is useful for importing legacy data into the new system.

    Args:
        ref: ReferenceSwing from legacy detector.
        swing_id: Optional ID to assign. If None, generates a new one.
        formed_at_bar: Bar index when formed. If None, uses the later
            of high_bar_index or low_bar_index.

    Returns:
        SwingNode with equivalent data.

    Example:
        >>> ref = ReferenceSwing(
        ...     high_price=5100.0,
        ...     high_bar_index=100,
        ...     low_price=5000.0,
        ...     low_bar_index=150,
        ...     size=100.0,
        ...     direction="bull",
        ... )
        >>> node = reference_swing_to_swing_node(ref)
        >>> node.direction
        'bull'
    """
    if formed_at_bar is None:
        formed_at_bar = max(ref.high_bar_index, ref.low_bar_index)

    return SwingNode(
        swing_id=swing_id or SwingNode.generate_id(),
        high_bar_index=ref.high_bar_index,
        high_price=Decimal(str(ref.high_price)),
        low_bar_index=ref.low_bar_index,
        low_price=Decimal(str(ref.low_price)),
        direction=ref.direction,
        status="active",
        formed_at_bar=formed_at_bar,
    )


def detect_swings_compat(
    df: pd.DataFrame,
    config: Optional[SwingConfig] = None,
    **kwargs,
) -> Dict[str, List[ReferenceSwing]]:
    """
    Compatibility wrapper matching old detect_swings() return format.

    Uses the new hierarchical detector internally but returns results
    grouped by scale (XL/L/M/S) for backward compatibility.

    Note: The scales are derived from swing size percentiles, not the
    original detect_swings() behavior. This is a compatibility shim.

    Args:
        df: DataFrame with OHLC data.
        config: SwingConfig for the detector. If None, uses defaults.
        **kwargs: Ignored (for signature compatibility with legacy code).

    Returns:
        Dict mapping scale names ("XL", "L", "M", "S") to lists of
        ReferenceSwing objects.

    Example:
        >>> import pandas as pd
        >>> df = pd.read_csv("market_data.csv")
        >>> result = detect_swings_compat(df)
        >>> print(f"XL swings: {len(result['XL'])}")
        >>> print(f"S swings: {len(result['S'])}")
    """
    # Run new detector
    detector, _events = calibrate_from_dataframe(df, config)

    # Convert to legacy format
    active_nodes = detector.get_active_swings()
    legacy_swings = [swing_node_to_reference_swing(node) for node in active_nodes]

    # Group by "scale" based on size quartiles (legacy behavior)
    return _group_by_legacy_scale(legacy_swings)


def _group_by_legacy_scale(
    swings: List[ReferenceSwing],
) -> Dict[str, List[ReferenceSwing]]:
    """
    Group swings into S/M/L/XL buckets based on size percentiles.

    This is a compatibility shim — the hierarchical model doesn't use
    discrete scales, but some consumers expect this format.

    Distribution:
    - XL: Top 10% by size
    - L: Next 15% (10-25%)
    - M: Next 25% (25-50%)
    - S: Bottom 50%

    Args:
        swings: List of ReferenceSwing objects.

    Returns:
        Dict with keys "XL", "L", "M", "S" mapping to swing lists.
    """
    result: Dict[str, List[ReferenceSwing]] = {"XL": [], "L": [], "M": [], "S": []}

    if not swings:
        return result

    # Sort by size descending
    sorted_swings = sorted(swings, key=lambda s: s.size, reverse=True)
    n = len(sorted_swings)

    # Calculate thresholds
    xl_cutoff = max(1, int(n * 0.10))  # Top 10%
    l_cutoff = max(xl_cutoff, int(n * 0.25))  # Top 25%
    m_cutoff = max(l_cutoff, int(n * 0.50))  # Top 50%

    # Assign scales
    for i, swing in enumerate(sorted_swings):
        swing.rank = i + 1  # Update rank while we're at it
        if i < xl_cutoff:
            result["XL"].append(swing)
        elif i < l_cutoff:
            result["L"].append(swing)
        elif i < m_cutoff:
            result["M"].append(swing)
        else:
            result["S"].append(swing)

    return result


def convert_swings_to_legacy_dict(
    nodes: List[SwingNode],
) -> Dict[str, List[Dict]]:
    """
    Convert SwingNode list to legacy dict format used by some APIs.

    Returns the format expected by discretization and some API endpoints:
    {"XL": [...], "L": [...], "M": [...], "S": [...]}

    Each swing is converted to a dict via ReferenceSwing.to_dict().

    Args:
        nodes: List of SwingNode objects.

    Returns:
        Dict mapping scale names to lists of swing dicts.
    """
    legacy_swings = [swing_node_to_reference_swing(node) for node in nodes]
    grouped = _group_by_legacy_scale(legacy_swings)

    return {
        scale: [swing.to_dict() for swing in swings]
        for scale, swings in grouped.items()
    }
