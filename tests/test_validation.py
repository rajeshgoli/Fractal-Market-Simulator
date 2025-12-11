"""
Validation Component Tests

Comprehensive tests for historical data validation functionality including
data loading, session management, and issue cataloging.

Test Coverage:
- Historical data loading with date range filtering
- Validation session lifecycle and persistence
- Issue cataloging and analysis
- CLI validation command integration

Author: Generated for Market Simulator Project
"""

import os
import pytest
import tempfile
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

# Project imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import (
    load_historical_data, discover_historical_files, 
    get_available_date_ranges, validate_data_availability
)
from src.validation.session import ValidationSession, ValidationProgress
from src.validation.issue_catalog import ValidationIssue, IssueCatalog, IssueType, IssueSeverity
from src.swing_analysis.bull_reference_detector import Bar


@pytest.fixture
def temp_data_dir():
    """Create temporary directory with test data files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test CSV files
        test_data_1m = Path(temp_dir) / "ES_1m_20231001.csv"
        test_data_5m = Path(temp_dir) / "ES_5m_20231001.csv"

        # Sample 1-minute data - use timezone-aware datetime for consistent timestamps
        with open(test_data_1m, 'w') as f:
            f.write("time,open,high,low,close,volume\n")
            base_time = int(datetime(2023, 10, 1, 9, 30, tzinfo=timezone.utc).timestamp())
            for i in range(100):  # 100 minutes of data
                timestamp = base_time + (i * 60)
                price = 5800 + (i * 0.25)  # Simple price progression
                f.write(f"{timestamp},{price},{price+1},{price-1},{price+0.5},1000\n")

        # Sample 5-minute data
        with open(test_data_5m, 'w') as f:
            f.write("time,open,high,low,close,volume\n")
            base_time = int(datetime(2023, 10, 1, 9, 30, tzinfo=timezone.utc).timestamp())
            for i in range(20):  # 20 five-minute bars
                timestamp = base_time + (i * 300)  # 5 minutes = 300 seconds
                price = 5800 + (i * 1.25)
                f.write(f"{timestamp},{price},{price+2},{price-2},{price+1},1000\n")

        yield temp_dir


@pytest.fixture
def sample_validation_session():
    """Create sample validation session for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = ValidationSession(
            symbol="ES",
            resolution="1m",
            start_date=datetime(2023, 10, 1, 9, 30),
            end_date=datetime(2023, 10, 1, 11, 30),
            session_dir=temp_dir
        )
        yield session


@pytest.fixture
def sample_issues():
    """Create sample validation issues for testing."""
    return [
        ValidationIssue(
            timestamp=datetime(2023, 10, 1, 10, 0),
            issue_type="accuracy",
            severity="major",
            description="Swing detection missed clear reversal pattern",
            market_context={"bar_index": 30, "price": 5815.0}
        ),
        ValidationIssue(
            timestamp=datetime(2023, 10, 1, 10, 15),
            issue_type="level",
            severity="minor",
            description="Fibonacci retracement level calculation off by 0.25 points",
            market_context={"bar_index": 45, "price": 5823.5},
            suggested_fix="Review fib calculation precision"
        ),
        ValidationIssue(
            timestamp=datetime(2023, 10, 1, 10, 30),
            issue_type="performance",
            severity="critical",
            description="Processing lag exceeded 500ms threshold",
            market_context={"bar_index": 60, "processing_time_ms": 750}
        )
    ]


