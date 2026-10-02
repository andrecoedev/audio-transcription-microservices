import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Toaster } from 'react-hot-toast'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Transcriptions from './pages/Transcriptions'
import TranscriptionDetail from './pages/TranscriptionDetail'
import Meetings from './pages/Meetings'
import MeetingDetail from './pages/MeetingDetail'
import NewTranscription from './pages/NewTranscription'
import MeetingMinutes from './pages/MeetingMinutes'
import Settings from './pages/Settings'
import Login from './pages/Login'
import { authService } from './services/authService'
import { useAuthStore } from './stores/authStore'

function App() {
  const {
    isAuthenticated,
    setSession,
    logout,
  } = useAuthStore()
  const [bootstrapped, setBootstrapped] = useState(false)

  useEffect(() => {
    const bootstrap = async () => {
      let verified = false
      try {
        await authService.getConfig()

        const token = localStorage.getItem('token')
        if (token) {
          const me = await authService.me()
          if (me.authenticated) {
            setSession(me.user, token)
            verified = true
            setBootstrapped(true)
            return
          }
        }

      } catch {
        // Fail closed: API unavailability never creates an anonymous session.
      } finally {
        if (!verified) {
          logout()
        }
        setBootstrapped(true)
      }
    }

    bootstrap()
  }, [setSession, logout])

  if (!bootstrapped) {
    return null
  }

  const requiresLogin = !isAuthenticated

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
        <Route path="/login" element={<Login />} />

        {requiresLogin ? (
          <Route path="*" element={<Navigate to="/login" replace />} />
        ) : (
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="transcriptions" element={<Transcriptions />} />
          <Route path="transcriptions/:id" element={<TranscriptionDetail />} />
          <Route path="meetings" element={<Meetings />} />
          <Route path="meetings/:id" element={<MeetingDetail />} />
          <Route path="new-transcription" element={<NewTranscription />} />
          <Route path="meeting-minutes" element={<MeetingMinutes />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
        )}
      </Routes>
    </Router>
  )
}

export default App
