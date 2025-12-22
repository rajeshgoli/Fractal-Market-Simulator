/**
 * useHierarchyMode - Hook for managing hierarchy exploration state.
 *
 * Handles:
 * - Entering hierarchy mode for a leg (via tree icon click)
 * - Fetching and caching lineage data
 * - Exiting hierarchy mode (via X button or ESC key)
 * - Recentering on a different leg in hierarchy mode
 *
 * Issue #250 - Hierarchy Exploration Mode
 */

import { useState, useCallback, useEffect, useMemo } from 'react';
import { fetchLegLineage, LegLineageResponse } from '../lib/api';
import { ActiveLeg } from '../types';

export interface HierarchyModeState {
  // Whether hierarchy mode is active
  isActive: boolean;
  // The leg that is currently focused (center of hierarchy view)
  focusedLegId: string | null;
  // Lineage data for the focused leg
  lineage: LegLineageResponse | null;
  // Set of leg IDs that should be highlighted (focused + ancestors + descendants)
  highlightedLegIds: Set<string>;
  // Whether lineage is being fetched
  isLoading: boolean;
  // Error message if lineage fetch failed
  error: string | null;
}

export interface UseHierarchyModeResult {
  state: HierarchyModeState;
  // Enter hierarchy mode for a specific leg
  enterHierarchyMode: (legId: string) => Promise<void>;
  // Exit hierarchy mode
  exitHierarchyMode: () => void;
  // Recenter on a different leg while in hierarchy mode
  recenterOnLeg: (legId: string) => Promise<void>;
  // Check if a leg is in the current hierarchy
  isInHierarchy: (legId: string) => boolean;
  // Check if a leg is the focused leg
  isFocused: (legId: string) => boolean;
}

export function useHierarchyMode(_legs: ActiveLeg[]): UseHierarchyModeResult {
  void _legs; // Available for future use (e.g., local lineage computation)
  const [isActive, setIsActive] = useState(false);
  const [focusedLegId, setFocusedLegId] = useState<string | null>(null);
  const [lineage, setLineage] = useState<LegLineageResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Compute highlighted leg IDs from lineage
  const highlightedLegIds = useMemo(() => {
    if (!lineage) return new Set<string>();
    const ids = new Set<string>();
    ids.add(lineage.leg_id);
    lineage.ancestors.forEach(id => ids.add(id));
    lineage.descendants.forEach(id => ids.add(id));
    return ids;
  }, [lineage]);

  // Fetch lineage for a leg
  const fetchLineageForLeg = useCallback(async (legId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchLegLineage(legId);
      setLineage(data);
      setFocusedLegId(legId);
      setIsActive(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch lineage');
      console.error('Failed to fetch lineage:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Enter hierarchy mode
  const enterHierarchyMode = useCallback(async (legId: string) => {
    await fetchLineageForLeg(legId);
  }, [fetchLineageForLeg]);

  // Exit hierarchy mode
  const exitHierarchyMode = useCallback(() => {
    setIsActive(false);
    setFocusedLegId(null);
    setLineage(null);
    setError(null);
  }, []);

  // Recenter on a different leg
  const recenterOnLeg = useCallback(async (legId: string) => {
    if (!isActive) return;
    await fetchLineageForLeg(legId);
  }, [isActive, fetchLineageForLeg]);

  // Check if a leg is in the hierarchy
  const isInHierarchy = useCallback((legId: string) => {
    return highlightedLegIds.has(legId);
  }, [highlightedLegIds]);

  // Check if a leg is the focused leg
  const isFocused = useCallback((legId: string) => {
    return legId === focusedLegId;
  }, [focusedLegId]);

  // Handle ESC key to exit hierarchy mode
  useEffect(() => {
    if (!isActive) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        exitHierarchyMode();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isActive, exitHierarchyMode]);

  const state: HierarchyModeState = {
    isActive,
    focusedLegId,
    lineage,
    highlightedLegIds,
    isLoading,
    error,
  };

  return {
    state,
    enterHierarchyMode,
    exitHierarchyMode,
    recenterOnLeg,
    isInHierarchy,
    isFocused,
  };
}
