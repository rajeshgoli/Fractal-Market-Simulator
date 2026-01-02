import { DAGView } from './pages/DAGView';
import { LevelsAtPlayView } from './pages/LevelsAtPlayView';
import { useChartPreferences } from './hooks/useChartPreferences';

export type ViewMode = 'dag' | 'levels-at-play';

function App() {
  const { currentView, setCurrentView } = useChartPreferences();

  return currentView === 'dag' ? (
    <DAGView onNavigate={setCurrentView} />
  ) : (
    <LevelsAtPlayView onNavigate={setCurrentView} />
  );
}

export default App