class TestHistoricalDataLoader:
    """Test historical data loading functionality."""
    
    def test_discover_historical_files(self, temp_data_dir):
        """Test file discovery with various naming patterns."""
        files = discover_historical_files("ES", "1m", temp_data_dir)
        assert len(files) == 1
        assert "ES_1m_20231001.csv" in files[0]
        
        files = discover_historical_files("ES", "5m", temp_data_dir)
        assert len(files) == 1
        assert "ES_5m_20231001.csv" in files[0]
        
        # Test non-existent symbol
        files = discover_historical_files("NQ", "1m", temp_data_dir)
        assert len(files) == 0
    
    def test_load_historical_data_success(self, temp_data_dir):
        """Test successful historical data loading."""
        start_date = datetime(2023, 10, 1, 9, 30, tzinfo=timezone.utc)
        end_date = datetime(2023, 10, 1, 10, 30, tzinfo=timezone.utc)

        bars = load_historical_data("ES", "1m", start_date, end_date, temp_data_dir)

        assert len(bars) > 0
        assert isinstance(bars[0], Bar)
        assert bars[0].timestamp >= start_date.timestamp()
        assert bars[-1].timestamp <= end_date.timestamp()
        
        # Verify bars are sorted by timestamp
        timestamps = [bar.timestamp for bar in bars]
        assert timestamps == sorted(timestamps)
    
    def test_load_historical_data_date_filtering(self, temp_data_dir):
        """Test date range filtering."""
        # Load narrow range
        start_date = datetime(2023, 10, 1, 10, 0, tzinfo=timezone.utc)
        end_date = datetime(2023, 10, 1, 10, 10, tzinfo=timezone.utc)

        bars = load_historical_data("ES", "1m", start_date, end_date, temp_data_dir)

        # Should have approximately 10 minutes of data
        assert 8 <= len(bars) <= 12  # Allow some tolerance
    
    def test_load_historical_data_invalid_inputs(self, temp_data_dir):
        """Test error handling for invalid inputs."""
        start_date = datetime(2023, 10, 1, 10, 0, tzinfo=timezone.utc)
        end_date = datetime(2023, 10, 1, 9, 0, tzinfo=timezone.utc)  # End before start

        with pytest.raises(ValueError, match="Start date must be before end date"):
            load_historical_data("ES", "1m", start_date, end_date, temp_data_dir)

        # Invalid resolution - use valid date range
        valid_start = datetime(2023, 10, 1, 9, 30, tzinfo=timezone.utc)
        valid_end = datetime(2023, 10, 1, 10, 30, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="Invalid resolution"):
            load_historical_data("ES", "30s", valid_start, valid_end, temp_data_dir)

        # Non-existent symbol
        with pytest.raises(FileNotFoundError):
            load_historical_data("INVALID", "1m", valid_start, valid_end, temp_data_dir)
    
    def test_get_available_date_ranges(self, temp_data_dir):
        """Test date range discovery."""
        ranges = get_available_date_ranges("ES", "1m", temp_data_dir)
        
        assert len(ranges) == 1
        start, end = ranges[0]
        assert isinstance(start, datetime)
        assert isinstance(end, datetime)
        assert start < end
    
    def test_validate_data_availability(self, temp_data_dir):
        """Test data availability validation."""
        start_date = datetime(2023, 10, 1, 9, 30, tzinfo=timezone.utc)
        end_date = datetime(2023, 10, 1, 10, 30, tzinfo=timezone.utc)

        # Valid request
        is_available, message = validate_data_availability("ES", "1m", start_date, end_date, temp_data_dir)
        assert is_available
        assert "available" in message.lower()

        # Invalid symbol
        is_available, message = validate_data_availability("INVALID", "1m", start_date, end_date, temp_data_dir)
        assert not is_available
        assert "no data files found" in message.lower()


class TestValidationSession:
    """Test validation session management."""
    
    def test_session_initialization(self, sample_validation_session):
        """Test session initialization."""
        session = sample_validation_session
        
        assert session.symbol == "ES"
        assert session.resolution == "1m"
        assert not session.is_active
        assert session.current_bar_index == 0
        assert len(session.session_id) == 8
    
    def test_session_lifecycle(self, sample_validation_session):
        """Test session start/stop lifecycle."""
        session = sample_validation_session
        
        # Start session
        start_date = datetime(2023, 10, 1, 9, 30)
        end_date = datetime(2023, 10, 1, 11, 30)
        session.start_session("ES", (start_date, end_date))
        
        assert session.is_active
        assert session.session_start is not None
        assert session.last_update is not None
    
    def test_progress_tracking(self, sample_validation_session):
        """Test progress tracking functionality."""
        session = sample_validation_session
        session.start_session("ES", (datetime.now(), datetime.now() + timedelta(hours=2)))
        
        # Update progress
        session.update_progress(50, 100)
        
        progress = session.get_progress()
        assert progress.current_bar_index == 50
        assert progress.total_bars == 100
        assert progress.completion_percentage == 50.0
    
    def test_issue_logging(self, sample_validation_session):
        """Test issue logging functionality."""
        session = sample_validation_session
        session.start_session("ES", (datetime.now(), datetime.now() + timedelta(hours=2)))
        
        # Log issue
        timestamp = datetime(2023, 10, 1, 10, 0)
        session.log_issue(timestamp, "accuracy", "Test issue description")
        
        assert len(session.issue_catalog.issues) == 1
        issue = session.issue_catalog.issues[0]
        assert issue.issue_type == "accuracy"
        assert issue.description == "Test issue description"
    
    def test_expert_notes(self, sample_validation_session):
        """Test expert note functionality."""
        session = sample_validation_session
        session.start_session("ES", (datetime.now(), datetime.now() + timedelta(hours=2)))
        
        # Add expert note
        session.add_expert_note("This is a test note", {"context": "testing"})
        
        assert len(session.expert_notes) == 1
        note = session.expert_notes[0]
        assert note["note"] == "This is a test note"
        assert note["context"]["context"] == "testing"
    
    def test_session_persistence(self, sample_validation_session):
        """Test session save/load functionality."""
        session = sample_validation_session
        session.start_session("ES", (datetime.now(), datetime.now() + timedelta(hours=2)))
        
        # Add some data
        session.log_issue(datetime.now(), "accuracy", "Test issue")
        session.add_expert_note("Test note")
        session.update_progress(25, 100)
        
        # Save session
        session.save_session()
        
        # Create new session and load
        new_session = ValidationSession(
            symbol="TEST",
            resolution="1m", 
            start_date=datetime.now(),
            end_date=datetime.now(),
            session_dir=session.session_dir
        )
        
        success = new_session.load_session(session.session_id)
        assert success
        assert len(new_session.issue_catalog.issues) == 1
        assert len(new_session.expert_notes) == 1
        assert new_session.current_bar_index == 25
    
    def test_export_findings(self, sample_validation_session):
        """Test findings export functionality."""
        session = sample_validation_session
        session.start_session("ES", (datetime.now(), datetime.now() + timedelta(hours=2)))
        
        # Add test data
        session.log_issue(datetime.now(), "accuracy", "Test issue 1")
        session.log_issue(datetime.now(), "level", "Test issue 2", "critical")
        session.update_progress(100, 100)
        
        # Export to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            success = session.export_findings(temp_file.name)
            assert success
            
            # Verify export content
            with open(temp_file.name, 'r') as f:
                data = json.load(f)
                
            assert data['summary']['total_issues'] == 2
            assert len(data['detailed_issues']) == 2
            assert data['validation_progress']['completion_percentage'] == 100.0
            
            os.unlink(temp_file.name)


