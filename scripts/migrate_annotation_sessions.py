#!/usr/bin/env python3
"""
One-time migration script: Move annotation sessions to ground_truth.json

This script:
1. Reads all session+review pairs from annotation_sessions/
2. Appends each to ground_truth/ground_truth.json
3. Reports migration status

After successful migration, annotation_sessions/ can be deleted manually.

Usage:
    python scripts/migrate_annotation_sessions.py [--dry-run]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ground_truth_annotator.storage import (
    GROUND_TRUTH_DIR,
    GROUND_TRUTH_FILE,
    GROUND_TRUTH_SCHEMA_VERSION,
)


def find_session_pairs(sessions_dir: Path) -> list[tuple[Path, Path | None]]:
    """
    Find all session+review pairs in the sessions directory.

    Returns:
        List of (session_path, review_path) tuples.
        review_path is None if no corresponding review file exists.
    """
    pairs = []

    # Find all session files (not review files)
    for session_path in sorted(sessions_dir.glob("*.json")):
        if session_path.name.endswith("_review.json"):
            continue
        if session_path.name.startswith("inprogress-"):
            continue

        # Look for corresponding review file
        # Session files can have two naming patterns:
        # 1. UUID-based: {session_id}.json -> {session_id}_review.json
        # 2. Timestamp-based: yyyy-mmm-dd-HHmm-ver{N}.json

        # For timestamp-based, try to find review by reading session_id
        review_path = None
        try:
            with open(session_path, 'r') as f:
                session_data = json.load(f)
                session_id = session_data.get('session_id')
                if session_id:
                    potential_review = sessions_dir / f"{session_id}_review.json"
                    if potential_review.exists():
                        review_path = potential_review
        except (json.JSONDecodeError, KeyError):
            pass

        # Also check for timestamp-based review naming
        if review_path is None:
            base = session_path.stem
            potential_review = sessions_dir / f"{base}_review.json"
            if potential_review.exists():
                review_path = potential_review

        pairs.append((session_path, review_path))

    return pairs


def load_or_create_ground_truth(path: Path) -> dict:
    """Load existing ground_truth.json or create new structure."""
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)

    return {
        "metadata": {
            "schema_version": GROUND_TRUTH_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        "sessions": []
    }


def migrate_sessions(sessions_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    """
    Migrate all sessions from sessions_dir to ground_truth.json.

    Args:
        sessions_dir: Path to annotation_sessions directory
        dry_run: If True, just report what would be done

    Returns:
        Tuple of (sessions_migrated, sessions_skipped)
    """
    if not sessions_dir.exists():
        print(f"Sessions directory not found: {sessions_dir}")
        return 0, 0

    pairs = find_session_pairs(sessions_dir)
    if not pairs:
        print("No sessions found to migrate.")
        return 0, 0

    print(f"Found {len(pairs)} session(s) to migrate")

    # Ensure ground_truth directory exists
    if not dry_run:
        GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)

    # Load or create ground_truth.json
    ground_truth = load_or_create_ground_truth(GROUND_TRUTH_FILE)

    # Track existing sessions to avoid duplicates
    existing_filenames = {
        entry.get("original_filename")
        for entry in ground_truth.get("sessions", [])
    }

    migrated = 0
    skipped = 0

    for session_path, review_path in pairs:
        original_filename = session_path.stem

        # Check for duplicates
        if original_filename in existing_filenames:
            print(f"  SKIP: {original_filename} (already in ground_truth.json)")
            skipped += 1
            continue

        # Load session data
        try:
            with open(session_path, 'r') as f:
                session_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ERROR: {original_filename} - {e}")
            skipped += 1
            continue

        # Load review data if exists
        review_data = None
        if review_path:
            try:
                with open(review_path, 'r') as f:
                    review_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass  # Proceed without review

        # Create entry
        entry = {
            "finalized_at": datetime.now(timezone.utc).isoformat(),
            "original_filename": original_filename,
            "session": session_data
        }
        if review_data:
            entry["review"] = review_data

        if dry_run:
            review_status = "with review" if review_data else "no review"
            print(f"  Would migrate: {original_filename} ({review_status})")
        else:
            ground_truth["sessions"].append(entry)
            existing_filenames.add(original_filename)
            review_status = "with review" if review_data else "no review"
            print(f"  Migrated: {original_filename} ({review_status})")

        migrated += 1

    # Save ground_truth.json
    if not dry_run and migrated > 0:
        ground_truth["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(GROUND_TRUTH_FILE, 'w') as f:
            json.dump(ground_truth, f, indent=2)
        print(f"\nSaved ground_truth.json with {len(ground_truth['sessions'])} total sessions")

    return migrated, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Migrate annotation sessions to ground_truth.json"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("annotation_sessions"),
        help="Source directory (default: annotation_sessions)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Annotation Session Migration")
    print("=" * 60)

    if args.dry_run:
        print("DRY RUN - no changes will be made\n")

    migrated, skipped = migrate_sessions(args.source, dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print(f"Migration complete: {migrated} migrated, {skipped} skipped")

    if not args.dry_run and migrated > 0:
        print(f"\nNext steps:")
        print(f"  1. Verify ground_truth/ground_truth.json contains all sessions")
        print(f"  2. Delete the old directory: rm -rf {args.source}")
        print(f"  3. Commit ground_truth/ground_truth.json to version control")


if __name__ == "__main__":
    main()
