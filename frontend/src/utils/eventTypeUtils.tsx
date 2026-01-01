/**
 * Event type utilities for icons and colors.
 * Shared logic for displaying event type icons across components.
 */

import React from 'react';
import {
  GitBranch,
  Scissors,
  Ban,
  AlertTriangle,
} from 'lucide-react';
import { EventType } from '../types';

/**
 * Get the icon component for an event type.
 *
 * @param type - Event type string (EventType enum)
 * @param size - Icon size in pixels (default: 16)
 */
export function getIconForEventType(
  type: string,
  size: number = 16
): React.ReactNode {
  switch (type) {
    case EventType.LEG_CREATED:
    case 'LEG_CREATED':
      return <GitBranch size={size} className="text-trading-blue" />;
    case EventType.LEG_PRUNED:
    case 'LEG_PRUNED':
      return <Scissors size={size} className="text-trading-orange" />;
    case EventType.LEG_INVALIDATED:
    case 'LEG_INVALIDATED':
      return <Ban size={size} className="text-trading-bear" />;
    default:
      return <AlertTriangle size={size} className="text-trading-orange" />;
  }
}

/**
 * Get the color class for an event type.
 *
 * @param type - Event type string
 */
export function getColorForEventType(type: string): string {
  switch (type) {
    case EventType.LEG_CREATED:
    case 'LEG_CREATED':
      return 'text-trading-blue';
    case EventType.LEG_PRUNED:
    case 'LEG_PRUNED':
      return 'text-trading-orange';
    case EventType.LEG_INVALIDATED:
    case 'LEG_INVALIDATED':
      return 'text-trading-bear';
    default:
      return 'text-trading-orange';
  }
}
