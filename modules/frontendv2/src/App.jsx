import { BrowserRouter as Router, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Toaster } from 'react-hot-toast'
import Layout from './components/Layout'
import Home from './pages/Home'
import Transcriptions from './pages/Transcriptions'
import TranscriptionDetail from './pages/TranscriptionDetail'
import Meetings from './pages/Meetings'
import MeetingDetail from './pages/MeetingDetail'
import NewTranscription from './pages/NewTranscription'
import MeetingMinutes from './pages/MeetingMinutes'
import Settings from './pages/Settings'
import Login from './pages/Login'
import Guest from './pages/Guest'
import GuestDemo from './pages/GuestDemo'
import Tasks from './pages/Tasks'
import Card, { CardContent, CardHeader, CardTitle } from './components/Card'
import { restoreSession } from './services/sessionService'
import { firebaseAuth } from './services/firebaseAuth'
import { useAuthStore } from './stores/authStore'

function AccountRequired({ children }) {
  const authenticated = useAuthStore((state) => state.isAuthenticated)
  const location = useLocation()
  const context = `?returnTo=${encodeURIComponent(location.pathname + location.search)}`
  if (authenticated) return children
  return <Card><CardHeader><CardTitle>Salve e acompanhe suas reuniões</CardTitle></CardHeader>
    <CardContent><p className="text-gray-600 mb-4">Entre ou crie uma conta para usar este recurso. Sua transcrição temporária continua disponível nesta aba.</p>
      <div className="flex gap-4 text-primary-700"><Link to={`/login${context}`}>Entrar</Link><Link to={`/signup${context}`}>Criar conta</Link><Link to="/new-transcription">Transcrever um arquivo</Link></div>
    </CardContent></Card>
}

function App() {
  const {
    isAuthenticated,
    logout,
  } = useAuthStore()
  const [bootstrapped, setBootstrapped] = useState(false)
  const [sessionError, setSessionError] = useState(false)
  const [sessionRetry, setSessionRetry] = useState(0)

  useEffect(() => {
    let disposed = false
    let unsubscribe
    let observedUid
    const bootstrap = async () => {
      setSessionError(false)
      try {
        await restoreSession()
        if (!disposed) {
          unsubscribe = await firebaseAuth.observe((signedIn, uid) => {
            const accountChanged = observedUid !== undefined && uid !== observedUid
            observedUid = uid
            if (!signedIn && useAuthStore.getState().authProvider === 'firebase') logout()
            if (signedIn && accountChanged && useAuthStore.getState().authProvider === 'firebase') {
              setBootstrapped(false)
              restoreSession().catch(() => {
                if (!disposed) setSessionError(true)
              }).finally(() => {
                if (!disposed) setBootstrapped(true)
              })
            }
          })
          if (disposed) unsubscribe()
        }
      } catch {
        // Keep the SDK session/context on temporary outages, but do not render
        // protected content until the API has verified the internal identity.
        if (!disposed) setSessionError(true)
      } finally {
        if (!disposed) setBootstrapped(true)
      }
    }

    bootstrap()
    return () => { disposed = true; unsubscribe?.() }
  }, [logout, sessionRetry])

  if (sessionError) {
    return <div role="alert" className="mx-auto max-w-md p-6 text-gray-700">
      <p>Não foi possível verificar sua sessão. Verifique sua conexão e tente novamente.</p>
      <button type="button" className="btn-primary mt-4" onClick={() => {
        setBootstrapped(false)
        setSessionRetry((value) => value + 1)
      }}>Tentar novamente</button>
    </div>
  }

  if (!bootstrapped) {
    return <p role="status" className="p-6 text-gray-600">Verificando sessão...</p>
  }

  return (
    <Router>
      <Toaster 
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            background: '#363636',
            color: '#fff',
          },
          success: {
            duration: 3000,
            iconTheme: {
              primary: '#10b981',
              secondary: '#fff',
            },
          },
          error: {
            duration: 5000,
            iconTheme: {
              primary: '#ef4444',
              secondary: '#fff',
            },
          },
        }}
      />
      
      <Routes>
        <Route path="/guest" element={<Navigate to="/new-transcription" replace />} />
        <Route path="/" element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="login" element={<Login />} />
          <Route path="signup" element={<Login signup />} />
          <Route path="transcriptions" element={<AccountRequired><Transcriptions /></AccountRequired>} />
          <Route path="transcriptions/:id" element={<AccountRequired><TranscriptionDetail /></AccountRequired>} />
          <Route path="meetings" element={<AccountRequired><Meetings /></AccountRequired>} />
          <Route path="meetings/:id" element={<AccountRequired><MeetingDetail /></AccountRequired>} />
          <Route path="tasks" element={<AccountRequired><Tasks /></AccountRequired>} />
          <Route path="new-transcription" element={isAuthenticated ? <><Guest /><NewTranscription /></> : <><Guest /><GuestDemo /></>} />
          <Route path="meeting-minutes" element={<AccountRequired><MeetingMinutes /></AccountRequired>} />
          <Route path="settings" element={<AccountRequired><Settings /></AccountRequired>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Router>
  )
}

export default App
