"""
Tests for the lightweight swing validator module.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

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
