"""
Validation Session Management

Manages validation sessions for systematic review of swing detection logic.
Tracks progress, logs expert findings, and supports session persistence.

Features:
- Session state persistence across multiple validation runs
- Progress tracking with resume capabilities
- Expert review note integration
- Structured export of validation findings

Author: Generated for Market Simulator Project
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import uuid

from .issue_catalog import ValidationIssue, IssueCatalog


@dataclass
class ValidationProgress:
    """Progress tracking for validation sessions."""
    current_bar_index: int
    total_bars: int
    bars_reviewed: int
    issues_logged: int
    session_start: datetime
    last_update: datetime
    completion_percentage: float
    
    def __post_init__(self):
        """Calculate derived fields."""
        if self.total_bars > 0:
            self.completion_percentage = (self.current_bar_index / self.total_bars) * 100
        else:
            self.completion_percentage = 0.0


class ValidationSession:
    """
    Manages validation sessions for systematic swing detection review.
    
    Provides:
    - Session state persistence
    - Progress tracking and resume functionality
    - Issue logging integration
    - Structured export capabilities
    """
    
    def __init__(self, 
                 symbol: str,
                 resolution: str,
                 start_date: datetime,
                 end_date: datetime,
                 session_id: Optional[str] = None,
                 session_dir: str = "validation_sessions"):
        """
        Initialize validation session.
        
        Args:
            symbol: Market symbol being validated
            resolution: Data resolution (1m, 5m, 1d)
            start_date: Validation start date
            end_date: Validation end date
            session_id: Optional session identifier
            session_dir: Directory for session persistence
        """
        self.symbol = symbol
        self.resolution = resolution
        self.start_date = start_date
        self.end_date = end_date
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.session_dir = Path(session_dir)
        
        # Session state
        self.is_active = False
        self.current_bar_index = 0
        self.total_bars = 0
        self.session_start = None
        self.last_update = None
        
        # Issue tracking
        self.issue_catalog = IssueCatalog()
        self.expert_notes = []
        
        # Session metadata
        self.metadata = {
            'symbol': symbol,
            'resolution': resolution,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'session_id': self.session_id,
            'created_at': datetime.now().isoformat()
        }
        
        # Ensure session directory exists
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_file = self.session_dir / f"{self.session_id}.json"
    
    def start_session(self, symbol: str, date_range: Tuple[datetime, datetime]) -> None:
        """
        Start a new validation session.
        
        Args:
            symbol: Market symbol
            date_range: (start_date, end_date) tuple
        """
        self.is_active = True
        self.session_start = datetime.now()
        self.last_update = self.session_start
        self.current_bar_index = 0
        
        # Update metadata
        self.metadata.update({
            'session_start': self.session_start.isoformat(),
            'date_range_start': date_range[0].isoformat(),
            'date_range_end': date_range[1].isoformat()
        })
        
        # Save initial state
        self.save_session()
        
        print(f"Started validation session {self.session_id}")
        print(f"Symbol: {symbol}, Range: {date_range[0].date()} to {date_range[1].date()}")
    
    def update_progress(self, current_bar: int, total_bars: int) -> None:
        """
        Update session progress.
        
        Args:
            current_bar: Current bar index
            total_bars: Total number of bars in dataset
        """
        self.current_bar_index = current_bar
        self.total_bars = total_bars
        self.last_update = datetime.now()
        
        # Save progress periodically (every 100 bars)
        if current_bar % 100 == 0:
            self.save_session()
    
    def log_issue(self, 
                  timestamp: datetime, 
                  issue_type: str, 
                  description: str,
                  severity: str = "major",
                  suggested_fix: Optional[str] = None) -> None:
        """
        Log a validation issue.
        
        Args:
            timestamp: Timestamp when issue occurred
            issue_type: Type of issue (accuracy, level, event, etc.)
            description: Detailed description of the issue
            severity: Issue severity (critical, major, minor)
            suggested_fix: Optional suggested fix
        """
        # Create market context
        market_context = {
            'bar_index': self.current_bar_index,
            'timestamp': timestamp.isoformat(),
            'symbol': self.symbol,
            'resolution': self.resolution
        }
        
        # Create and log issue
        issue = ValidationIssue(
            timestamp=timestamp,
            issue_type=issue_type,
            severity=severity,
            description=description,
            market_context=market_context,
            suggested_fix=suggested_fix
        )
        
        self.issue_catalog.add_issue(issue)
        self.last_update = datetime.now()
        
        print(f"Logged {severity} {issue_type} issue at bar {self.current_bar_index}")
    
    def add_expert_note(self, note: str, context: Optional[Dict] = None) -> None:
        """
        Add expert review note.
        
        Args:
            note: Expert note text
            context: Optional context information
        """
        note_entry = {
            'timestamp': datetime.now().isoformat(),
            'bar_index': self.current_bar_index,
            'note': note,
            'context': context or {}
        }
        
        self.expert_notes.append(note_entry)
        self.last_update = datetime.now()
    
    def get_progress(self) -> ValidationProgress:
        """
        Get current validation progress.
        
        Returns:
            ValidationProgress object with current state
        """
        bars_reviewed = self.current_bar_index
        issues_logged = len(self.issue_catalog.issues)
        
        return ValidationProgress(
            current_bar_index=self.current_bar_index,
            total_bars=self.total_bars,
            bars_reviewed=bars_reviewed,
            issues_logged=issues_logged,
            session_start=self.session_start or datetime.now(),
            last_update=self.last_update or datetime.now(),
            completion_percentage=0.0  # Will be calculated in __post_init__
        )
    
    def save_session(self) -> None:
        """Save session state to file."""
        try:
            session_data = {
                'metadata': self.metadata,
                'state': {
                    'is_active': self.is_active,
                    'current_bar_index': self.current_bar_index,
                    'total_bars': self.total_bars,
                    'session_start': self.session_start.isoformat() if self.session_start else None,
                    'last_update': self.last_update.isoformat() if self.last_update else None
                },
                'issues': [asdict(issue) for issue in self.issue_catalog.issues],
                'expert_notes': self.expert_notes
            }
            
            with open(self.session_file, 'w') as f:
                json.dump(session_data, f, indent=2, default=str)
                
        except Exception as e:
            print(f"Warning: Failed to save session {self.session_id}: {e}")
    
    def load_session(self, session_id: str) -> bool:
        """
        Load existing session from file.
        
        Args:
            session_id: Session identifier to load
            
        Returns:
            True if session loaded successfully
        """
        try:
            session_file = self.session_dir / f"{session_id}.json"
            
            if not session_file.exists():
                return False
            
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            # Restore metadata
            self.metadata = session_data['metadata']
            
            # Restore state
            state = session_data['state']
            self.is_active = state['is_active']
            self.current_bar_index = state['current_bar_index']
            self.total_bars = state['total_bars']
            
            if state['session_start']:
                self.session_start = datetime.fromisoformat(state['session_start'])
            if state['last_update']:
                self.last_update = datetime.fromisoformat(state['last_update'])
            
            # Restore issues
            for issue_data in session_data.get('issues', []):
                issue = ValidationIssue(
                    timestamp=datetime.fromisoformat(issue_data['timestamp']),
                    issue_type=issue_data['issue_type'],
                    severity=issue_data['severity'],
                    description=issue_data['description'],
                    market_context=issue_data['market_context'],
                    suggested_fix=issue_data.get('suggested_fix')
                )
                self.issue_catalog.add_issue(issue)
            
            # Restore expert notes
            self.expert_notes = session_data.get('expert_notes', [])
            
            self.session_id = session_id
            self.session_file = session_file
            
            return True
            
        except Exception as e:
            print(f"Error loading session {session_id}: {e}")
            return False
    
    def export_findings(self, output_path: str) -> bool:
        """
        Export validation findings to structured format.
        
        Args:
            output_path: Path for export file
            
        Returns:
            True if export successful
        """
        try:
            progress = self.get_progress()
            
            # Create comprehensive report
            findings = {
                'session_metadata': self.metadata,
                'validation_progress': asdict(progress),
                'summary': {
                    'total_issues': len(self.issue_catalog.issues),
                    'issues_by_type': self.issue_catalog.get_issue_summary(),
                    'issues_by_severity': self._get_issues_by_severity(),
                    'completion_status': 'completed' if progress.completion_percentage >= 100 else 'in_progress'
                },
                'detailed_issues': [asdict(issue) for issue in self.issue_catalog.issues],
                'expert_notes': self.expert_notes,
                'recommendations': self._generate_recommendations()
            }
            
            # Export based on file extension
            output_file = Path(output_path)
            
            if output_file.suffix.lower() == '.json':
                with open(output_file, 'w') as f:
                    json.dump(findings, f, indent=2, default=str)
            else:
                # Default to text format
                self._export_text_report(findings, output_file)
            
            return True
            
        except Exception as e:
            print(f"Export error: {e}")
            return False
    
    def _get_issues_by_severity(self) -> Dict[str, int]:
        """Get issue counts by severity level."""
        severity_counts = {}
        for issue in self.issue_catalog.issues:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
        return severity_counts
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on logged issues."""
        recommendations = []
        
        issue_types = self.issue_catalog.get_issue_summary()
        
        # Generate type-specific recommendations
        if issue_types.get('accuracy', 0) > 0:
            recommendations.append("Review swing detection algorithms for accuracy improvements")
        
        if issue_types.get('level', 0) > 0:
            recommendations.append("Validate Fibonacci level calculations and reference points")
        
        if issue_types.get('event', 0) > 0:
            recommendations.append("Examine completion/invalidation trigger logic")
        
        if issue_types.get('consistency', 0) > 0:
            recommendations.append("Review multi-scale relationship handling")
        
        if issue_types.get('performance', 0) > 0:
            recommendations.append("Optimize processing performance for real-time operation")
        
        # Add general recommendations
        total_issues = len(self.issue_catalog.issues)
        if total_issues > 10:
            recommendations.append("Consider systematic refactoring based on issue patterns")
        
        return recommendations
    
    def _export_text_report(self, findings: Dict, output_file: Path) -> None:
        """Export findings as formatted text report."""
        with open(output_file, 'w') as f:
            f.write("VALIDATION FINDINGS REPORT\\n")
            f.write("=" * 50 + "\\n\\n")
            
            # Session info
            metadata = findings['session_metadata']
            f.write(f"Session: {metadata['session_id']}\\n")
            f.write(f"Symbol: {metadata['symbol']} ({metadata['resolution']})\\n")
            f.write(f"Date Range: {metadata['start_date']} to {metadata['end_date']}\\n\\n")
            
            # Progress summary
            progress = findings['validation_progress']
            f.write(f"Progress: {progress['completion_percentage']:.1f}% complete\\n")
            f.write(f"Bars Reviewed: {progress['bars_reviewed']}/{progress['total_bars']}\\n")
            f.write(f"Issues Found: {progress['issues_logged']}\\n\\n")
            
            # Issue summary
            f.write("ISSUE SUMMARY\\n")
            f.write("-" * 20 + "\\n")
            for issue_type, count in findings['summary']['issues_by_type'].items():
                f.write(f"{issue_type.capitalize()}: {count}\\n")
            f.write("\\n")
            
            # Detailed issues
            if findings['detailed_issues']:
                f.write("DETAILED ISSUES\\n")
                f.write("-" * 20 + "\\n")
                for i, issue in enumerate(findings['detailed_issues'], 1):
                    f.write(f"{i}. {issue['issue_type'].upper()} ({issue['severity']})\\n")
                    f.write(f"   Time: {issue['timestamp']}\\n")
                    f.write(f"   Description: {issue['description']}\\n")
                    if issue.get('suggested_fix'):
                        f.write(f"   Suggested Fix: {issue['suggested_fix']}\\n")
                    f.write("\\n")
            
            # Recommendations
            if findings['recommendations']:
                f.write("RECOMMENDATIONS\\n")
                f.write("-" * 20 + "\\n")
                for i, rec in enumerate(findings['recommendations'], 1):
                    f.write(f"{i}. {rec}\\n")
                f.write("\\n")
    
    @classmethod
    def list_sessions(cls, session_dir: str = "validation_sessions") -> List[Dict]:
        """
        List available validation sessions.
        
        Args:
            session_dir: Directory containing sessions
            
        Returns:
            List of session metadata dictionaries
        """
        sessions = []
        session_path = Path(session_dir)
        
        if not session_path.exists():
            return sessions
        
        for session_file in session_path.glob("*.json"):
            try:
                with open(session_file, 'r') as f:
                    session_data = json.load(f)
                    sessions.append(session_data['metadata'])
            except Exception:
                # Skip invalid session files
                continue
        
        return sessions