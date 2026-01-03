import { useState, useCallback, useRef } from 'react';
import {
  fetchReferenceState as fetchReferenceStateApi,
  fetchStructurePanel,
  ReferenceStateResponseExtended,
  LevelCrossEvent,
  StructurePanelResponse,
  trackLegForCrossing,
  untrackLegForCrossing,
  RefStateSnapshot,
  ReferenceSwing,
} from '../lib/api';

interface UseReferenceStateReturn {
  referenceState: ReferenceStateResponseExtended | null;
  isLoading: boolean;
  error: string | null;
  fetchReferenceState: (barIndex: number) => void;
  setFromSnapshot: (snapshot: RefStateSnapshot) => void;  // For buffered playback (#456)
  fadingRefs: Set<string>;
  // Sticky leg tracking (Phase 2)
  stickyLegIds: Set<string>;
  toggleStickyLeg: (legId: string) => Promise<{ success: boolean; error?: string }>;
  isStickyLeg: (legId: string) => boolean;
  // Level crossing (Issue #416)
  crossingEvents: LevelCrossEvent[];
  trackError: string | null;
  clearTrackError: () => void;
  // Structure panel (Issue #420)
  structureData: StructurePanelResponse | null;
  isStructureLoading: boolean;
}

export function useReferenceState(): UseReferenceStateReturn {
  const [referenceState, setReferenceState] = useState<ReferenceStateResponseExtended | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fadingRefs, setFadingRefs] = useState<Set<string>>(new Set());
  const [stickyLegIds, setStickyLegIds] = useState<Set<string>>(new Set());
  const [crossingEvents, setCrossingEvents] = useState<LevelCrossEvent[]>([]);
  const [trackError, setTrackError] = useState<string | null>(null);
  // Structure panel state (Issue #420)
  const [structureData, setStructureData] = useState<StructurePanelResponse | null>(null);
  const [isStructureLoading, setIsStructureLoading] = useState(false);

  // Track previous reference IDs for fade-out detection
  const prevRefIdsRef = useRef<Set<string>>(new Set());

  // Fade-out animation duration
  const FADE_DURATION_MS = 300;

  const fetchReferenceState = useCallback(async (barIndex: number) => {
    setIsLoading(true);
    setIsStructureLoading(true);
    setError(null);

    try {
      // Fetch all data in parallel for performance
      const [state, structure] = await Promise.all([
        fetchReferenceStateApi(barIndex),
        fetchStructurePanel(barIndex).catch(() => null),
      ]);

      // Detect removed references for fade-out animation
      const currentIds = new Set(state.references.map(r => r.leg_id));
      const prevIds = prevRefIdsRef.current;

      // Find removed refs
      const removed = new Set<string>();
      prevIds.forEach(id => {
        if (!currentIds.has(id)) {
          removed.add(id);
        }
      });

      if (removed.size > 0) {
        // Set fading refs
        setFadingRefs(removed);

        // Clear fading refs after animation completes
        setTimeout(() => {
          setFadingRefs(new Set());
        }, FADE_DURATION_MS);
      }

      // Update previous refs
      prevRefIdsRef.current = currentIds;

      // Sync sticky legs from backend
      if (state.tracked_leg_ids) {
        setStickyLegIds(new Set(state.tracked_leg_ids));
      }

      // Capture crossing events from this update
      if (state.crossing_events && state.crossing_events.length > 0) {
        setCrossingEvents(state.crossing_events);
      }

      setReferenceState(state);
      setStructureData(structure);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch reference state');
    } finally {
      setIsLoading(false);
      setIsStructureLoading(false);
    }
  }, []);

  // Set reference state from a buffered snapshot (#456)
  // Used during high-speed playback to avoid per-bar API calls
  const setFromSnapshot = useCallback((snapshot: RefStateSnapshot) => {
    // Build derived groupings from references array
    const by_bin: Record<number, ReferenceSwing[]> = {};
    const by_depth: Record<number, ReferenceSwing[]> = {};
    const by_direction: { bull: ReferenceSwing[]; bear: ReferenceSwing[] } = { bull: [], bear: [] };

    for (const ref of snapshot.references) {
      // Group by bin
      if (!by_bin[ref.bin]) by_bin[ref.bin] = [];
      by_bin[ref.bin].push(ref);

      // Group by depth
      if (!by_depth[ref.depth]) by_depth[ref.depth] = [];
      by_depth[ref.depth].push(ref);

      // Group by direction
      by_direction[ref.direction].push(ref);
    }

    // Compute direction imbalance
    let direction_imbalance: 'bull' | 'bear' | null = null;
    if (by_direction.bull.length > by_direction.bear.length * 1.5) {
      direction_imbalance = 'bull';
    } else if (by_direction.bear.length > by_direction.bull.length * 1.5) {
      direction_imbalance = 'bear';
    }

    // Detect removed references for fade-out animation
    const currentIds = new Set(snapshot.references.map(r => r.leg_id));
    const prevIds = prevRefIdsRef.current;
    const removed = new Set<string>();
    prevIds.forEach(id => {
      if (!currentIds.has(id)) {
        removed.add(id);
      }
    });

    if (removed.size > 0) {
      setFadingRefs(removed);
      setTimeout(() => {
        setFadingRefs(new Set());
      }, FADE_DURATION_MS);
    }

    prevRefIdsRef.current = currentIds;

    // Build full response format
    const state: ReferenceStateResponseExtended = {
      references: snapshot.references,
      active_filtered: snapshot.active_filtered ?? [],  // #457: refs that didn't make top N
      by_bin,
      by_depth,
      by_direction,
      direction_imbalance,
      is_warming_up: snapshot.is_warming_up,
      warmup_progress: snapshot.warmup_progress,
      // Keep existing tracked_leg_ids from current state (not in snapshot)
      tracked_leg_ids: referenceState?.tracked_leg_ids ?? [],
      filtered_legs: snapshot.filtered_legs,
      filter_stats: null,  // Not included in snapshot for performance
      crossing_events: snapshot.crossing_events ?? [],  // #458: crossing events from snapshot
    };

    // Update crossing events from snapshot (#458)
    if (snapshot.crossing_events && snapshot.crossing_events.length > 0) {
      setCrossingEvents(snapshot.crossing_events);
    }

    setReferenceState(state);
  }, [referenceState?.tracked_leg_ids]);

  const toggleStickyLeg = useCallback(async (legId: string): Promise<{ success: boolean; error?: string }> => {
    try {
      if (stickyLegIds.has(legId)) {
        const result = await untrackLegForCrossing(legId);
        if (result.success) {
          setStickyLegIds(prev => {
            const next = new Set(prev);
            next.delete(legId);
            return next;
          });
        }
        return { success: result.success, error: result.error || undefined };
      } else {
        const result = await trackLegForCrossing(legId);
        if (result.success) {
          setStickyLegIds(prev => new Set([...prev, legId]));
        } else if (result.error) {
          // Max limit reached
          setTrackError(result.error);
          // Auto-clear after 3 seconds
          setTimeout(() => setTrackError(null), 3000);
        }
        return { success: result.success, error: result.error || undefined };
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to toggle sticky leg';
      console.error('Failed to toggle sticky leg:', err);
      setTrackError(errorMsg);
      setTimeout(() => setTrackError(null), 3000);
      return { success: false, error: errorMsg };
    }
  }, [stickyLegIds]);

  const clearTrackError = useCallback(() => {
    setTrackError(null);
  }, []);

  const isStickyLeg = useCallback((legId: string) => {
    return stickyLegIds.has(legId);
  }, [stickyLegIds]);

  return {
    referenceState,
    isLoading,
    error,
    fetchReferenceState,
    setFromSnapshot,  // For buffered playback (#456)
    fadingRefs,
    stickyLegIds,
    toggleStickyLeg,
    isStickyLeg,
    crossingEvents,
    trackError,
    clearTrackError,
    // Structure panel (Issue #420)
    structureData,
    isStructureLoading,
  };
}
