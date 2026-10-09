import { useEffect, useState } from 'react'
import { flushSync } from 'react-dom'

import Button from './Button'
import { authService } from '../services/authService'
import { firebaseAuth } from '../services/firebaseAuth'
import { useAuthStore } from '../stores/authStore'

const COOLDOWN_SECONDS = 60

export default function LegacyFirebaseMigration() {
  const user = useAuthStore((state) => state.user)
  const authProvider = useAuthStore((state) => state.authProvider)
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const setFirebaseSession = useAuthStore((state) => state.setFirebaseSession)
  const [config, setConfig] = useState(null)
  const [configLoaded, setConfigLoaded] = useState(false)
  const [target, setTarget] = useState('existing')
  const [email, setEmail] = useState('')
  const [targetPassword, setTargetPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [localPassword, setLocalPassword] = useState('')
  const [stage, setStage] = useState('credentials')
  const [pendingToken, setPendingToken] = useState(null)
  const [cooldown, setCooldown] = useState(0)
  const [loading, setLoading] = useState(false)
  const [restoreChecked, setRestoreChecked] = useState(false)
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

  useEffect(() => {
    if (!cooldown) return undefined
    const timer = window.setTimeout(() => setCooldown((value) => Math.max(0, value - 1)), 1000)
    return () => window.clearTimeout(timer)
  }, [cooldown])

  const firebaseEnabled = configLoaded && config?.firebase_enabled === true && config?.firebase_password_enabled === true
    && typeof config.firebase_project_id === 'string'
    && firebaseAuth.isConfigured()
    && firebaseAuth.projectId() === config.firebase_project_id
  const localAccount = isAuthenticated && authProvider === 'local' && user?.id != null
  const connected = Boolean(user?.firebase_connected || user?.google_connected)

  useEffect(() => {
    const enabled = configLoaded && config?.firebase_enabled === true && config?.firebase_password_enabled === true
      && typeof config.firebase_project_id === 'string'
      && firebaseAuth.isConfigured()
      && firebaseAuth.projectId() === config.firebase_project_id
      && isAuthenticated && authProvider === 'local' && user?.id != null
      && !user?.firebase_connected && !user?.google_connected
    if (!enabled) {
      if (configLoaded) setRestoreChecked(true)
      return undefined
    }
    let active = true
    firebaseAuth.getEmailVerificationState().then((result) => {
      if (active && result) {
        if (result.verified && result.token) {
          setPendingToken(result.token)
          setStage('link')
        } else {
          setStage('verification')
        }
      }
    }).catch(() => {
      if (active) setError('Não foi possível recuperar o acesso Firebase iniciado anteriormente.')
    }).finally(() => {
      if (active) setRestoreChecked(true)
    })
    return () => { active = false }
  }, [configLoaded, config, isAuthenticated, authProvider, user?.id, user?.firebase_connected, user?.google_connected])

  const clearTargetPasswords = () => {
    setTargetPassword('')
    setConfirmPassword('')
  }

  const cleanupFirebase = async () => {
    try {
      await firebaseAuth.signOut()
      return true
    } catch {
      return false
    }
  }

  const displayFailure = (failure) => {
    if (failure?.status === 401) return 'Confirme sua senha USAGI e entre novamente pelo acesso por e-mail para renovar a confirmação. Sua sessão atual continua ativa.'
    if (failure?.status === 409) return 'Este acesso por e-mail não pode ser conectado a esta conta USAGI. Seus dados permanecem na conta atual.'
    if (failure?.status === 503) return 'A conexão está temporariamente indisponível. Sua conta e seus dados não foram alterados.'
    return 'Não foi possível conectar o acesso por e-mail. Sua conta e seus dados permanecem na conta atual.'
  }

  const cleanupFailure = 'Não foi possível encerrar o acesso por e-mail, que ainda pode estar ativo. Saia dele antes de continuar. Sua conta USAGI continua ativa.'

  const acceptVerifiedCredential = (result) => {
    if (!result?.verified || !result.token) {
      setPendingToken(null)
      setStage('verification')
      return
    }
    setPendingToken(result.token)
    setStage('link')
  }

  const handleTargetSubmit = async (event) => {
    event.preventDefault()
    if (target === 'create' && targetPassword !== confirmPassword) {
      flushSync(clearTargetPasswords)
      setError('As senhas da nova conta Firebase não coincidem.')
      return
    }
    const emailValue = email
    const passwordValue = targetPassword
    flushSync(clearTargetPasswords)
    setLoading(true)
    setError('')
    try {
      const result = target === 'create'
        ? await firebaseAuth.createWithEmail(emailValue, passwordValue)
        : await firebaseAuth.signInWithEmail(emailValue, passwordValue)
      if (target === 'create' && !result.verified) setCooldown(COOLDOWN_SECONDS)
      acceptVerifiedCredential(result)
    } catch (failure) {
      const signedOut = await cleanupFirebase()
      const message = failure?.code === 'auth/weak-password'
        ? 'A senha não atende aos requisitos de segurança configurados no Firebase.'
        : 'Não foi possível validar o acesso por e-mail. Confira os dados e tente novamente.'
      setError(signedOut ? message : `${message} ${cleanupFailure}`)
    } finally {
      clearTargetPasswords()
      setLoading(false)
    }
  }

  const handleRefreshVerification = async () => {
    setLoading(true)
    setError('')
    try {
      acceptVerifiedCredential(await firebaseAuth.refreshVerification())
    } catch {
      setError('Não foi possível consultar a verificação do e-mail. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  const handleResendVerification = async () => {
    setLoading(true)
    setError('')
    try {
      await firebaseAuth.resendVerification()
      setCooldown(COOLDOWN_SECONDS)
    } catch {
      setError('Não foi possível reenviar o e-mail de verificação. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  const handleLink = async (event) => {
    event.preventDefault()
    const localUser = useAuthStore.getState()
    if (localUser.authProvider !== 'local' || localUser.user?.id !== user.id || !localUser.isAuthenticated) {
      setError('Sua sessão mudou. Recarregue a página e tente novamente.')
      return
    }
    const localPasswordValue = localPassword
    flushSync(() => setLocalPassword(''))
    setLoading(true)
    setError('')
    try {
      const result = await authService.linkGoogle(pendingToken, localPasswordValue)
      const current = useAuthStore.getState()
      if (current.authProvider !== 'local' || current.user?.id !== user.id
          || result.user?.id !== user.id) {
        throw Object.assign(new Error('Identity mismatch'), { status: 409 })
      }
      setFirebaseSession(result.user)
      setStage('complete')
    } catch (failure) {
      const signedOut = await cleanupFirebase()
      setPendingToken(null)
      setStage('credentials')
      const message = displayFailure(failure)
      setError(signedOut ? message : `${message} ${cleanupFailure}`)
    } finally {
      setLocalPassword('')
      setLoading(false)
    }
  }

  const handleCancel = async () => {
    setLoading(true)
    const signedOut = await cleanupFirebase()
    clearTargetPasswords()
    setLocalPassword('')
    setPendingToken(null)
    setEmail('')
    setStage('credentials')
    setCooldown(0)
    setError(signedOut ? '' : cleanupFailure)
    setLoading(false)
  }

  if (!localAccount) return null

  if (connected || stage === 'complete') {
    return <p role="status" className="text-sm text-gray-700">
      Acesso conectado à sua conta USAGI. Seus dados permanecem nesta conta; use o método conectado para entrar.
    </p>
  }

  if (!firebaseEnabled) return null

  return (
    <section aria-labelledby="firebase-migration-heading" className="space-y-3">
      <div>
        <h2 id="firebase-migration-heading" className="text-base font-semibold text-gray-900">Conectar acesso por e-mail</h2>
        <p className="mt-1 text-sm text-gray-600">
          Conecte um método Firebase à sua conta USAGI atual. Suas transcrições e demais dados continuam na mesma conta.
        </p>
      </div>

      {!restoreChecked && <p role="status" className="text-sm text-gray-600">Verificando um acesso Firebase iniciado anteriormente…</p>}

      {restoreChecked && stage === 'credentials' && <>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-gray-700">Qual acesso por e-mail deseja conectar?</legend>
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="radio" name="firebase-target" value="existing" checked={target === 'existing'}
              onChange={() => setTarget('existing')} />
            Já uso e-mail e senha
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="radio" name="firebase-target" value="create" checked={target === 'create'}
              onChange={() => setTarget('create')} />
            Criar acesso por e-mail
          </label>
        </fieldset>
        <form onSubmit={handleTargetSubmit} className="space-y-3">
          <label htmlFor="migration-email" className="block text-sm font-medium text-gray-700">E-mail do acesso
            <input id="migration-email" type="email" autoComplete="email" required maxLength={255}
              value={email} onChange={(event) => setEmail(event.target.value)} className="input mt-2" />
          </label>
          <label htmlFor="migration-password" className="block text-sm font-medium text-gray-700">Senha do acesso por e-mail
            <input id="migration-password" type="password" autoComplete={target === 'create' ? 'new-password' : 'current-password'}
              required minLength={target === 'create' ? 12 : undefined} value={targetPassword}
              onChange={(event) => setTargetPassword(event.target.value)} className="input mt-2" />
          </label>
          {target === 'create' && <label htmlFor="migration-confirm-password" className="block text-sm font-medium text-gray-700">Confirmar senha
            <input id="migration-confirm-password" type="password" autoComplete="new-password" required
              minLength={12} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className="input mt-2" />
          </label>}
          {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
          <Button type="submit" loading={loading}>
            {target === 'create' ? 'Criar acesso por e-mail' : 'Continuar'}
          </Button>
        </form>
      </>}

      {restoreChecked && stage === 'verification' && <div className="space-y-3">
        <p role="status" className="text-sm text-gray-700">Confirme o endereço pelo link enviado ao seu e-mail. Depois, atualize a confirmação para continuar.</p>
        {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" loading={loading} onClick={handleRefreshVerification}>Já confirmei meu e-mail</Button>
          <Button type="button" variant="secondary" loading={loading} disabled={loading || cooldown > 0} onClick={handleResendVerification}>
            {cooldown > 0 ? `Reenviar e-mail (${cooldown}s)` : 'Reenviar e-mail de verificação'}
          </Button>
        </div>
        <Button type="button" variant="ghost" disabled={loading} onClick={handleCancel}>Cancelar</Button>
      </div>}

      {restoreChecked && stage === 'link' && <form onSubmit={handleLink} className="space-y-3">
        <p className="text-sm text-gray-700">Confirme novamente sua senha USAGI para conectar este acesso à conta atual.</p>
        <label htmlFor="migration-local-password" className="block text-sm font-medium text-gray-700">Senha USAGI atual
          <input id="migration-local-password" type="password" autoComplete="current-password" required
            value={localPassword} onChange={(event) => setLocalPassword(event.target.value)} className="input mt-2" />
        </label>
        {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" loading={loading}>Conectar à conta atual</Button>
          <Button type="button" variant="ghost" disabled={loading} onClick={handleCancel}>Cancelar</Button>
        </div>
      </form>}
    </section>
  )
}
