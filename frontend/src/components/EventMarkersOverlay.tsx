/**
 * EventMarkersOverlay - Issue #267
 *
 * Displays markers on candles where lifecycle events occurred for followed legs.
 * Uses the lightweight-charts SeriesMarkersPlugin API.
 */

import { useEffect, useCallback } from 'react';
import { ISeriesMarkersPluginApi, Time, SeriesMarker } from 'lightweight-charts';
import { BarData } from '../types';
import { LifecycleEventWithLegInfo } from '../hooks/useFollowLeg';

interface EventMarkersOverlayProps {
  markersPlugin: ISeriesMarkersPluginApi<Time> | null;
  bars: BarData[];
  eventsByBar: Map<number, LifecycleEventWithLegInfo[]>;
  onMarkerClick?: (barIndex: number, events: LifecycleEventWithLegInfo[]) => void;
}

/**
 * Get marker shape based on event type
 */
function getMarkerShape(eventType: string): 'arrowUp' | 'arrowDown' | 'circle' | 'square' {
  switch (eventType) {
    case 'formed':
      return 'arrowUp';
    case 'invalidated':
    case 'engulfed':
      return 'arrowDown';
    case 'pruned':
      return 'square';
    case 'origin_breached':
    case 'pivot_breached':
      return 'circle';
    default:
      return 'circle';
  }
}

/**
 * Get marker position based on event
 */
function getMarkerPosition(eventType: string): 'aboveBar' | 'belowBar' {
  // Negative events below, positive events above
  switch (eventType) {
    case 'formed':
      return 'aboveBar';
    case 'invalidated':
    case 'engulfed':
    case 'pruned':
      return 'belowBar';
    case 'origin_breached':
    case 'pivot_breached':
      return 'belowBar';
    default:
      return 'belowBar';
  }
}

/**
 * Get marker text based on event type
 */
function getMarkerText(eventType: string): string {
  switch (eventType) {
    case 'formed':
      return 'F';
    case 'invalidated':
      return 'X';
    case 'engulfed':
      return 'E';
    case 'pruned':
      return 'P';
    case 'origin_breached':
      return 'O!';
    case 'pivot_breached':
      return 'P!';
    default:
      return '?';
  }
}

export const EventMarkersOverlay: React.FC<EventMarkersOverlayProps> = ({
  markersPlugin,
  bars,
  eventsByBar,
}) => {
  // Build timestamp lookup
  const getTimestampForBarIndex = useCallback((barIndex: number): number | null => {
    // Find bar with matching source index range
    for (const bar of bars) {
      if (bar.source_start_index !== undefined && bar.source_end_index !== undefined) {
        if (barIndex >= bar.source_start_index && barIndex <= bar.source_end_index) {
          return bar.timestamp;
        }
      }
      // Fallback: match by exact index
      if (bar.index === barIndex) {
        return bar.timestamp;
      }
    }
    return null;
  }, [bars]);

  // Update markers when events change
  useEffect(() => {
    if (!markersPlugin || bars.length === 0) {
      return;
    }

    // Build markers from events
    const markers: SeriesMarker<Time>[] = [];

    for (const [barIndex, events] of eventsByBar) {
      const timestamp = getTimestampForBarIndex(barIndex);
      if (timestamp === null) continue;

      // If multiple events on same bar, show the most significant one
      // Priority: invalidated > engulfed > pruned > formed > breaches
      const sortedEvents = [...events].sort((a, b) => {
        const priority: Record<string, number> = {
          invalidated: 5,
          engulfed: 4,
          pruned: 3,
          formed: 2,
          origin_breached: 1,
          pivot_breached: 1,
        };
        return (priority[b.event_type] || 0) - (priority[a.event_type] || 0);
      });

      const primaryEvent = sortedEvents[0];

      markers.push({
        time: timestamp as Time,
        position: getMarkerPosition(primaryEvent.event_type),
        color: primaryEvent.legColor,
        shape: getMarkerShape(primaryEvent.event_type),
        text: getMarkerText(primaryEvent.event_type),
        size: events.length > 1 ? 2 : 1, // Larger if multiple events
      });
    }

    // Sort markers by time (required by lightweight-charts)
    markers.sort((a, b) => (a.time as number) - (b.time as number));

    // Update the markers plugin
    markersPlugin.setMarkers(markers);

    // Cleanup: clear markers on unmount
    return () => {
      markersPlugin.setMarkers([]);
    };
  }, [markersPlugin, bars, eventsByBar, getTimestampForBarIndex]);

  // This component only manages markers via the plugin, no visual render
  return null;
};
