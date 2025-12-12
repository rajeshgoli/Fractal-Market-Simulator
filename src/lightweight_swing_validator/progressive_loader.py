"""
Progressive data loader for large datasets.

Enables <2 second time-to-first-UI for datasets >100k bars by:
1. Loading a random initial window quickly
2. Loading additional windows in the background
3. Providing diverse market regime coverage across windows
"""

import logging
import random
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional

import pandas as pd

from ..data.ohlc_loader import get_file_metrics, load_ohlc_window, load_ohlc, FileMetrics
from ..swing_analysis.bull_reference_detector import Bar
from ..swing_analysis.scale_calibrator import ScaleCalibrator, ScaleConfig

logger = logging.getLogger(__name__)


# Threshold for progressive loading
LARGE_FILE_THRESHOLD = 100_000  # bars
DEFAULT_WINDOW_SIZE = 20_000  # bars per window


class WindowStatus(str, Enum):
    """Status of a data window."""
    PENDING = "pending"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


@dataclass
class DataWindow:
    """A window of loaded data from the dataset."""
    window_id: str
    start_row: int
    num_rows: int
    status: WindowStatus = WindowStatus.PENDING
    bars: List[Bar] = field(default_factory=list)
    scale_config: Optional[ScaleConfig] = None
    start_timestamp: Optional[datetime] = None
    end_timestamp: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "window_id": self.window_id,
            "start_row": self.start_row,
            "num_rows": self.num_rows,
            "actual_bars": len(self.bars),
            "status": self.status.value,
            "start_timestamp": self.start_timestamp.isoformat() if self.start_timestamp else None,
            "end_timestamp": self.end_timestamp.isoformat() if self.end_timestamp else None,
            "error": self.error
        }


@dataclass
class LoadingProgress:
    """Current loading progress state."""
    total_bars: int
    loaded_bars: int
    windows_total: int
    windows_ready: int
    is_complete: bool
    current_window_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "total_bars": self.total_bars,
            "loaded_bars": self.loaded_bars,
            "windows_total": self.windows_total,
            "windows_ready": self.windows_ready,
            "is_complete": self.is_complete,
            "current_window_id": self.current_window_id,
            "percent_complete": (self.loaded_bars / self.total_bars * 100) if self.total_bars > 0 else 100
        }


