/**
 * Auth hook for managing authentication state.
 *
 * Fetches auth status from the server and provides user info
 * and logout functionality.
 */

import { useState, useEffect, useCallback } from 'react';

export interface User {
  id: string;
  email: string;
}

export interface AuthState {
  authenticated: boolean;
  multiTenant: boolean;
  user: User | null;
  providers?: {
    google: boolean;
    github: boolean;
  };
  loading: boolean;
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    authenticated: false,
    multiTenant: false,
    user: null,
    loading: true,
  });

  const checkAuth = useCallback(async () => {
    try {
      const response = await fetch('/auth/status', {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error('Failed to check auth status');
      }

      const data = await response.json();

      setState({
        authenticated: data.authenticated,
        multiTenant: data.multi_tenant,
        user: data.user,
        providers: data.providers,
        loading: false,
      });
    } catch (error) {
      console.error('Auth check failed:', error);
      setState(prev => ({ ...prev, loading: false }));
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const logout = useCallback(async () => {
    try {
      await fetch('/auth/logout', {
        method: 'POST',
        credentials: 'include',
      });
      // Redirect to landing page
      window.location.href = '/';
    } catch (error) {
      console.error('Logout failed:', error);
    }
  }, []);

  return {
    ...state,
    logout,
    refresh: checkAuth,
  };
}
