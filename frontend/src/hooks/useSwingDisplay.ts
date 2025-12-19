import { useMemo } from 'react';
import {
  CalibrationSwing,
  CalibrationData,
  SwingDisplayConfig,
  SwingScaleKey,
} from '../types';

interface UseSwingDisplayResult {
  /** Filtered and ranked active swings based on display config (limited by activeSwingCount for chart display) */
  filteredActiveSwings: CalibrationSwing[];
  /** All active swings for enabled scales (not limited - for navigation) */
  allNavigableSwings: CalibrationSwing[];
  /** Filtered stats by scale (only enabled scales) */
  filteredStats: Record<string, { total_swings: number; active_swings: number; displayed_swings: number }>;
}

/**
 * Hook to filter and rank active swings based on display configuration.
 *
 * - Filters by enabled scales (XL/L/M/S toggles)
 * - Limits to top N biggest swings per scale (activeSwingCount)
 * - Ranks swings by size (pts) within each scale
 */
export function useSwingDisplay(
  calibrationData: CalibrationData | null,
  displayConfig: SwingDisplayConfig
): UseSwingDisplayResult {
  return useMemo(() => {
    if (!calibrationData) {
      return {
        filteredActiveSwings: [],
        allNavigableSwings: [],
        filteredStats: {},
      };
    }

    const { enabledScales, activeSwingCount } = displayConfig;
    const scaleOrder: SwingScaleKey[] = ['XL', 'L', 'M', 'S'];

    const filteredActiveSwings: CalibrationSwing[] = [];
    const allNavigableSwings: CalibrationSwing[] = [];
    const filteredStats: Record<string, { total_swings: number; active_swings: number; displayed_swings: number }> = {};

    for (const scale of scaleOrder) {
      const scaleStat = calibrationData.stats_by_scale[scale];
      // Use active_swings_by_scale for both navigation and display (reference swings only)
      const activeSwings = calibrationData.active_swings_by_scale[scale] || [];

      if (!scaleStat) continue;

      // Get displayed swings (top N by size if scale is enabled)
      let displayedSwings: CalibrationSwing[] = [];
      if (enabledScales.has(scale)) {
        // Active swings for navigation - sorted by size, ranked but not limited
        const sortedActiveSwings = [...activeSwings].sort((a, b) => b.size - a.size);
        const rankedActiveSwings = sortedActiveSwings.map((swing, index) => ({
          ...swing,
          rank: index + 1,  // Rank based on size order
        }));
        allNavigableSwings.push(...rankedActiveSwings);

        // Active swings for chart display - take top N from the same list
        displayedSwings = rankedActiveSwings.slice(0, activeSwingCount);
        filteredActiveSwings.push(...displayedSwings);
      }

      // Always include stats for all scales (so UI can show grayed out)
      filteredStats[scale] = {
        total_swings: scaleStat.total_swings,
        active_swings: scaleStat.active_swings,
        displayed_swings: displayedSwings.length,
      };
    }

    return {
      filteredActiveSwings,
      allNavigableSwings,
      filteredStats,
    };
  }, [calibrationData, displayConfig]);
}