class TestIssueCatalog:
    """Test issue cataloging functionality."""
    
    def test_catalog_initialization(self):
        """Test catalog initialization."""
        catalog = IssueCatalog()
        
        assert len(catalog) == 0
        assert not catalog
        assert len(catalog.issues) == 0
    
    def test_add_and_retrieve_issues(self, sample_issues):
        """Test adding and retrieving issues."""
        catalog = IssueCatalog()
        
        for issue in sample_issues:
            catalog.add_issue(issue)
        
        assert len(catalog) == 3
        assert bool(catalog)
        
        # Test retrieval by ID
        first_issue = catalog.issues[0]
        retrieved = catalog.get_issue(first_issue.issue_id)
        assert retrieved is not None
        assert retrieved.issue_id == first_issue.issue_id
    
    def test_filtering_by_type(self, sample_issues):
        """Test issue filtering by type."""
        catalog = IssueCatalog()
        for issue in sample_issues:
            catalog.add_issue(issue)
        
        accuracy_issues = catalog.get_issues_by_type("accuracy")
        assert len(accuracy_issues) == 1
        assert accuracy_issues[0].issue_type == "accuracy"
        
        performance_issues = catalog.get_issues_by_type("performance")
        assert len(performance_issues) == 1
        assert performance_issues[0].severity == "critical"
    
    def test_filtering_by_severity(self, sample_issues):
        """Test issue filtering by severity."""
        catalog = IssueCatalog()
        for issue in sample_issues:
            catalog.add_issue(issue)
        
        critical_issues = catalog.get_issues_by_severity("critical")
        assert len(critical_issues) == 1
        assert critical_issues[0].issue_type == "performance"
        
        major_issues = catalog.get_issues_by_severity("major")
        assert len(major_issues) == 1
        assert major_issues[0].issue_type == "accuracy"
    
    def test_timeframe_filtering(self, sample_issues):
        """Test filtering by timeframe."""
        catalog = IssueCatalog()
        for issue in sample_issues:
            catalog.add_issue(issue)
        
        start_time = datetime(2023, 10, 1, 10, 10)
        end_time = datetime(2023, 10, 1, 10, 20)
        
        filtered = catalog.get_issues_in_timeframe(start_time, end_time)
        assert len(filtered) == 1
        assert filtered[0].issue_type == "level"
    
    def test_statistics_generation(self, sample_issues):
        """Test statistics generation."""
        catalog = IssueCatalog()
        for issue in sample_issues:
            catalog.add_issue(issue)
        
        stats = catalog.get_statistics()
        
        assert stats['total_issues'] == 3
        assert stats['by_type']['accuracy'] == 1
        assert stats['by_type']['level'] == 1
        assert stats['by_type']['performance'] == 1
        assert stats['by_severity']['major'] == 1
        assert stats['by_severity']['minor'] == 1
        assert stats['by_severity']['critical'] == 1
        assert stats['most_common_type'] in ['accuracy', 'level', 'performance']  # All equal
        assert stats['issues_with_fixes'] == 1
    
    def test_similar_issue_detection(self, sample_issues):
        """Test similar issue detection."""
        catalog = IssueCatalog()
        for issue in sample_issues:
            catalog.add_issue(issue)
        
        # Add similar issue
        similar_issue = ValidationIssue(
            timestamp=datetime(2023, 10, 1, 11, 0),
            issue_type="accuracy",
            severity="major", 
            description="Swing detection missed another reversal pattern",
            market_context={"bar_index": 90, "price": 5840.0}
        )
        catalog.add_issue(similar_issue)
        
        # Find similar issues
        reference_issue = catalog.get_issues_by_type("accuracy")[0]
        similar = catalog.find_similar_issues(reference_issue, similarity_threshold=0.5)
        
        assert len(similar) >= 1
        # Should find the similar accuracy issue
        assert any(issue.description.find("reversal") >= 0 for issue in similar)
    
    def test_export_functionality(self, sample_issues):
        """Test export functionality."""
        catalog = IssueCatalog()
        for issue in sample_issues:
            catalog.add_issue(issue)
        
        # Test JSON export
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            success = catalog.export_issues(temp_file.name, format="json")
            assert success
            
            # Verify content
            with open(temp_file.name, 'r') as f:
                data = json.load(f)
            assert len(data['issues']) == 3
            
            os.unlink(temp_file.name)
        
        # Test CSV export
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            success = catalog.export_issues(temp_file.name, format="csv")
            assert success
            
            # Verify file exists and has content
            assert Path(temp_file.name).stat().st_size > 0
            
            os.unlink(temp_file.name)


