import React, { useState, useRef, useEffect } from 'react';
import { Menu, Monitor, Clock, ChevronDown, GitBranch, Settings } from 'lucide-react';

// ViewMode kept for backward compatibility (DAGView is now the sole view)
type ViewMode = 'dag';

interface HeaderProps {
  onToggleSidebar: () => void;
  currentTimestamp?: string;
  sourceBarCount: number;
  calibrationStatus?: 'calibrating' | 'calibrated' | 'playing';
  currentMode?: ViewMode;
  onModeChange?: (mode: ViewMode) => void;
  dataFileName?: string;
  onOpenSettings?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  onToggleSidebar,
  currentTimestamp,
  sourceBarCount,
  calibrationStatus,
  currentMode = 'dag',
  onModeChange,
  dataFileName,
  onOpenSettings,
}) => {
  const [isNavOpen, setIsNavOpen] = useState(false);
  const navRef = useRef<HTMLDivElement>(null);

  // Close nav when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (navRef.current && !navRef.current.contains(event.target as Node)) {
        setIsNavOpen(false);
      }
    };

    if (isNavOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isNavOpen]);

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

  // Single view available - Market Structure View
  const navItems = [
    {
      id: 'dag' as ViewMode,
      label: 'Market Structure View',
      icon: <GitBranch size={16} />,
      description: 'View market structure as it forms',
    },
  ];

  return (
    <header className="h-12 bg-app-secondary border-b border-app-border flex items-center justify-between px-4 shrink-0 z-20">
      <div className="flex items-center gap-4">
        {/* Hamburger Menu Button */}
        <div className="relative" ref={navRef}>
          <button
            onClick={() => setIsNavOpen(!isNavOpen)}
            className="text-app-muted hover:text-white p-1 rounded hover:bg-app-card transition-colors"
            aria-label="Toggle navigation"
          >
            <Menu size={20} />
          </button>

          {/* Navigation Dropdown */}
          {isNavOpen && (
            <div className="absolute top-full left-0 mt-2 w-64 bg-app-secondary border border-app-border rounded-lg shadow-xl z-50 overflow-hidden">
              <div className="p-2">
                {navItems.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => {
                      if (onModeChange && item.id !== currentMode) {
                        onModeChange(item.id);
                      }
                      setIsNavOpen(false);
                    }}
                    className={`w-full flex items-start gap-3 p-3 rounded-lg transition-colors group text-left ${
                      item.id === currentMode
                        ? 'bg-trading-blue/20 text-trading-blue'
                        : 'hover:bg-app-card'
                    }`}
                  >
                    <div className={`mt-0.5 ${item.id === currentMode ? 'text-trading-blue' : 'text-trading-blue'}`}>
                      {item.icon}
                    </div>
                    <div>
                      <div className={`text-sm font-medium ${
                        item.id === currentMode ? 'text-trading-blue' : 'text-app-text group-hover:text-white'
                      }`}>
                        {item.label}
                        {item.id === currentMode && <span className="ml-2 text-xs opacity-60">(current)</span>}
                      </div>
                      <div className="text-xs text-app-muted">
                        {item.description}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Sidebar Toggle (separate from nav) */}
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
          <h1 className="font-bold tracking-wide text-sm">MARKET STRUCTURE ANALYSIS</h1>
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
      <div className="flex items-center gap-4">
        {/* Current Time Position */}
        <div className="flex items-center gap-2 text-sm font-mono tabular-nums text-app-text bg-app-card px-3 py-1 rounded border border-app-border/50">
          <Clock size={14} className="text-app-muted" />
          <span>{date}</span>
          <span className="text-app-border">|</span>
          <span>{time}</span>
        </div>

        {/* Source Bar Info with Settings Button */}
        <div className="hidden md:flex items-center gap-3 text-xs">
          {dataFileName && (
            <>
              <span className="text-app-muted">File:</span>
              <span className="font-mono text-app-text">{dataFileName}</span>
              <span className="text-app-border">|</span>
            </>
          )}
          <span className="text-app-muted">Source:</span>
          <span className="font-mono tabular-nums text-app-text">
            {sourceBarCount.toLocaleString()} bars
          </span>

          {/* Settings Button */}
          {onOpenSettings && (
            <button
              onClick={onOpenSettings}
              className="ml-2 p-1.5 text-app-muted hover:text-white hover:bg-app-card rounded transition-colors"
              aria-label="Open settings"
              title="Data source settings"
            >
              <Settings size={14} />
            </button>
          )}
        </div>
      </div>
    </header>
  );
};
