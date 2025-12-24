import { useState, useEffect, useCallback, useRef } from 'react';

const STORAGE_KEY = 'session-settings';

/**
 * Session settings persisted to localStorage.
 *
 * These settings control which data file and starting position
 * are used when the app starts.
 */
export interface SessionSettings {
  dataFile: string | null;    // Path to selected CSV
  startDate: string | null;   // ISO date string (YYYY-MM-DD)
}

const DEFAULT_SETTINGS: SessionSettings = {
  dataFile: null,
  startDate: null,
};

function loadSettings(): SessionSettings {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return {
        ...DEFAULT_SETTINGS,
        ...parsed,
      };
    }
  } catch (e) {
    console.warn('Failed to load session settings:', e);
  }
  return DEFAULT_SETTINGS;
}

function saveSettings(settings: SessionSettings): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch (e) {
    console.warn('Failed to save session settings:', e);
  }
}

export interface UseSessionSettingsReturn {
  // Current settings
  dataFile: string | null;
  startDate: string | null;

  // Whether settings have been loaded from storage
  isLoaded: boolean;

  // Whether there's a saved session to restore
  hasSavedSession: boolean;

  // Update functions
  setDataFile: (value: string | null) => void;
  setStartDate: (value: string | null) => void;

  // Save current session settings (call after successful session load)
  saveSession: (dataFile: string, startDate: string | null) => void;

  // Clear saved session
  clearSession: () => void;
}

export function useSessionSettings(): UseSessionSettingsReturn {
  // Load initial state from localStorage
  const [settings, setSettings] = useState<SessionSettings>(() => loadSettings());
  const [isLoaded, setIsLoaded] = useState(false);

  // Track if we've initialized (to avoid saving on initial load)
  const isInitializedRef = useRef(false);

  // Mark as loaded after first render
  useEffect(() => {
    setIsLoaded(true);
  }, []);

  // Save to localStorage whenever settings change (after initial load)
  useEffect(() => {
    if (isInitializedRef.current) {
      saveSettings(settings);
    } else {
      isInitializedRef.current = true;
    }
  }, [settings]);

  const setDataFile = useCallback((value: string | null) => {
    setSettings(prev => ({ ...prev, dataFile: value }));
  }, []);

  const setStartDate = useCallback((value: string | null) => {
    setSettings(prev => ({ ...prev, startDate: value }));
  }, []);

  const saveSession = useCallback((dataFile: string, startDate: string | null) => {
    setSettings({ dataFile, startDate });
  }, []);

  const clearSession = useCallback(() => {
    setSettings(DEFAULT_SETTINGS);
  }, []);

  const hasSavedSession = settings.dataFile !== null;

  return {
    dataFile: settings.dataFile,
    startDate: settings.startDate,
    isLoaded,
    hasSavedSession,
    setDataFile,
    setStartDate,
    saveSession,
    clearSession,
  };
}