class TestValidationIssue:
    """Test individual validation issue functionality."""
    
    def test_issue_creation(self):
        """Test issue creation and auto-generation."""
        timestamp = datetime(2023, 10, 1, 10, 0)
        issue = ValidationIssue(
            timestamp=timestamp,
            issue_type="accuracy",
            severity="major",
            description="Test issue",
            market_context={"bar": 100}
        )
        
        assert issue.timestamp == timestamp
        assert issue.issue_type == "accuracy"
        assert issue.severity == "major"
        assert len(issue.issue_id) > 0
        assert issue.created_at is not None
    
    def test_summary_generation(self):
        """Test issue summary generation."""
        issue = ValidationIssue(
            timestamp=datetime(2023, 10, 1, 10, 0),
            issue_type="level",
            severity="critical",
            description="This is a long description that should be truncated in the summary",
            market_context={}
        )
        
        summary = issue.to_summary()
        assert "CRITICAL" in summary
        assert "level" in summary
        assert len(summary) < len(issue.description) + 50  # Should be truncated
    
    def test_context_summary(self):
        """Test market context summary."""
        issue = ValidationIssue(
            timestamp=datetime(2023, 10, 1, 10, 0),
            issue_type="accuracy",
            severity="major",
            description="Test",
            market_context={
                "bar_index": 50,
                "symbol": "ES",
                "resolution": "1m",
                "extra_data": "ignored"
            }
        )
        
        context_summary = issue.get_context_summary()
        assert "Bar 50" in context_summary
        assert "Symbol ES" in context_summary
        assert "Resolution 1m" in context_summary


# Integration tests
class TestCLIIntegration:
    """Test CLI integration for validation commands."""
    
    @patch('src.visualization_harness.main.load_historical_data')
    @patch('src.visualization_harness.main.validate_data_availability')
    def test_validation_command_success(self, mock_validate, mock_load):
        """Test successful validation command execution."""
        # Mock successful data validation
        mock_validate.return_value = (True, "Data available")

        # Mock data loading
        mock_bars = [
            Bar(timestamp=1696152600, open=5800.0, high=5801.0, low=5799.0, close=5800.5, index=i)
            for i in range(10)
        ]
        mock_load.return_value = mock_bars
        
        # This would normally test the actual CLI, but we'll test the components
        from src.visualization_harness.main import ValidationHarness
        from src.validation.session import ValidationSession
        
        session = ValidationSession(
            symbol="ES", 
            resolution="1m",
            start_date=datetime(2023, 10, 1),
            end_date=datetime(2023, 10, 2)
        )
        
        # Test harness creation
        harness = ValidationHarness(mock_bars, session, auto_pause=True)
        assert harness.bars == mock_bars
        assert harness.session == session
        assert harness.auto_pause


@pytest.fixture(autouse=True)
def cleanup_temp_files():
    """Clean up any temporary files created during tests."""
    yield
    # Cleanup code would go here if needed
    

if __name__ == "__main__":
    pytest.main([__file__, "-v"])