import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { DAGView } from './pages/DAGView';
import { LevelsAtPlayView } from './pages/LevelsAtPlayView';
import { LandingPage } from './pages/LandingPage';
import { DevelopersPage } from './pages/DevelopersPage';
import { TradersPage } from './pages/TradersPage';
import { StoryPage } from './pages/StoryPage';
import { PrivacyPage } from './pages/PrivacyPage';
import { TermsPage } from './pages/TermsPage';
import { useChartPreferences } from './hooks/useChartPreferences';
import { useAuth } from './hooks/useAuth';

export type ViewMode = 'dag' | 'levels-at-play';

function AppViews() {
  const { currentView, setCurrentView } = useChartPreferences();

  return currentView === 'dag' ? (
    <DAGView onNavigate={setCurrentView} />
  ) : (
    <LevelsAtPlayView onNavigate={setCurrentView} />
  );
}

function HomePage() {
  const { authenticated, loading, multiTenant } = useAuth();

  // Show nothing while checking auth
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-app-bg">
        <div className="text-app-muted">Loading...</div>
      </div>
    );
  }

  // In multi-tenant mode: show app if authenticated, landing if not
  // In single-tenant mode: always show landing at "/" (use /app to access app)
  if (multiTenant) {
    return authenticated ? <AppViews /> : <LandingPage />;
  } else {
    return <LandingPage />;
  }
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/app" element={<AppViews />} />
        <Route path="/developers" element={<DevelopersPage />} />
        <Route path="/traders" element={<TradersPage />} />
        <Route path="/story" element={<StoryPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
