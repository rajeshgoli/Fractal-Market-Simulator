import React from 'react';
import { Monitor, Clock, ChevronDown } from 'lucide-react';

interface HeaderProps {
  onToggleSidebar: () => void;
  currentTimestamp?: string;
  sourceBarCount: number;
  calibrationStatus?: 'calibrating' | 'calibrated' | 'playing';
}

export const Header: React.FC<HeaderProps> = ({
  onToggleSidebar,
  currentTimestamp,
  sourceBarCount,
  calibrationStatus,
}) => {
  // Format timestamp for display (fixed-width)
  const formatTimestamp = (ts?: string) => {
    if (!ts) return { date: '---', time: '--:--:--' };
    try {
      const d = new Date(ts);
      return {
        date: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }),
        time: d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      };
    } catch {
      return { date: '---', time: '--:--:--' };
    }
  };

  const { date, time } = formatTimestamp(currentTimestamp);

  return (
    <header className="h-12 bg-app-secondary border-b border-app-border flex items-center justify-between px-4 shrink-0 z-20">
      <div className="flex items-center gap-4">
        {/* Sidebar Toggle */}
        <button
          onClick={onToggleSidebar}
          className="text-app-muted hover:text-white p-1 rounded hover:bg-app-card transition-colors md:hidden"
          aria-label="Toggle sidebar"
        >
          <ChevronDown size={16} className="rotate-90" />
        </button>

        {/* Title */}
        <div className="flex items-center gap-2">
          <Monitor className="text-trading-blue" size={18} />
          <h1 className="font-bold tracking-wide text-sm">MARKET REPLAY</h1>
        </div>

        {/* Calibration Status Badge */}
        {calibrationStatus && (
          <div className={`px-2 py-0.5 rounded text-xs font-medium ${
            calibrationStatus === 'calibrating'
              ? 'bg-trading-orange/20 text-trading-orange'
              : calibrationStatus === 'calibrated'
              ? 'bg-trading-bull/20 text-trading-bull'
              : 'bg-trading-blue/20 text-trading-blue'
          }`}>
            {calibrationStatus === 'calibrating' && 'Calibrating...'}
            {calibrationStatus === 'calibrated' && 'Calibrated'}
            {calibrationStatus === 'playing' && 'Playing'}
          </div>
        )}
      </div>

      {/* Right Side Info */}
      <div className="flex items-center gap-6">
        {/* Current Time Position */}
        <div className="flex items-center gap-2 text-sm font-mono tabular-nums text-app-text bg-app-card px-3 py-1 rounded border border-app-border/50">
          <Clock size={14} className="text-app-muted" />
          <span>{date}</span>
          <span className="text-app-border">|</span>
          <span>{time}</span>
        </div>

        {/* Source Bar Info */}
        <div className="hidden md:flex items-center gap-2 text-xs">
          <span className="text-app-muted">Source:</span>
          <span className="font-mono tabular-nums text-app-text">
            {sourceBarCount.toLocaleString()} bars
          </span>
        </div>
      </div>
    </header>
  );
};
