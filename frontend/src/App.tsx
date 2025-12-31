import { useState } from 'react';
import { DAGView } from './pages/DAGView';
import { LevelsAtPlayView } from './pages/LevelsAtPlayView';

export type ViewMode = 'dag' | 'levels-at-play';

function App() {
  const [currentView, setCurrentView] = useState<ViewMode>('dag');

  return currentView === 'dag' ? (
    <DAGView onNavigate={setCurrentView} />
  ) : (
    <LevelsAtPlayView onNavigate={setCurrentView} />
  );
}

export default App
