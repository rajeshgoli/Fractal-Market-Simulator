import { useState, useEffect, useCallback } from 'react'
import { Replay } from './pages/Replay'
import { DAGView } from './pages/DAGView'
import { fetchConfig } from './lib/api'

export type ViewMode = 'calibration' | 'dag'

function App() {
  const [mode, setMode] = useState<ViewMode>('calibration')
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    fetchConfig()
      .then(config => {
        setMode(config.mode)
      })
      .catch(err => {
        console.error('Failed to fetch config:', err)
        // Default to calibration mode on error
      })
      .finally(() => {
        setIsLoading(false)
      })
  }, [])

  const handleModeChange = useCallback((newMode: ViewMode) => {
    setMode(newMode)
  }, [])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-app-bg text-app-text">
        <div className="text-center">
          <div className="animate-spin w-8 h-8 border-2 border-trading-blue border-t-transparent rounded-full mx-auto mb-4"></div>
          <p>Loading...</p>
        </div>
      </div>
    )
  }

  return mode === 'dag'
    ? <DAGView currentMode={mode} onModeChange={handleModeChange} />
    : <Replay currentMode={mode} onModeChange={handleModeChange} />
}

export default App
