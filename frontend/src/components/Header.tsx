import React, { useState, useRef, useEffect } from 'react';
import { Menu, Monitor, Clock, Settings, ChevronDown, BarChart3, Layers } from 'lucide-react';
import type { ViewMode } from '../App';

interface HeaderProps {
  onToggleSidebar: () => void;
  currentTimestamp?: string;
  sourceBarCount: number;
  initStatus?: 'initializing' | 'initialized' | 'playing';
  dataFileName?: string;
  onOpenSettings?: () => void;
  currentView?: ViewMode;
  onNavigate?: (view: ViewMode) => void;
}

export const Header: React.FC<HeaderProps> = ({
  onToggleSidebar,
  currentTimestamp,
  sourceBarCount,
  initStatus,
  dataFileName,
  onOpenSettings,
  currentView = 'dag',
  onNavigate,
}) => {
  const [isViewMenuOpen, setIsViewMenuOpen] = useState(false);
  const viewMenuRef = useRef<HTMLDivElement>(null);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (viewMenuRef.current && !viewMenuRef.current.contains(event.target as Node)) {
        setIsViewMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const viewOptions = [
    { value: 'dag' as ViewMode, label: 'DAG View', icon: BarChart3 },
    { value: 'levels-at-play' as ViewMode, label: 'Levels at Play', icon: Layers },
  ];

  const currentViewOption = viewOptions.find(v => v.value === currentView) || viewOptions[0];
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
          className="text-app-muted hover:text-white p-1 rounded hover:bg-app-card transition-colors"
          aria-label="Toggle sidebar"
        >
          <Menu size={20} />
        </button>

        {/* Title with View Switcher */}
        <div className="flex items-center gap-2">
          <Monitor className="text-trading-blue" size={18} />
          <h1 className="font-bold tracking-wide text-sm">MARKET STRUCTURE ANALYSIS</h1>

          {/* View Switcher Dropdown */}
          {onNavigate && (
            <div className="relative" ref={viewMenuRef}>
              <button
                onClick={() => setIsViewMenuOpen(!isViewMenuOpen)}
                className="flex items-center gap-1.5 px-2 py-1 text-xs font-medium bg-app-card rounded border border-app-border hover:border-app-muted transition-colors"
              >
                <currentViewOption.icon size={14} className="text-trading-blue" />
                <span>{currentViewOption.label}</span>
                <ChevronDown size={12} className={`text-app-muted transition-transform ${isViewMenuOpen ? 'rotate-180' : ''}`} />
              </button>

              {isViewMenuOpen && (
                <div className="absolute top-full left-0 mt-1 bg-app-card border border-app-border rounded shadow-lg z-50 min-w-[150px]">
                  {viewOptions.map((option) => (
                    <button
                      key={option.value}
                      onClick={() => {
                        onNavigate(option.value);
                        setIsViewMenuOpen(false);
                      }}
                      className={`w-full flex items-center gap-2 px-3 py-2 text-xs text-left hover:bg-app-secondary transition-colors ${
                        currentView === option.value ? 'bg-app-secondary text-trading-blue' : 'text-app-text'
                      }`}
                    >
                      <option.icon size={14} />
                      <span>{option.label}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Status Badge */}
        {initStatus && (
          <div className={`px-2 py-0.5 rounded text-xs font-medium ${
            initStatus === 'initializing'
              ? 'bg-trading-orange/20 text-trading-orange'
              : initStatus === 'initialized'
              ? 'bg-trading-bull/20 text-trading-bull'
              : 'bg-trading-blue/20 text-trading-blue'
          }`}>
            {initStatus === 'initializing' && 'Initializing...'}
            {initStatus === 'initialized' && 'Initialized'}
            {initStatus === 'playing' && 'Playing'}
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
