import { useEffect, useState } from 'react'

import Button from './Button'
import { authService } from '../services/authService'
import { firebaseAuth } from '../services/firebaseAuth'
import { useAuthStore } from '../stores/authStore'

export default function GoogleAccountLink() {
  const user = useAuthStore((state) => state.user)
  const authProvider = useAuthStore((state) => state.authProvider)
  const setFirebaseSession = useAuthStore((state) => state.setFirebaseSession)
  const [config, setConfig] = useState(null)
  const [configLoaded, setConfigLoaded] = useState(false)
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    authService.getConfig().then((result) => {
      if (active) setConfig(result)
    }).catch(() => {
      if (active) setConfig(null)
    }).finally(() => {
      if (active) setConfigLoaded(true)
    })
    return () => { active = false }
  }, [])

  const connected = Boolean(user?.google_connected) || authProvider === 'firebase'
  const firebaseEnabled = configLoaded && config?.firebase_enabled === true
    && typeof config.firebase_project_id === 'string'
    && firebaseAuth.isConfigured()
    && firebaseAuth.projectId() === config.firebase_project_id

  const handleLink = async (event) => {
    event.preventDefault()
    const reauthPassword = password
    setPassword('')
    setLoading(true)
    setError('')
    try {
      const idToken = await firebaseAuth.signInWithGoogle()
      const result = await authService.linkGoogle(idToken, reauthPassword)
      setFirebaseSession(result.user)
    } catch {
      let cleanupFailed = false
      try {
        await firebaseAuth.signOut()
      } catch {
        cleanupFailed = true
      }
      setError(cleanupFailed
        ? 'Não foi possível conectar o Google nem encerrar a sessão Google. Tente novamente.'
        : 'Não foi possível conectar o Google. Confirme sua senha e tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  if (connected) {
    return <p role="status" className="text-sm text-gray-700">Google conectado</p>
  }

  if (!firebaseEnabled) return null

  return (
    <section aria-labelledby="google-link-heading" className="space-y-3">
      <div>
        <h2 id="google-link-heading" className="text-base font-semibold text-gray-900">Conectar conta Google</h2>
        <p className="mt-1 text-sm text-gray-600">Confirme sua senha USAGI para conectar sua conta Google existente.</p>
      </div>
      <form onSubmit={handleLink} className="space-y-3">
        <label htmlFor="google-link-password" className="block text-sm font-medium text-gray-700">Senha USAGI
          <input id="google-link-password" type="password" autoComplete="current-password" required
            value={password} onChange={(event) => setPassword(event.target.value)} className="input mt-2" />
        </label>
        {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
        <Button type="submit" loading={loading} disabled={!password}>Conectar Google</Button>
      </form>
    </section>
  )
}
