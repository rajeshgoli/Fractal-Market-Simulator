"""
Tests for the lightweight swing validator module.
"""

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.lightweight_swing_validator.models import (
    OHLCBar,
    Scale,
    SamplerConfig,
    SessionStats,
    SwingCandidate,
    ValidationSample,
    Vote,
    VoteRequest,
    VoteType,
)
from src.lightweight_swing_validator.sampler import IntervalSampler
from src.lightweight_swing_validator.storage import VoteStorage
from src.lightweight_swing_validator.progressive_loader import (
    ProgressiveLoader,
    DataWindow,
    WindowStatus,
    LARGE_FILE_THRESHOLD,
)
from src.data.ohlc_loader import get_file_metrics, load_ohlc_window, FileMetrics


class TestModels:
    """Tests for Pydantic models."""

    def test_scale_enum(self):
        assert Scale.S.value == "S"
        assert Scale.M.value == "M"
        assert Scale.L.value == "L"
        assert Scale.XL.value == "XL"

    def test_ohlc_bar(self):
        bar = OHLCBar(
            timestamp=1700000000,
            open=100.0,
            high=105.0,
            low=99.0,
            close=103.0
        )
        assert bar.timestamp == 1700000000
        assert bar.high > bar.low

    def test_swing_candidate(self):
        candidate = SwingCandidate(
            swing_id="test-123",
            scale=Scale.M,
            is_bull=True,
            high_price=110.0,
            low_price=100.0,
            high_timestamp=1700001000,
            low_timestamp=1700000000,
            size=10.0,
            duration_bars=20,
            levels={"0.382": 103.82},
            rank=1
        )
        assert candidate.swing_id == "test-123"
        assert candidate.is_bull
        assert candidate.size == 10.0

    def test_vote_type_enum(self):
        assert VoteType.UP.value == "up"
        assert VoteType.DOWN.value == "down"
        assert VoteType.SKIP.value == "skip"

    def test_vote_request(self):
        request = VoteRequest(
            sample_id="sample-123",
            swing_votes=[
                Vote(swing_id="swing-1", vote=VoteType.UP),
                Vote(swing_id="swing-2", vote=VoteType.DOWN, comment="Too small"),
            ],
            found_right_swings=True,
            overall_comment="Good detection"
        )
        assert len(request.swing_votes) == 2
        assert request.found_right_swings is True


class TestSampler:
    """Tests for the interval sampler."""

    @pytest.fixture
    def sampler(self):
        """Create sampler with test data."""
        config = SamplerConfig(data_file="test_data/test.csv")
        return IntervalSampler(config, seed=42)

    def test_sampler_initialization(self, sampler):
        """Test sampler initializes correctly."""
        assert sampler.bars is not None
        assert len(sampler.bars) > 0
        assert sampler.scale_config is not None

    def test_sampler_generates_sample(self, sampler):
        """Test sampler generates a valid sample."""
        sample = sampler.sample()

        assert sample.sample_id is not None
        assert sample.scale in Scale
        assert len(sample.bars) > 0
        assert sample.interval_start > 0
        assert sample.interval_end > sample.interval_start

    def test_sampler_respects_scale_parameter(self, sampler):
        """Test sampler respects requested scale."""
        sample = sampler.sample(scale=Scale.M)
        assert sample.scale == Scale.M

    def test_sampler_deterministic_with_seed(self):
        """Test sampler produces same results with same seed."""
        config = SamplerConfig(data_file="test_data/test.csv")

        sampler1 = IntervalSampler(config, seed=12345)
        sampler2 = IntervalSampler(config, seed=12345)

        sample1 = sampler1.sample()
        sample2 = sampler2.sample()

        assert sample1.scale == sample2.scale
        assert sample1.interval_start == sample2.interval_start

    def test_data_summary(self, sampler):
        """Test data summary contains expected fields."""
        summary = sampler.get_data_summary()

        assert "total_bars" in summary
        assert "start_time" in summary
        assert "end_time" in summary
        assert "scale_boundaries" in summary
        assert summary["total_bars"] > 0


