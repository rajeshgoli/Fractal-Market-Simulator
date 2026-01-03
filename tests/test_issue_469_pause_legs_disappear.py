"""
Test documenting issue #469: Backend API limitation when BE ahead of FE.

ROOT CAUSE (confirmed):
The API endpoint `/api/reference/state` uses detector.state.active_legs from
the CURRENT detector position, not the historical state at the requested bar_index.
When BE has processed ahead of FE, legs pruned between those positions are missing.

FIX (implemented in frontend):
LevelsAtPlayView.tsx now:
1. On pause: Keeps buffered state (doesn't call API)
2. On view switch: Triggers resync before fetching

These tests document the backend limitation. The frontend fix avoids the
problematic code path entirely.
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from src.replay_server.api import app, init_app, state
from src.replay_server.routers.cache import reset_replay_cache, get_replay_cache


@pytest.fixture
def client():
    """Create test client and initialize with test data."""
    reset_replay_cache()

    # Find test data file
    project_root = Path(__file__).parent.parent
    test_file = project_root / "test_data" / "5min.csv"

    if not test_file.exists():
        # Try alternate location
        test_file = project_root / "test_data" / "test.csv"

    if not test_file.exists():
        pytest.skip("No test data file available")

    # Initialize app with test data
    init_app(
        data_file=str(test_file),
        resolution_minutes=5,
        window_size=5000,
        target_bars=200,
        window_offset=0,
        mode="dag"
    )

    with TestClient(app) as client:
        yield client


@pytest.mark.xfail(reason="Known backend limitation - FE fix avoids this code path")
def test_api_returns_stale_legs_when_be_ahead(client):
    """
    Documents backend limitation: API returns stale data when BE ahead of FE.

    This test confirms the root cause of issue #469:
    - Buffer captures correct state at each bar
    - API uses current detector state (may be ahead)
    - Legs pruned between FE position and BE position are missing

    The frontend fix (LevelsAtPlayView.tsx) avoids this by:
    1. Not calling API on pause (keeps buffered state)
    2. Triggering resync before API calls on view switch
    """
    # Step 1: Advance with buffered ref_states enabled to get correct state
    # We need to advance enough bars for legs to form and potentially be pruned

    # First advance: get to a point where we have some references
    advance_response = client.post("/api/dag/advance", json={
        "current_bar_index": -1,
        "advance_by": 500,  # Advance 500 bars to get legs forming
        "include_per_bar_ref_states": True,
    })
    assert advance_response.status_code == 200
    data = advance_response.json()

    # Check if we got ref_states in buffer
    ref_states = data.get("ref_states", [])
    if not ref_states:
        pytest.skip("No ref_states returned - need more bars for legs to form")

    # Find a bar with references in the buffer
    buffer_bar_with_refs = None
    buffer_leg_ids = None
    for ref_state in ref_states:
        refs = ref_state.get("references", [])
        if refs:
            buffer_bar_with_refs = ref_state["bar_index"]
            buffer_leg_ids = {r["leg_id"] for r in refs}
            break

    if buffer_bar_with_refs is None:
        pytest.skip("No references found in buffer - data may not produce legs")

    print(f"\nFound {len(buffer_leg_ids)} legs at bar {buffer_bar_with_refs} in buffer")
    print(f"Buffer leg IDs: {buffer_leg_ids}")

    # Step 2: Continue advancing BE further - this is where legs might be pruned
    advance_response2 = client.post("/api/dag/advance", json={
        "current_bar_index": 499,  # Continue from where we left off
        "advance_by": 200,  # Advance 200 more bars
        "include_per_bar_ref_states": False,  # Don't need buffer this time
    })
    assert advance_response2.status_code == 200

    # Step 3: Simulate "pause" - call API at the earlier bar_index
    # This is what LevelsAtPlayView does when user pauses
    api_response = client.get(f"/api/reference/state?bar_index={buffer_bar_with_refs}")
    assert api_response.status_code == 200
    api_data = api_response.json()

    api_refs = api_data.get("references", [])
    api_leg_ids = {r["leg_id"] for r in api_refs}

    print(f"\nAPI returned {len(api_leg_ids)} legs at bar {buffer_bar_with_refs}")
    print(f"API leg IDs: {api_leg_ids}")

    # Step 4: Compare buffer vs API
    missing_from_api = buffer_leg_ids - api_leg_ids
    extra_in_api = api_leg_ids - buffer_leg_ids

    print(f"\nComparison:")
    print(f"  Missing from API (were in buffer): {missing_from_api}")
    print(f"  Extra in API (not in buffer): {extra_in_api}")

    # This assertion will FAIL if the bug exists, confirming the hypothesis
    if missing_from_api:
        print(f"\n*** BUG CONFIRMED: {len(missing_from_api)} legs disappeared on 'pause' ***")
        print(f"These legs were in the buffer at bar {buffer_bar_with_refs} but are missing from API:")
        for leg_id in missing_from_api:
            print(f"  - {leg_id}")

    # Assert that all buffer legs are in API response
    # If this fails, the bug is confirmed
    assert missing_from_api == set(), (
        f"Bug #469 confirmed: {len(missing_from_api)} legs from buffer missing in API response. "
        f"Missing: {missing_from_api}"
    )


def test_identify_pruned_legs():
    """
    Diagnostic test to identify which legs get pruned and when.

    This helps understand the pruning patterns that cause issue #469.
    """
    reset_replay_cache()

    project_root = Path(__file__).parent.parent
    test_file = project_root / "test_data" / "5min.csv"

    if not test_file.exists():
        test_file = project_root / "test_data" / "test.csv"

    if not test_file.exists():
        pytest.skip("No test data file available")

    init_app(
        data_file=str(test_file),
        resolution_minutes=5,
        window_size=5000,
        target_bars=200,
        window_offset=0,
        mode="dag"
    )

    with TestClient(app) as client:
        # Advance with per-bar ref states to track leg lifecycle
        advance_response = client.post("/api/dag/advance", json={
            "current_bar_index": -1,
            "advance_by": 700,
            "include_per_bar_ref_states": True,
        })
        assert advance_response.status_code == 200
        data = advance_response.json()

        ref_states = data.get("ref_states", [])
        if not ref_states:
            pytest.skip("No ref_states returned")

        # Track leg lifecycle across bars
        leg_first_seen = {}  # leg_id -> bar_index when first appeared
        leg_last_seen = {}   # leg_id -> bar_index when last appeared

        for ref_state in ref_states:
            bar_index = ref_state["bar_index"]
            refs = ref_state.get("references", [])

            for ref in refs:
                leg_id = ref["leg_id"]
                if leg_id not in leg_first_seen:
                    leg_first_seen[leg_id] = bar_index
                leg_last_seen[leg_id] = bar_index

        # Find legs that disappeared before the end
        final_bar = ref_states[-1]["bar_index"] if ref_states else 0
        disappeared_legs = {
            leg_id: (leg_first_seen[leg_id], leg_last_seen[leg_id])
            for leg_id, last_bar in leg_last_seen.items()
            if last_bar < final_bar
        }

        print(f"\n=== Leg Lifecycle Analysis ===")
        print(f"Total unique legs seen: {len(leg_first_seen)}")
        print(f"Legs that disappeared before final bar ({final_bar}): {len(disappeared_legs)}")

        if disappeared_legs:
            print(f"\nDisappeared legs (potential issue #469 candidates):")
            for leg_id, (first, last) in sorted(disappeared_legs.items(), key=lambda x: x[1][1]):
                print(f"  {leg_id}: bars {first}-{last} (vanished at bar {last})")

        # For each disappeared leg, verify the bug by checking API at their last seen bar
        cache = get_replay_cache()
        detector = cache.get("detector")

        if disappeared_legs and detector:
            current_active_ids = {leg.leg_id for leg in detector.state.active_legs}

            # Count how many disappeared legs are no longer in active_legs
            truly_pruned = {
                leg_id for leg_id in disappeared_legs
                if leg_id not in current_active_ids
            }

            print(f"\nOf disappeared legs, {len(truly_pruned)} are no longer in detector.state.active_legs")
            print(f"These would be missing from API responses - confirming bug #469")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
