import React, { useState, useEffect } from 'react';
import { Settings, X, Loader2, AlertCircle, Calendar } from 'lucide-react';
import { fetchDataFiles, restartSession, DataFileInfo } from '../lib/api';

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  currentDataFile: string;
  onSessionRestart: () => void;
  onSaveSession: (dataFile: string, startDate: string | null) => void;
  // Multi-tenant mode props
  multiTenant?: boolean;
  sessionStartDate?: string | null;  // ISO date from session (for multi-tenant)
  sessionEndDate?: string | null;    // ISO date from session (for multi-tenant)
}

export const SettingsPanel: React.FC<SettingsPanelProps> = ({
  isOpen,
  onClose,
  currentDataFile,
  onSessionRestart,
  onSaveSession,
  multiTenant = false,
  sessionStartDate,
  sessionEndDate,
}) => {
  const [files, setFiles] = useState<DataFileInfo[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>(currentDataFile);
  const [startDate, setStartDate] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [isRestarting, setIsRestarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Selected file info for date constraints (single-tenant mode)
  const selectedFileInfo = files.find(f => f.path === selectedFile);

  // Load files on mount (only in single-tenant mode)
  useEffect(() => {
    if (!isOpen) return;
    if (multiTenant) {
      // In multi-tenant mode, no file loading needed
      setIsLoading(false);
      return;
    }

    const loadFiles = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const dataFiles = await fetchDataFiles();
        setFiles(dataFiles);
        // Set default selection if current file is valid
        if (currentDataFile && dataFiles.some(f => f.path === currentDataFile)) {
          setSelectedFile(currentDataFile);
        } else if (dataFiles.length > 0) {
          setSelectedFile(dataFiles[0].path);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load files');
      } finally {
        setIsLoading(false);
      }
    };

    loadFiles();
  }, [isOpen, currentDataFile, multiTenant]);

  // Format number with K/M suffix
  const formatNumber = (n: number): string => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return n.toString();
  };

  // Format date for display
  const formatDate = (isoDate: string | null | undefined): string => {
    if (!isoDate) return 'N/A';
    try {
      return new Date(isoDate).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      });
    } catch {
      return isoDate;
    }
  };

  // Get min/max dates for date picker
  const getMinDate = (): string => {
    if (multiTenant) {
      // Use session dates in multi-tenant mode
      if (!sessionStartDate) return '';
      return sessionStartDate.split('T')[0];
    }
    // Use selected file dates in single-tenant mode
    if (!selectedFileInfo?.start_date) return '';
    return selectedFileInfo.start_date.split('T')[0];
  };

  const getMaxDate = (): string => {
    if (multiTenant) {
      // Use session dates in multi-tenant mode
      if (!sessionEndDate) return '';
      return sessionEndDate.split('T')[0];
    }
    // Use selected file dates in single-tenant mode
    if (!selectedFileInfo?.end_date) return '';
    return selectedFileInfo.end_date.split('T')[0];
  };

  // Check if we have valid date constraints
  const hasDateConstraints = multiTenant
    ? Boolean(sessionStartDate && sessionEndDate)
    : Boolean(selectedFileInfo?.start_date && selectedFileInfo?.end_date);

  // Handle apply
  const handleApply = async () => {
    // In multi-tenant mode, we only change start date (keep current file)
    const fileToUse = multiTenant ? currentDataFile : selectedFile;
    if (!fileToUse && !multiTenant) return;

    setIsRestarting(true);
    setError(null);

    try {
      await restartSession({
        data_file: fileToUse,
        start_date: startDate || undefined,
      });

      // Save to localStorage
      onSaveSession(fileToUse, startDate || null);

      // Trigger full page reload to reinitialize
      onSessionRestart();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to restart session');
    } finally {
      setIsRestarting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative bg-app-secondary border border-app-border rounded-xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-app-border">
          <div className="flex items-center gap-3">
            {multiTenant ? (
              <Calendar className="text-trading-blue" size={20} />
            ) : (
              <Settings className="text-trading-blue" size={20} />
            )}
            <h2 className="text-lg font-semibold">
              {multiTenant ? 'Playback Settings' : 'Data Source Settings'}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-app-muted hover:text-white p-1 rounded hover:bg-app-card transition-colors"
            aria-label="Close"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-5">
          {/* Error Display */}
          {error && (
            <div className="flex items-center gap-2 p-3 bg-trading-bear/10 border border-trading-bear/30 rounded-lg text-trading-bear text-sm">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {/* Loading State (single-tenant only) */}
          {isLoading && !multiTenant ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="animate-spin text-trading-blue" size={24} />
              <span className="ml-2 text-app-muted">Loading files...</span>
            </div>
          ) : (
            <>
              {/* File Selection (single-tenant only) */}
              {!multiTenant && (
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-app-text">
                    Data File
                  </label>
                  <select
                    value={selectedFile}
                    onChange={(e) => {
                      setSelectedFile(e.target.value);
                      setStartDate(''); // Reset date when file changes
                    }}
                    className="w-full px-3 py-2 bg-app-card border border-app-border rounded-lg text-app-text focus:outline-none focus:ring-2 focus:ring-trading-blue/50"
                    disabled={isRestarting}
                  >
                    {files.map((file) => (
                      <option key={file.path} value={file.path}>
                        {file.name} ({formatNumber(file.total_bars)} bars, {file.resolution})
                      </option>
                    ))}
                  </select>

                  {/* File Info */}
                  {selectedFileInfo && (
                    <div className="text-xs text-app-muted mt-1">
                      {formatDate(selectedFileInfo.start_date)} — {formatDate(selectedFileInfo.end_date)}
                    </div>
                  )}
                </div>
              )}

              {/* Data Range Info (multi-tenant) */}
              {multiTenant && hasDateConstraints && (
                <div className="p-3 bg-app-card rounded-lg border border-app-border">
                  <div className="text-xs text-app-muted mb-1">Available Data Range</div>
                  <div className="text-sm text-app-text font-medium">
                    {formatDate(sessionStartDate)} — {formatDate(sessionEndDate)}
                  </div>
                </div>
              )}

              {/* Start Date */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-app-text">
                  Start Date <span className="text-app-muted font-normal">(optional)</span>
                </label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  min={getMinDate()}
                  max={getMaxDate()}
                  className="w-full px-3 py-2 bg-app-card border border-app-border rounded-lg text-app-text focus:outline-none focus:ring-2 focus:ring-trading-blue/50"
                  disabled={isRestarting || !hasDateConstraints}
                />
                <div className="text-xs text-app-muted">
                  {hasDateConstraints
                    ? 'Leave empty to start from the beginning'
                    : 'Loading date constraints...'}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-app-border bg-app-card/50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-app-muted hover:text-white transition-colors"
            disabled={isRestarting}
          >
            Cancel
          </button>
          <button
            onClick={handleApply}
            disabled={isLoading || isRestarting || (!multiTenant && !selectedFile)}
            className="px-4 py-2 text-sm font-medium bg-trading-blue text-white rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isRestarting && <Loader2 className="animate-spin" size={14} />}
            Apply & Restart
          </button>
        </div>
      </div>
    </div>
  );
};