class TestStorage:
    """Tests for vote storage."""

    @pytest.fixture
    def temp_storage(self):
        """Create storage with temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = VoteStorage(storage_dir=tmpdir)
            yield storage

    def test_storage_initialization(self, temp_storage):
        """Test storage initializes correctly."""
        assert temp_storage.session_id is not None
        assert temp_storage.session_file.exists()

    def test_record_vote(self, temp_storage):
        """Test recording a vote."""
        request = VoteRequest(
            sample_id="test-sample",
            swing_votes=[
                Vote(swing_id="swing-1", vote=VoteType.UP),
            ],
            found_right_swings=True,
        )

        result = temp_storage.record_vote(
            request,
            sample_scale=Scale.M,
            interval_start=1700000000,
            interval_end=1700001000
        )

        assert result.sample_id == "test-sample"
        assert len(temp_storage.results) == 1

    def test_stats_update(self, temp_storage):
        """Test statistics update after voting."""
        request = VoteRequest(
            sample_id="test-sample",
            swing_votes=[
                Vote(swing_id="swing-1", vote=VoteType.UP),
                Vote(swing_id="swing-2", vote=VoteType.DOWN),
            ],
        )

        temp_storage.record_vote(
            request,
            sample_scale=Scale.M,
            interval_start=0,
            interval_end=0
        )

        stats = temp_storage.get_stats()
        assert stats.samples_validated == 1
        assert stats.swings_approved == 1
        assert stats.swings_rejected == 1

    def test_export_csv(self, temp_storage):
        """Test CSV export."""
        request = VoteRequest(
            sample_id="test-sample",
            swing_votes=[Vote(swing_id="swing-1", vote=VoteType.UP)],
        )
        temp_storage.record_vote(request, Scale.S, 0, 0)

        csv_path = temp_storage.export_csv(
            str(temp_storage.storage_dir / "export.csv")
        )
        assert Path(csv_path).exists()

    def test_export_json(self, temp_storage):
        """Test JSON export."""
        request = VoteRequest(
            sample_id="test-sample",
            swing_votes=[Vote(swing_id="swing-1", vote=VoteType.UP)],
        )
        temp_storage.record_vote(request, Scale.S, 0, 0)

        json_path = temp_storage.export_json(
            str(temp_storage.storage_dir / "export.json")
        )
        assert Path(json_path).exists()

        with open(json_path) as f:
            data = json.load(f)
        assert "results" in data
        assert len(data["results"]) == 1


class TestAPI:
    """Tests for FastAPI endpoints."""

    @pytest.fixture(autouse=True)
    def setup_api(self):
        """Initialize API before each test."""
        from src.lightweight_swing_validator import api

        # Reset global state
        api.sampler = None
        api.storage = None

        with tempfile.TemporaryDirectory() as tmpdir:
            api.init_app(
                data_file="test_data/test.csv",
                storage_dir=tmpdir,
                seed=42
            )
            yield

    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.lightweight_swing_validator.api import app
        return TestClient(app)

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/api/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"
        assert data["sampler_initialized"] is True

    def test_sample_endpoint(self, client):
        """Test sample generation endpoint."""
        response = client.get("/api/sample")
        assert response.status_code == 200

        data = response.json()
        assert "sample_id" in data
        assert "scale" in data
        assert "bars" in data
        assert "candidates" in data

    def test_sample_with_scale_filter(self, client):
        """Test sample endpoint with scale filter."""
        response = client.get("/api/sample?scale=M")
        assert response.status_code == 200

        data = response.json()
        assert data["scale"] == "M"

    def test_stats_endpoint(self, client):
        """Test stats endpoint."""
        response = client.get("/api/stats")
        assert response.status_code == 200

        data = response.json()
        assert "samples_validated" in data
        assert "swings_approved" in data

    def test_data_summary_endpoint(self, client):
        """Test data summary endpoint."""
        response = client.get("/api/data-summary")
        assert response.status_code == 200

        data = response.json()
        assert "total_bars" in data
        assert "scale_boundaries" in data

    def test_vote_endpoint(self, client):
        """Test vote submission endpoint."""
        # First get a sample
        sample_resp = client.get("/api/sample")
        sample = sample_resp.json()

        # Submit vote
        vote_request = {
            "sample_id": sample["sample_id"],
            "swing_votes": [],
            "found_right_swings": True,
            "overall_comment": "Test vote"
        }

        response = client.post("/api/vote", json=vote_request)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ok"

    def test_windows_endpoint(self, client):
        """Test windows listing endpoint."""
        response = client.get("/api/windows")
        assert response.status_code == 200

        data = response.json()
        assert "windows" in data
        assert "is_progressive" in data

    def test_loading_status_endpoint(self, client):
        """Test loading status endpoint."""
        response = client.get("/api/loading-status")
        assert response.status_code == 200

        data = response.json()
        assert "is_progressive" in data
        assert "is_complete" in data
        assert "percent_complete" in data


class TestFileMetrics:
    """Tests for fast file metrics function."""

    def test_get_file_metrics_small_file(self):
        """Test file metrics on small test file."""
        metrics = get_file_metrics("test_data/test.csv")

        assert metrics.total_bars > 0
        assert metrics.file_size_bytes > 0
        assert metrics.format in ("format_a", "format_b")

    def test_get_file_metrics_speed(self):
        """Test that file metrics is fast (< 100ms for any file)."""
        start = time.time()
        metrics = get_file_metrics("test_data/test.csv")
        elapsed = time.time() - start

        assert elapsed < 0.5  # Should be much faster, 500ms is generous

    def test_get_file_metrics_missing_file(self):
        """Test file metrics raises on missing file."""
        with pytest.raises(FileNotFoundError):
            get_file_metrics("nonexistent_file.csv")


class TestLoadOhlcWindow:
    """Tests for windowed OHLC loading."""

    def test_load_window_basic(self):
        """Test loading a window from test file."""
        df, gaps = load_ohlc_window("test_data/test.csv", start_row=0, num_rows=100)

        assert len(df) <= 100
        assert len(df) > 0
        assert "open" in df.columns
        assert "high" in df.columns
        assert "low" in df.columns
        assert "close" in df.columns

    def test_load_window_offset(self):
        """Test loading with offset."""
        # Load first window
        df1, _ = load_ohlc_window("test_data/test.csv", start_row=0, num_rows=50)

        # Load second window with offset
        df2, _ = load_ohlc_window("test_data/test.csv", start_row=50, num_rows=50)

        # Verify they don't overlap (timestamps should be different)
        if len(df1) > 0 and len(df2) > 0:
            assert df1.index[-1] < df2.index[-1]


class TestProgressiveLoader:
    """Tests for progressive data loading."""

    def test_loader_detects_small_file(self):
        """Test loader correctly identifies small files."""
        loader = ProgressiveLoader("test_data/test.csv")

        # test.csv is small, should not be in progressive mode
        assert loader.is_large_file is False

    def test_loader_loads_initial_window(self):
        """Test loader loads initial window successfully."""
        loader = ProgressiveLoader("test_data/test.csv", seed=42)
        window = loader.load_initial_window()

        assert window is not None
        assert window.status == WindowStatus.READY
        assert len(window.bars) > 0
        assert window.scale_config is not None

    def test_loader_current_window(self):
        """Test loader tracks current window."""
        loader = ProgressiveLoader("test_data/test.csv", seed=42)
        window = loader.load_initial_window()

        current = loader.get_current_window()
        assert current is not None
        assert current.window_id == window.window_id

    def test_loader_progress(self):
        """Test loader reports progress correctly."""
        loader = ProgressiveLoader("test_data/test.csv", seed=42)
        loader.load_initial_window()

        progress = loader.get_loading_progress()

        assert progress.total_bars > 0
        assert progress.loaded_bars > 0
        # For small files, should be complete after initial load
        assert progress.is_complete is True

    def test_loader_list_windows(self):
        """Test loader lists windows."""
        loader = ProgressiveLoader("test_data/test.csv", seed=42)
        loader.load_initial_window()

        windows = loader.list_windows()
        assert len(windows) >= 1

        # Each window should have required fields
        for w in windows:
            assert "window_id" in w
            assert "status" in w
            assert "start_row" in w
            assert "num_rows" in w


class TestSamplerFromBars:
    """Tests for sampler initialization from pre-loaded bars."""

    def test_sampler_from_bars(self):
        """Test creating sampler from pre-loaded bars."""
        # First load bars using loader
        loader = ProgressiveLoader("test_data/test.csv", seed=42)
        window = loader.load_initial_window()

        # Create sampler from bars
        config = SamplerConfig(data_file="test_data/test.csv")
        sampler = IntervalSampler.from_bars(
            bars=window.bars,
            scale_config=window.scale_config,
            config=config,
            seed=42,
            window_id=window.window_id,
            window_start=window.start_timestamp,
            window_end=window.end_timestamp
        )

        assert sampler is not None
        assert len(sampler.bars) == len(window.bars)
        assert sampler.scale_config == window.scale_config

    def test_sampler_from_bars_generates_samples(self):
        """Test sampler from bars can generate samples."""
        loader = ProgressiveLoader("test_data/test.csv", seed=42)
        window = loader.load_initial_window()

        config = SamplerConfig(data_file="test_data/test.csv")
        sampler = IntervalSampler.from_bars(
            bars=window.bars,
            scale_config=window.scale_config,
            config=config,
            seed=42
        )

        sample = sampler.sample()
        assert sample is not None
        assert sample.sample_id is not None
        assert len(sample.bars) > 0

    def test_sampler_data_summary_includes_window(self):
        """Test data summary includes window info when available."""
        loader = ProgressiveLoader("test_data/test.csv", seed=42)
        window = loader.load_initial_window()

        config = SamplerConfig(data_file="test_data/test.csv")
        sampler = IntervalSampler.from_bars(
            bars=window.bars,
            scale_config=window.scale_config,
            config=config,
            window_id="test_window",
            window_start=datetime(2024, 1, 1),
            window_end=datetime(2024, 1, 2)
        )

        summary = sampler.get_data_summary()
        assert "window" in summary
        assert summary["window"]["window_id"] == "test_window"
