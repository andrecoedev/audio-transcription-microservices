import { useEffect, useState } from 'react'
import { authService } from '../services/authService'
import { firebaseAuth } from '../services/firebaseAuth'
import Button from './Button'

const GENERIC_RESET_MESSAGE = 'Se este e-mail puder redefinir uma senha, enviaremos as instruções.'

export default function FirebaseAccountMethods({ account, onUpdated }) {
  const [config, setConfig] = useState(null)
  const [methods, setMethods] = useState([])
  const [configReady, setConfigReady] = useState(false)
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    Promise.all([authService.getConfig(), firebaseAuth.getAuthMethods()])
      .then(([result, ids]) => {
        if (!active) return
        setConfig(result)
        setMethods(Array.isArray(ids) ? ids : [])
      })
      .catch(() => {
        if (!active) return
        setConfig(null)
        setMethods([])
      })
      .finally(() => { if (active) setConfigReady(true) })
    return () => { active = false }
  }, [account.id])

  const firebaseEnabled = configReady && config?.firebase_enabled === true
    && typeof config.firebase_project_id === 'string'
    && firebaseAuth.isConfigured()
    && firebaseAuth.projectId() === config.firebase_project_id
  const passwordEnabled = firebaseEnabled && config?.firebase_password_enabled === true
  const hasPassword = methods.includes('password')
  const hasGoogle = methods.includes('google.com')
  const accessEmail = account.firebase_email

  const run = async (operation, successMessage) => {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await operation()
      setMessage(successMessage)
      if (onUpdated) await onUpdated()
      setMethods(await firebaseAuth.getAuthMethods())
    } catch {
      setError('Não foi possível concluir esta alteração. Confira os dados e tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  const handleReset = () => run(
    () => firebaseAuth.resetPassword(accessEmail),
    GENERIC_RESET_MESSAGE,
  )

  const handleLinkPassword = async (event) => {
    event.preventDefault()
    const newPassword = password
    const confirmPassword = confirmation
    setPassword('')
    setConfirmation('')
    setError('')
    setMessage('')
    if (newPassword.length < 12) {
      setError('A senha deve ter pelo menos 12 caracteres.')
      return
    }
    if (newPassword !== confirmPassword) {
      setError('As senhas não correspondem.')
      return
    }
    setBusy(true)
    try {
      const status = await firebaseAuth.validatePassword(newPassword)
      if (!status?.isValid) {
        setError('Escolha uma senha que atenda aos requisitos de segurança.')
        return
      }
      await firebaseAuth.linkPassword(accessEmail, newPassword)
      setMessage('Senha conectada a esta conta.')
      if (onUpdated) await onUpdated()
      setMethods(await firebaseAuth.getAuthMethods())
    } catch {
      setError('Não foi possível conectar a senha. Tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  const handleLinkGoogle = async (event) => {
    event.preventDefault()
    const reauthPassword = currentPassword
    setCurrentPassword('')
    await run(async () => {
      await firebaseAuth.reauthenticatePassword(reauthPassword)
      const result = await firebaseAuth.linkGoogle()
      if (!result?.methods?.includes('google.com')) throw new Error('Google was not linked.')
      await firebaseAuth.getToken(true)
    }, 'Google conectado a esta conta.')
  }

  if (!configReady) return null
  if (!firebaseEnabled) return null

  return <section className="space-y-4" aria-label="Métodos de acesso">
    <div className="space-y-1 text-sm text-gray-700">
      <p>Métodos de acesso conectados:</p>
      {hasGoogle && <p>Google</p>}
      {hasPassword && <p>E-mail e senha</p>}
      {!hasGoogle && !hasPassword && <p>Nenhum método confirmado pelo Firebase.</p>}
    </div>

    {passwordEnabled && accessEmail && <div className="space-y-3">
      {hasPassword
        ? <Button type="button" variant="outline" loading={busy} onClick={handleReset}>Redefinir senha</Button>
        : <form onSubmit={handleLinkPassword} className="space-y-3">
          <h3 className="text-sm font-semibold text-gray-900">Adicionar senha a esta conta</h3>
          <p className="text-sm text-gray-600">Você poderá entrar com Google ou senha, sem mudar de conta.</p>
          <label className="block text-sm font-medium text-gray-700" htmlFor="firebase-new-password">Nova senha
            <input id="firebase-new-password" type="password" autoComplete="new-password" minLength={12} required
              value={password} onChange={event => setPassword(event.target.value)} className="input mt-2" />
          </label>
          <label className="block text-sm font-medium text-gray-700" htmlFor="firebase-confirm-password">Confirmar nova senha
            <input id="firebase-confirm-password" type="password" autoComplete="new-password" minLength={12} required
              value={confirmation} onChange={event => setConfirmation(event.target.value)} className="input mt-2" />
          </label>
          <Button type="submit" loading={busy}>Adicionar senha</Button>
        </form>}
    </div>}

    {!hasGoogle && hasPassword && <form onSubmit={handleLinkGoogle} className="space-y-3">
      <h3 className="text-sm font-semibold text-gray-900">Conectar Google</h3>
      <p className="text-sm text-gray-600">Confirme sua senha para conectar Google à conta atual.</p>
      <label className="block text-sm font-medium text-gray-700" htmlFor="firebase-current-password">Senha atual
        <input id="firebase-current-password" type="password" autoComplete="current-password" required
          value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} className="input mt-2" />
      </label>
      <Button type="submit" loading={busy}>Conectar Google</Button>
    </form>}

    {message && <p role="status" className="text-sm text-gray-700">{message}</p>}
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
  </section>
}
