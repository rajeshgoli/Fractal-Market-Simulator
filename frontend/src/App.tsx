import { DAGView } from './pages/DAGView'

// ViewMode kept for backward compatibility (DAGView is now the sole view)
export type ViewMode = 'dag'

function App() {
  return <DAGView currentMode="dag" onModeChange={() => {}} />
}

export default App
