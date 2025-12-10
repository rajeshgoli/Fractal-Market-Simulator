"""
Issue Cataloging System

Systematic classification and documentation of validation issues discovered
during swing detection analysis.

Features:
- Structured issue classification by type and severity
- Market context preservation for debugging
- Issue aggregation and reporting capabilities
- Integration with validation sessions

Author: Generated for Market Simulator Project
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum


class IssueType(Enum):
    """Classification of validation issue types."""
    DETECTION_ACCURACY = "accuracy"      # Swing identification errors
    LEVEL_CALCULATION = "level"         # Fibonacci level computation problems
    EVENT_LOGIC = "event"               # Completion/invalidation trigger issues
    CROSS_SCALE_CONSISTENCY = "consistency"  # Multi-scale relationship problems
    PERFORMANCE = "performance"         # Response time or memory issues


class IssueSeverity(Enum):
    """Issue severity levels."""
    CRITICAL = "critical"   # System-breaking or completely incorrect behavior
    MAJOR = "major"        # Significant functional problems
    MINOR = "minor"        # Minor inconsistencies or edge cases


@dataclass
class ValidationIssue:
    """
    Represents a single validation issue discovered during analysis.
    
    Contains all necessary information for debugging and resolution,
    including market context and expert assessment.
    """
    timestamp: datetime
    issue_type: str
    severity: str
    description: str
    market_context: Dict[str, Any]
    suggested_fix: Optional[str] = None
    
    # Auto-generated fields
    issue_id: str = field(default="", init=False)
    created_at: datetime = field(default_factory=datetime.now, init=False)
    
    def __post_init__(self):
        """Generate unique issue ID."""
        if not self.issue_id:
            # Create ID from timestamp and type
            ts_str = self.timestamp.strftime("%Y%m%d_%H%M%S")
            self.issue_id = f"{self.issue_type}_{ts_str}_{id(self) % 10000:04d}"
    
    def to_summary(self) -> str:
        """Create a brief summary string for the issue."""
        return f"[{self.severity.upper()}] {self.issue_type} at {self.timestamp}: {self.description[:50]}..."
    
    def get_context_summary(self) -> str:
        """Get formatted market context summary."""
        context_items = []
        for key, value in self.market_context.items():
            if key == 'bar_index':
                context_items.append(f"Bar {value}")
            elif key == 'symbol':
                context_items.append(f"Symbol {value}")
            elif key == 'resolution':
                context_items.append(f"Resolution {value}")
        return " | ".join(context_items)


class IssueCatalog:
    """
    Manages collection and analysis of validation issues.
    
    Provides:
    - Issue storage and retrieval
    - Classification and filtering
    - Statistical analysis
    - Export capabilities
    """
    
    def __init__(self):
        """Initialize empty issue catalog."""
        self.issues: List[ValidationIssue] = []
        self._issue_index: Dict[str, ValidationIssue] = {}
    
    def add_issue(self, issue: ValidationIssue) -> None:
        """
        Add issue to catalog.
        
        Args:
            issue: ValidationIssue to add
        """
        self.issues.append(issue)
        self._issue_index[issue.issue_id] = issue
    
    def get_issue(self, issue_id: str) -> Optional[ValidationIssue]:
        """
        Retrieve issue by ID.
        
        Args:
            issue_id: Unique issue identifier
            
        Returns:
            ValidationIssue if found, None otherwise
        """
        return self._issue_index.get(issue_id)
    
    def get_issues_by_type(self, issue_type: str) -> List[ValidationIssue]:
        """
        Get all issues of specified type.
        
        Args:
            issue_type: Issue type to filter by
            
        Returns:
            List of matching ValidationIssue objects
        """
        return [issue for issue in self.issues if issue.issue_type == issue_type]
    
    def get_issues_by_severity(self, severity: str) -> List[ValidationIssue]:
        """
        Get all issues of specified severity.
        
        Args:
            severity: Severity level to filter by
            
        Returns:
            List of matching ValidationIssue objects
        """
        return [issue for issue in self.issues if issue.severity == severity]
    
    def get_issues_in_timeframe(self, 
                               start_time: datetime, 
                               end_time: datetime) -> List[ValidationIssue]:
        """
        Get issues within specified timeframe.
        
        Args:
            start_time: Start of timeframe
            end_time: End of timeframe
            
        Returns:
            List of ValidationIssue objects in timeframe
        """
        return [
            issue for issue in self.issues 
            if start_time <= issue.timestamp <= end_time
        ]
    
    def get_issue_summary(self) -> Dict[str, int]:
        """
        Get summary of issue counts by type.
        
        Returns:
            Dictionary mapping issue types to counts
        """
        summary = {}
        for issue in self.issues:
            summary[issue.issue_type] = summary.get(issue.issue_type, 0) + 1
        return summary
    
    def get_severity_summary(self) -> Dict[str, int]:
        """
        Get summary of issue counts by severity.
        
        Returns:
            Dictionary mapping severity levels to counts
        """
        summary = {}
        for issue in self.issues:
            summary[issue.severity] = summary.get(issue.severity, 0) + 1
        return summary
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive statistics about cataloged issues.
        
        Returns:
            Dictionary with detailed statistics
        """
        if not self.issues:
            return {
                'total_issues': 0,
                'by_type': {},
                'by_severity': {},
                'time_span': None,
                'most_common_type': None,
                'most_common_severity': None
            }
        
        # Basic counts
        by_type = self.get_issue_summary()
        by_severity = self.get_severity_summary()
        
        # Time span
        timestamps = [issue.timestamp for issue in self.issues]
        time_span = {
            'earliest': min(timestamps),
            'latest': max(timestamps),
            'duration_hours': (max(timestamps) - min(timestamps)).total_seconds() / 3600
        }
        
        # Most common
        most_common_type = max(by_type.items(), key=lambda x: x[1])[0] if by_type else None
        most_common_severity = max(by_severity.items(), key=lambda x: x[1])[0] if by_severity else None
        
        return {
            'total_issues': len(self.issues),
            'by_type': by_type,
            'by_severity': by_severity,
            'time_span': time_span,
            'most_common_type': most_common_type,
            'most_common_severity': most_common_severity,
            'issues_with_fixes': sum(1 for issue in self.issues if issue.suggested_fix),
            'unique_contexts': len(set(issue.get_context_summary() for issue in self.issues))
        }
    
    def filter_issues(self, 
                     types: Optional[List[str]] = None,
                     severities: Optional[List[str]] = None,
                     start_time: Optional[datetime] = None,
                     end_time: Optional[datetime] = None) -> List[ValidationIssue]:
        """
        Filter issues by multiple criteria.
        
        Args:
            types: List of issue types to include
            severities: List of severities to include  
            start_time: Earliest timestamp to include
            end_time: Latest timestamp to include
            
        Returns:
            List of ValidationIssue objects matching criteria
        """
        filtered = self.issues
        
        if types:
            filtered = [issue for issue in filtered if issue.issue_type in types]
        
        if severities:
            filtered = [issue for issue in filtered if issue.severity in severities]
        
        if start_time:
            filtered = [issue for issue in filtered if issue.timestamp >= start_time]
        
        if end_time:
            filtered = [issue for issue in filtered if issue.timestamp <= end_time]
        
        return filtered
    
    def get_recent_issues(self, count: int = 10) -> List[ValidationIssue]:
        """
        Get most recently created issues.
        
        Args:
            count: Number of recent issues to return
            
        Returns:
            List of most recent ValidationIssue objects
        """
        sorted_issues = sorted(self.issues, key=lambda x: x.created_at, reverse=True)
        return sorted_issues[:count]
    
    def find_similar_issues(self, 
                           issue: ValidationIssue,
                           similarity_threshold: float = 0.7) -> List[ValidationIssue]:
        """
        Find issues similar to the given issue.
        
        Args:
            issue: Reference issue for similarity comparison
            similarity_threshold: Minimum similarity score (0.0 to 1.0)
            
        Returns:
            List of similar ValidationIssue objects
        """
        similar = []
        
        for other_issue in self.issues:
            if other_issue.issue_id == issue.issue_id:
                continue
                
            # Simple similarity based on type, severity, and description keywords
            score = self._calculate_similarity(issue, other_issue)
            
            if score >= similarity_threshold:
                similar.append(other_issue)
        
        # Sort by similarity score (highest first)
        similar.sort(key=lambda x: self._calculate_similarity(issue, x), reverse=True)
        return similar
    
    def _calculate_similarity(self, issue1: ValidationIssue, issue2: ValidationIssue) -> float:
        """
        Calculate similarity score between two issues.
        
        Args:
            issue1: First issue
            issue2: Second issue
            
        Returns:
            Similarity score from 0.0 to 1.0
        """
        score = 0.0
        
        # Same type adds significant similarity
        if issue1.issue_type == issue2.issue_type:
            score += 0.4
        
        # Same severity adds some similarity
        if issue1.severity == issue2.severity:
            score += 0.3
        
        # Description keyword overlap
        words1 = set(issue1.description.lower().split())
        words2 = set(issue2.description.lower().split())
        
        if words1 and words2:
            overlap = len(words1.intersection(words2))
            total = len(words1.union(words2))
            word_similarity = overlap / total if total > 0 else 0
            score += 0.3 * word_similarity
        
        return min(score, 1.0)
    
    def export_issues(self, 
                     filepath: str,
                     format: str = "json",
                     filter_criteria: Optional[Dict] = None) -> bool:
        """
        Export issues to file.
        
        Args:
            filepath: Output file path
            format: Export format ("json", "csv", "txt")
            filter_criteria: Optional filtering criteria
            
        Returns:
            True if export successful
        """
        try:
            # Apply filters if specified
            issues_to_export = self.issues
            if filter_criteria:
                issues_to_export = self.filter_issues(**filter_criteria)
            
            if format.lower() == "json":
                return self._export_json(filepath, issues_to_export)
            elif format.lower() == "csv":
                return self._export_csv(filepath, issues_to_export)
            elif format.lower() == "txt":
                return self._export_text(filepath, issues_to_export)
            else:
                raise ValueError(f"Unsupported export format: {format}")
                
        except Exception as e:
            print(f"Export error: {e}")
            return False
    
    def _export_json(self, filepath: str, issues: List[ValidationIssue]) -> bool:
        """Export issues as JSON."""
        import json
        from dataclasses import asdict
        
        data = {
            'export_metadata': {
                'timestamp': datetime.now().isoformat(),
                'total_issues': len(issues),
                'statistics': self.get_statistics()
            },
            'issues': [asdict(issue) for issue in issues]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        return True
    
    def _export_csv(self, filepath: str, issues: List[ValidationIssue]) -> bool:
        """Export issues as CSV."""
        import csv
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'issue_id', 'timestamp', 'issue_type', 'severity', 
                'description', 'suggested_fix', 'context_summary'
            ])
            
            # Data rows
            for issue in issues:
                writer.writerow([
                    issue.issue_id,
                    issue.timestamp.isoformat(),
                    issue.issue_type,
                    issue.severity,
                    issue.description,
                    issue.suggested_fix or '',
                    issue.get_context_summary()
                ])
        
        return True
    
    def _export_text(self, filepath: str, issues: List[ValidationIssue]) -> bool:
        """Export issues as formatted text."""
        with open(filepath, 'w') as f:
            f.write("VALIDATION ISSUES CATALOG\n")
            f.write("=" * 50 + "\n\n")
            
            # Statistics
            stats = self.get_statistics()
            f.write(f"Total Issues: {stats['total_issues']}\n")
            f.write(f"By Type: {stats['by_type']}\n")
            f.write(f"By Severity: {stats['by_severity']}\n\n")
            
            # Individual issues
            for i, issue in enumerate(issues, 1):
                f.write(f"{i}. {issue.issue_id}\n")
                f.write(f"   Type: {issue.issue_type} | Severity: {issue.severity}\n")
                f.write(f"   Time: {issue.timestamp}\n")
                f.write(f"   Context: {issue.get_context_summary()}\n")
                f.write(f"   Description: {issue.description}\n")
                if issue.suggested_fix:
                    f.write(f"   Suggested Fix: {issue.suggested_fix}\n")
                f.write("\n")
        
        return True
    
    def clear_catalog(self) -> None:
        """Clear all issues from catalog."""
        self.issues.clear()
        self._issue_index.clear()
    
    def __len__(self) -> int:
        """Return number of issues in catalog."""
        return len(self.issues)
    
    def __bool__(self) -> bool:
        """Return True if catalog contains issues."""
        return bool(self.issues)