class ProgressiveLoader:
    """
    Manages progressive loading of large datasets.

    For datasets >100k bars, loads data in windows to enable fast startup
    while providing diverse market regime coverage.
    """

    def __init__(
        self,
        filepath: str,
        instrument: str = "ES",
        window_size: int = DEFAULT_WINDOW_SIZE,
        seed: Optional[int] = None,
        on_window_ready: Optional[Callable[[DataWindow], None]] = None
    ):
        """
        Initialize the progressive loader.

        Args:
            filepath: Path to CSV data file.
            instrument: Instrument symbol for calibration.
            window_size: Number of bars per window.
            seed: Random seed for window selection.
            on_window_ready: Callback when a window finishes loading.
        """
        self.filepath = filepath
        self.instrument = instrument
        self.window_size = window_size
        self.rng = random.Random(seed)
        self.on_window_ready = on_window_ready

        # Get file metrics first (fast operation)
        self.metrics: FileMetrics = get_file_metrics(filepath)
        self.is_large_file = self.metrics.total_bars > LARGE_FILE_THRESHOLD

        # Window management
        self.windows: Dict[str, DataWindow] = {}
        self.window_order: List[str] = []  # Order of window IDs
        self.current_window_id: Optional[str] = None
        self._lock = threading.Lock()
        self._background_thread: Optional[threading.Thread] = None
        self._stop_background = False

        # Calibrator
        self._calibrator = ScaleCalibrator()

        logger.info(
            f"ProgressiveLoader: {self.metrics.total_bars} bars, "
            f"large_file={self.is_large_file}, window_size={window_size}"
        )

    def load_initial_window(self) -> DataWindow:
        """
        Load the initial window to get UI ready quickly.

        For large files, loads a random window. For small files, loads everything.

        Returns:
            The loaded DataWindow.
        """
        if not self.is_large_file:
            # Small file - load everything in one window
            window = self._create_window("full", 0, self.metrics.total_bars)
            self._load_window(window, use_full_loader=True)
            self.current_window_id = window.window_id
            return window

        # Large file - load random initial window
        window_positions = self._calculate_window_positions()

        # Pick a random window as the initial one
        initial_idx = self.rng.randint(0, len(window_positions) - 1)
        start_row, num_rows = window_positions[initial_idx]

        window = self._create_window(f"window_{initial_idx}", start_row, num_rows)
        self._load_window(window)
        self.current_window_id = window.window_id

        # Queue remaining windows for background loading
        for idx, (start, num) in enumerate(window_positions):
            if idx != initial_idx:
                pending_window = self._create_window(f"window_{idx}", start, num)
                # Don't load yet - will be loaded in background

        return window

    def start_background_loading(self):
        """Start loading remaining windows in the background."""
        if not self.is_large_file:
            return  # Nothing to load for small files

        if self._background_thread is not None:
            return  # Already running

        self._stop_background = False
        self._background_thread = threading.Thread(
            target=self._background_load_worker,
            daemon=True
        )
        self._background_thread.start()
        logger.info("Started background window loading")

    def stop_background_loading(self):
        """Stop background loading."""
        self._stop_background = True
        if self._background_thread:
            self._background_thread.join(timeout=2.0)
            self._background_thread = None

    def get_window(self, window_id: str) -> Optional[DataWindow]:
        """Get a specific window by ID."""
        with self._lock:
            return self.windows.get(window_id)

    def get_current_window(self) -> Optional[DataWindow]:
        """Get the current active window."""
        if self.current_window_id:
            return self.get_window(self.current_window_id)
        return None

    def set_current_window(self, window_id: str) -> bool:
        """
        Set the current active window.

        Args:
            window_id: ID of the window to activate.

        Returns:
            True if window exists and is ready, False otherwise.
        """
        with self._lock:
            window = self.windows.get(window_id)
            if window and window.status == WindowStatus.READY:
                self.current_window_id = window_id
                return True
            return False

    def get_next_window(self) -> Optional[DataWindow]:
        """Get and activate the next ready window in sequence."""
        with self._lock:
            if not self.window_order:
                return None

            # Find current position
            try:
                current_idx = self.window_order.index(self.current_window_id)
            except ValueError:
                current_idx = -1

            # Look for next ready window
            for i in range(1, len(self.window_order)):
                next_idx = (current_idx + i) % len(self.window_order)
                next_id = self.window_order[next_idx]
                window = self.windows[next_id]
                if window.status == WindowStatus.READY:
                    self.current_window_id = next_id
                    return window

            return None

    def get_loading_progress(self) -> LoadingProgress:
        """Get current loading progress."""
        with self._lock:
            loaded_bars = sum(
                len(w.bars) for w in self.windows.values()
                if w.status == WindowStatus.READY
            )
            windows_ready = sum(
                1 for w in self.windows.values()
                if w.status == WindowStatus.READY
            )
            is_complete = all(
                w.status in (WindowStatus.READY, WindowStatus.FAILED)
                for w in self.windows.values()
            )

            return LoadingProgress(
                total_bars=self.metrics.total_bars,
                loaded_bars=loaded_bars,
                windows_total=len(self.windows),
                windows_ready=windows_ready,
                is_complete=is_complete or not self.is_large_file,
                current_window_id=self.current_window_id
            )

    def list_windows(self) -> List[dict]:
        """List all windows with their status."""
        with self._lock:
            return [
                self.windows[wid].to_dict()
                for wid in self.window_order
            ]

    def _calculate_window_positions(self) -> List[tuple]:
        """
        Calculate window start positions for complete dataset coverage.

        Creates contiguous non-overlapping windows that cover all bars
        in the dataset. This ensures all data is loaded for full validation.
        """
        total_bars = self.metrics.total_bars
        window_size = self.window_size

        if total_bars <= window_size:
            return [(0, total_bars)]

        positions = []
        start = 0

        while start < total_bars:
            # Calculate how many bars remain
            remaining = total_bars - start
            num_rows = min(window_size, remaining)
            positions.append((start, num_rows))
            start += num_rows

        return positions

    def _create_window(self, window_id: str, start_row: int, num_rows: int) -> DataWindow:
        """Create and register a new window."""
        window = DataWindow(
            window_id=window_id,
            start_row=start_row,
            num_rows=num_rows
        )
        with self._lock:
            self.windows[window_id] = window
            if window_id not in self.window_order:
                self.window_order.append(window_id)
        return window

    def _load_window(self, window: DataWindow, use_full_loader: bool = False):
        """Load data for a window."""
        window.status = WindowStatus.LOADING

        try:
            if use_full_loader:
                # Use full loader for small files (better handling)
                df, gaps = load_ohlc(self.filepath)
            else:
                # Use windowed loader for large files
                df, gaps = load_ohlc_window(
                    self.filepath,
                    window.start_row,
                    window.num_rows
                )

            # Convert to Bar objects
            bars = self._df_to_bars(df)

            # Calibrate on this window
            scale_config = self._calibrator.calibrate(bars, self.instrument)

            # Update window
            with self._lock:
                window.bars = bars
                window.scale_config = scale_config
                window.status = WindowStatus.READY
                if bars:
                    window.start_timestamp = datetime.utcfromtimestamp(bars[0].timestamp)
                    window.end_timestamp = datetime.utcfromtimestamp(bars[-1].timestamp)

            logger.info(
                f"Window {window.window_id} loaded: {len(bars)} bars, "
                f"{window.start_timestamp} to {window.end_timestamp}"
            )

            # Notify callback
            if self.on_window_ready:
                self.on_window_ready(window)

        except Exception as e:
            with self._lock:
                window.status = WindowStatus.FAILED
                window.error = str(e)
            logger.error(f"Failed to load window {window.window_id}: {e}")

    def _df_to_bars(self, df: pd.DataFrame) -> List[Bar]:
        """Convert DataFrame to list of Bar objects."""
        bars = []
        for idx, (timestamp, row) in enumerate(df.iterrows()):
            bar = Bar(
                index=idx,
                timestamp=int(timestamp.timestamp()),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close'])
            )
            bars.append(bar)
        return bars

    def _background_load_worker(self):
        """Worker thread for background window loading."""
        logger.info("Background loader started")

        while not self._stop_background:
            # Find next pending window
            window_to_load = None
            with self._lock:
                for wid in self.window_order:
                    window = self.windows[wid]
                    if window.status == WindowStatus.PENDING:
                        window_to_load = window
                        break

            if window_to_load is None:
                # All windows loaded
                logger.info("Background loading complete")
                break

            # Load the window
            self._load_window(window_to_load)

        logger.info("Background loader stopped")
