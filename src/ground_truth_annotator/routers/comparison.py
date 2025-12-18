"""
Comparison router for Ground Truth Annotator.

Provides endpoints for comparing user annotations vs system detection:
- POST /api/compare - Run comparison
- GET /api/compare/report - Get full comparison report
- GET /api/compare/export - Export report as JSON or CSV

Also provides helper functions for background precomputation used by other modules.
"""

import logging
import threading
from typing import Dict, TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..comparison_analyzer import ComparisonAnalyzer, ComparisonResult
from ..schemas import (
    ComparisonRunResponse,
    ComparisonReportResponse,
    ComparisonSummary,
    ComparisonScaleResult,
    FalseNegativeItem,
    FalsePositiveItem,
)

if TYPE_CHECKING:
    from ..api import AppState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/compare", tags=["comparison"])


# ============================================================================
# Helper Functions (used by Review router as well)
# ============================================================================


def _ensure_comparison_run(s: "AppState") -> Dict[str, ComparisonResult]:
    """Ensure comparison has been run and cached."""
    from ..api import get_or_create_session

    if s.comparison_results is None:
        # Wait for precomputation if in progress
        if s.precompute_in_progress and s.precompute_thread:
            logger.info("Waiting for background precomputation to complete...")
            s.precompute_thread.join(timeout=30)  # Wait up to 30 seconds

        # If still not available, run synchronously
        if s.comparison_results is None:
            # Session must exist at this point (caller should have created it)
            session = get_or_create_session(s)
            analyzer = ComparisonAnalyzer(tolerance_pct=0.1)
            s.comparison_results = analyzer.compare_session(session, s.source_bars)
            # Also update the comparison report
            s.comparison_report = analyzer.generate_report(s.comparison_results)
    return s.comparison_results


def _precompute_comparison_background(s: "AppState") -> None:
    """
    Run comparison analysis in background thread.

    This allows the UI to remain responsive while the comparison is computed.
    Results are stored in AppState.comparison_results for later use.
    """
    try:
        logger.info("Starting background precomputation of system swings...")
        s.precompute_in_progress = True

        # Session should exist since this is called after annotation
        if s.session is None:
            logger.warning("Session is None in background precomputation, skipping")
            return

        analyzer = ComparisonAnalyzer(tolerance_pct=0.1)
        results = analyzer.compare_session(s.session, s.source_bars)
        report = analyzer.generate_report(results)

        # Store results
        s.comparison_results = results
        s.comparison_report = report

        logger.info("Background precomputation complete")
    except (ValueError, KeyError, TypeError, AttributeError, RuntimeError) as e:
        logger.error(f"Background precomputation failed: {e}")
    finally:
        s.precompute_in_progress = False


def start_precomputation_if_ready(s: "AppState") -> None:
    """
    Start background precomputation if conditions are met.

    Triggers early (after first annotation) to maximize time for computation
    to complete before user enters review mode.
    """
    if s.precompute_in_progress:
        return
    if s.comparison_results is not None:
        return
    if s.session is None or len(s.session.annotations) == 0:
        return  # Wait for at least one annotation

    # Start background thread
    s.precompute_thread = threading.Thread(
        target=_precompute_comparison_background,
        args=(s,),
        daemon=True
    )
    s.precompute_thread.start()
    logger.info("Started background precomputation thread (triggered by annotation)")


# ============================================================================
# Endpoints
# ============================================================================


@router.post("", response_model=ComparisonRunResponse)
async def run_comparison():
    """
    Run comparison between user annotations and system detection.

    Compares all annotations in the current session against system-detected
    swings on the source bars. Results are stored for later retrieval.
    """
    from ..api import get_state, get_or_create_session

    s = get_state()
    session = get_or_create_session(s)

    analyzer = ComparisonAnalyzer(tolerance_pct=0.1)

    # Run comparison on all scales that have annotations
    results = analyzer.compare_session(session, s.source_bars)

    # Generate report
    report = analyzer.generate_report(results)

    # Store report in state
    s.comparison_report = report

    # Create summary response
    summary = ComparisonSummary(
        total_user_annotations=report['summary']['total_user_annotations'],
        total_system_detections=report['summary']['total_system_detections'],
        total_matches=report['summary']['total_matches'],
        total_false_negatives=report['summary']['total_false_negatives'],
        total_false_positives=report['summary']['total_false_positives'],
        overall_match_rate=report['summary']['overall_match_rate'],
    )

    # Format message
    match_pct = int(summary.overall_match_rate * 100)
    message = (
        f"Match rate: {match_pct}% | "
        f"{summary.total_false_negatives} false negatives | "
        f"{summary.total_false_positives} false positives"
    )

    return ComparisonRunResponse(
        success=True,
        summary=summary,
        message=message,
    )


@router.get("/report", response_model=ComparisonReportResponse)
async def get_comparison_report():
    """
    Get the latest comparison report.

    Returns the full report from the most recent comparison run.
    Run POST /api/compare first to generate a report.
    """
    from ..api import get_state

    s = get_state()

    if s.comparison_report is None:
        raise HTTPException(
            status_code=404,
            detail="No comparison report available. Run POST /api/compare first."
        )

    report = s.comparison_report

    # Convert to response model
    summary = ComparisonSummary(**report['summary'])

    by_scale = {
        scale: ComparisonScaleResult(**data)
        for scale, data in report['by_scale'].items()
    }

    false_negatives = [
        FalseNegativeItem(**item)
        for item in report['false_negatives']
    ]

    false_positives = [
        FalsePositiveItem(**item)
        for item in report['false_positives']
    ]

    return ComparisonReportResponse(
        summary=summary,
        by_scale=by_scale,
        false_negatives=false_negatives,
        false_positives=false_positives,
    )


@router.get("/export")
async def export_comparison(format: str = Query("json", description="Export format: json or csv")):
    """
    Export comparison report as JSON or CSV.

    Args:
        format: Export format - "json" (default) or "csv"

    Returns:
        Report data in requested format
    """
    from ..api import get_state

    s = get_state()

    if s.comparison_report is None:
        raise HTTPException(
            status_code=404,
            detail="No comparison report available. Run POST /api/compare first."
        )

    report = s.comparison_report

    if format == "json":
        return report

    elif format == "csv":
        # Build CSV content for false negatives and false positives
        lines = []

        # Header
        lines.append("type,scale,start,end,direction,annotation_id,size,rank")

        # False negatives
        for item in report['false_negatives']:
            lines.append(
                f"false_negative,{item['scale']},{item['start']},{item['end']},"
                f"{item['direction']},{item['annotation_id']},,"
            )

        # False positives
        for item in report['false_positives']:
            lines.append(
                f"false_positive,{item['scale']},{item['start']},{item['end']},"
                f"{item['direction']},,{item['size']},{item['rank']}"
            )

        csv_content = "\n".join(lines)

        return PlainTextResponse(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=comparison_report.csv"}
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {format}. Use 'json' or 'csv'."
        )
