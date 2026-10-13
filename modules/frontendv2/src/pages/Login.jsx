import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Lock, User } from 'lucide-react'

import Button from '../components/Button'
import Card, { CardContent } from '../components/Card'
import { authService } from '../services/authService'
import { firebaseAuth } from '../services/firebaseAuth'
import { authDestination, authSwitchQuery } from '../services/authReturn'
import { useAuthStore } from '../stores/authStore'
import { usePasswordPolicy } from '../hooks/usePasswordPolicy'
import PasswordChecklist from '../components/PasswordChecklist'

const VERIFICATION_RESEND_SECONDS = 60

function firebaseErrorMessage(error, action) {
  const messages = {
    'auth/invalid-credential': 'E-mail ou senha inválidos.',
    'auth/wrong-password': 'E-mail ou senha inválidos.',
    'auth/user-not-found': 'E-mail ou senha inválidos.',
    'auth/invalid-email': 'Informe um e-mail válido.',
    'auth/email-already-in-use': 'Este e-mail já está em uso.',
    'auth/weak-password': 'Confira os requisitos da senha indicados abaixo.',
    'auth/too-many-requests': 'Muitas tentativas. Aguarde e tente novamente.',
    'auth/network-request-failed': 'Não foi possível conectar. Verifique sua conexão e tente novamente.',
    'auth/account-changed': 'A conta mudou. Entre novamente para continuar.',
  }
  if (error?.status === 409) {
    return 'Seu acesso precisa ser atualizado. Confirme seu acesso antigo para manter seus dados na mesma conta.'
  }
  return messages[error?.code] || (action === 'recover'
    ? 'Não foi possível iniciar a recuperação agora. Tente novamente.'
    : 'Não foi possível concluir a operação. Confira os dados e tente novamente.')
}

export default function Login({ signup = false }) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { setSession, setFirebaseSession } = useAuthStore()
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [needsAccessUpdate, setNeedsAccessUpdate] = useState(false)
  const [notice, setNotice] = useState('')
  const [config, setConfig] = useState(null)
  const [configLoaded, setConfigLoaded] = useState(false)
  const [mode, setMode] = useState('firebase')
  const [verificationPending, setVerificationPending] = useState(false)
  const [resendAvailableAt, setResendAvailableAt] = useState(0)
  const [secondsUntilResend, setSecondsUntilResend] = useState(0)

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
    if (!resendAvailableAt) return undefined
    const update = () => setSecondsUntilResend(Math.max(0, Math.ceil((resendAvailableAt - Date.now()) / 1000)))
    update()
    const timer = window.setInterval(update, 1000)
    return () => window.clearInterval(timer)
  }, [resendAvailableAt])

  const googleEnabled = config?.firebase_enabled === true
    && typeof config.firebase_project_id === 'string'
    && firebaseAuth.isConfigured()
    && firebaseAuth.projectId() === config.firebase_project_id
  const emailAuthEnabled = googleEnabled && config?.firebase_password_enabled === true
  const legacyMode = !signup && searchParams.get('legacy') === '1'
  const firebaseMode = !legacyMode
    ? (mode === 'recover' ? 'recover' : signup ? 'firebase-signup' : 'firebase')
    : null
  const isFirebaseSignup = firebaseMode === 'firebase-signup'
  const isRecovery = firebaseMode === 'recover'
  const localMode = legacyMode
  const guestQuery = authSwitchQuery(searchParams)
  const policy = usePasswordPolicy(password, isFirebaseSignup && emailAuthEnabled)
  const passwordsMatch = Boolean(password && confirmPassword && password === confirmPassword)

  useEffect(() => {
    if (!configLoaded || !emailAuthEnabled || isAuthenticated || verificationPending
        || typeof firebaseAuth.getEmailVerificationState !== 'function') return undefined
    let active = true
    firebaseAuth.getEmailVerificationState().then((state) => {
      if (active && state && !state.verified) {
        setVerificationPending(true)
        setResendAvailableAt(Date.now() + VERIFICATION_RESEND_SECONDS * 1000)
      }
    }).catch(() => {
      // A stale or unavailable Firebase session should not prevent ordinary login.
    })
    return () => { active = false }
  }, [configLoaded, emailAuthEnabled, isAuthenticated, verificationPending])

  const clearFeedback = () => {
    setError('')
    setNeedsAccessUpdate(false)
    setNotice('')
  }

  const goToDestination = () => navigate(authDestination(searchParams), { replace: true })

  const completeFirebaseLogin = async (token) => {
    if (!token) throw new Error('Missing Firebase token')
    const result = await authService.firebaseLogin(token)
    setFirebaseSession(result.user)
    goToDestination()
  }

  const handleLocalSubmit = async (event) => {
    event.preventDefault()
    if (!username || !password) {
      setPassword('')
      setError('Informe usuário e senha.')
      return
    }
    const submittedPassword = password
    setLoading(true)
    setPassword('')
    setConfirmPassword('')
    clearFeedback()
    try {
      const result = await authService.login(username, submittedPassword)
      setSession(result.user, result.access_token)
      goToDestination()
    } catch {
      setError('Não foi possível entrar. Confira seu usuário e senha e tente novamente.')
    } finally {
      setPassword('')
      setConfirmPassword('')
      setLoading(false)
    }
  }

  const handleFirebaseSubmit = async (event) => {
    event.preventDefault()
    clearFeedback()
    if (!email || !password) {
      setError('Informe seu e-mail e sua senha.')
      setPassword('')
      return
    }
    if (!emailAuthEnabled) {
      setError('O acesso por e-mail está indisponível. Tente novamente mais tarde.')
      return
    }
    if (isFirebaseSignup && (!policy.valid || !passwordsMatch)) {
      setError('Confira os requisitos da senha e a confirmação antes de continuar.')
      return
    }

    const submittedPassword = password
    setLoading(true)
    setPassword('')
    setConfirmPassword('')
    try {
      const result = isFirebaseSignup
        ? await firebaseAuth.createWithEmail(email.trim(), submittedPassword)
        : await firebaseAuth.signInWithEmail(email.trim(), submittedPassword)
      if (!result.verified) {
        setVerificationPending(true)
        setResendAvailableAt(Date.now() + VERIFICATION_RESEND_SECONDS * 1000)
        setNotice(isFirebaseSignup
          ? 'Enviamos um link de confirmação para seu e-mail. Confirme o endereço para continuar.'
          : 'Confirme o endereço pelo link de verificação. Se necessário, solicite outro envio.')
        return
      }
      await completeFirebaseLogin(result.token)
    } catch (failure) {
      setNeedsAccessUpdate(failure?.status === 409)
      try {
        await firebaseAuth.signOut()
        setError(firebaseErrorMessage(failure))
      } catch {
        setError('Não foi possível concluir a autenticação nem encerrar a sessão pendente. Tente novamente ou cancele a sessão antes de entrar.')
      }
    } finally {
      setPassword('')
      setConfirmPassword('')
      setLoading(false)
    }
  }

  const handleRefreshVerification = async () => {
    setLoading(true)
    clearFeedback()
    try {
      const result = await firebaseAuth.refreshVerification()
      if (!result.verified) {
        setNotice('Ainda não encontramos a confirmação. Abra o link enviado ao seu e-mail e tente novamente.')
        return
      }
      await completeFirebaseLogin(result.token)
      setVerificationPending(false)
    } catch (failure) {
      setNeedsAccessUpdate(failure?.status === 409)
      try {
        await firebaseAuth.signOut()
        setVerificationPending(false)
        setError(firebaseErrorMessage(failure))
      } catch {
        setError('Não foi possível atualizar a confirmação nem encerrar a sessão pendente. Tente novamente ou cancele a sessão antes de entrar.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleResendVerification = async () => {
    setLoading(true)
    clearFeedback()
    try {
      await firebaseAuth.resendVerification()
      setResendAvailableAt(Date.now() + VERIFICATION_RESEND_SECONDS * 1000)
      setNotice('Enviamos outro link de confirmação. Confira sua caixa de entrada.')
    } catch (failure) {
      setError(firebaseErrorMessage(failure))
    } finally {
      setLoading(false)
    }
  }

  const cancelVerification = async () => {
    setLoading(true)
    try { await firebaseAuth.signOut() } catch {
      setError('Não foi possível encerrar a sessão pendente. Tente novamente.')
      setLoading(false)
      return
    }
    setVerificationPending(false)
    setNotice('')
    setMode('firebase')
    setLoading(false)
  }

  const handleRecovery = async (event) => {
    event.preventDefault()
    if (!emailAuthEnabled) return
    setLoading(true)
    clearFeedback()
    try {
      await firebaseAuth.resetPassword(email.trim())
      setNotice('Se houver uma conta para este e-mail, enviaremos instruções para redefinir sua senha.')
    } catch (failure) {
      setError(firebaseErrorMessage(failure, 'recover'))
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleLogin = async () => {
    setLoading(true)
    clearFeedback()
    try {
      const idToken = await firebaseAuth.signInWithGoogle()
      const result = await authService.firebaseLogin(idToken)
      setFirebaseSession(result.user)
      goToDestination()
    } catch (failure) {
      setNeedsAccessUpdate(failure?.status === 409)
      setError(failure.status === 409
        ? 'Seu acesso precisa ser atualizado. Confirme seu acesso antigo para manter seus dados na mesma conta.'
        : 'Não foi possível entrar com Google. Tente novamente.')
      try { await firebaseAuth.signOut() } catch {
        setError('Não foi possível concluir nem encerrar a sessão Google. Tente novamente.')
      }
    } finally {
      setLoading(false)
    }
  }

  const selectFirebaseLogin = () => {
    clearFeedback()
    setMode('firebase')
    navigate(`/login${guestQuery}`, { replace: true })
  }

  const title = verificationPending
    ? 'Confirme seu e-mail'
    : isRecovery
      ? 'Recuperar senha'
      : isFirebaseSignup || (signup && localMode)
        ? 'Crie sua conta'
        : legacyMode ? 'Atualizar método de acesso' : 'Salve seu trabalho'

  return (
    <section aria-labelledby="auth-heading" className="mx-auto flex w-full max-w-md flex-col justify-center py-8">
      <div className="mb-5 text-center">
        <span className="rounded-full bg-primary-50 px-3 py-1.5 text-xs font-semibold text-primary-800">Salve seu progresso</span>
        <h1 id="auth-heading" className="mt-4 text-3xl font-semibold text-gray-900">{title}</h1>
        <p className="mx-auto mt-2 max-w-sm text-gray-600">
          {verificationPending
            ? email ? `Confirme ${email} pelo link enviado para acessar sua conta.` : 'Confirme seu endereço pelo link enviado para acessar sua conta.'
            : isFirebaseSignup || (signup && localMode)
              ? 'Crie uma conta para guardar transcrições e acessar seu histórico.'
              : isRecovery
                ? 'Informe seu e-mail e enviaremos instruções para redefinir sua senha.'
                : 'Entre para salvar esta transcrição, acessar o histórico e continuar em outro dispositivo.'}
        </p>
      </div>

      <Card className="p-7">
        <CardContent>
          {verificationPending ? (
            <div className="space-y-4">
              {notice && <p role="status" className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">{notice}</p>}
              <Button type="button" className="w-full" loading={loading} disabled={loading} onClick={handleRefreshVerification}>
                Já confirmei meu e-mail
              </Button>
              <Button type="button" variant="secondary" className="w-full" loading={loading} disabled={loading || secondsUntilResend > 0} onClick={handleResendVerification}>
                {secondsUntilResend > 0 ? `Enviar outro link em ${secondsUntilResend}s` : 'Reenviar link de confirmação'}
              </Button>
              <button type="button" className="w-full text-sm text-gray-600 hover:text-gray-900" disabled={loading} onClick={cancelVerification}>
                Cancelar e voltar
              </button>
            </div>
          ) : isRecovery ? (
            <form onSubmit={handleRecovery} className="space-y-4">
              <label htmlFor="recovery-email" className="block text-sm font-medium text-gray-700">E-mail
                <input id="recovery-email" type="email" autoComplete="email" className="input mt-2" required maxLength={255}
                  value={email} onChange={(event) => setEmail(event.target.value)} />
              </label>
              <Button type="submit" className="w-full" loading={loading}>Enviar instruções</Button>
              <button type="button" className="w-full text-sm text-primary-800" disabled={loading} onClick={() => { setMode('firebase'); clearFeedback() }}>
                Voltar ao login
              </button>
            </form>
          ) : firebaseMode && firebaseMode !== 'local' ? (
            <>
              {googleEnabled && <div className="mb-4">
                <Button type="button" className="w-full" loading={loading} disabled={loading} onClick={handleGoogleLogin}>Continuar com Google</Button>
                {!isFirebaseSignup && <p className="my-3 text-center text-sm text-gray-500">ou use seu e-mail e senha</p>}
              </div>}
              <form onSubmit={handleFirebaseSubmit} className="space-y-4">
                <label htmlFor="firebase-email" className="block text-sm font-medium text-gray-700">E-mail
                  <input id="firebase-email" type="email" autoComplete="email" className="input mt-2" required maxLength={255}
                    value={email} onChange={(event) => setEmail(event.target.value)} />
                </label>
                <label htmlFor="firebase-password" className="block text-sm font-medium text-gray-700">Senha
                  <span className="relative mt-2 block">
                    <Lock aria-hidden="true" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
                    <input id="firebase-password" autoComplete={isFirebaseSignup ? 'new-password' : 'current-password'} type="password"
                      value={password} onChange={(event) => setPassword(event.target.value)} className="input pl-10" required
                      aria-describedby={isFirebaseSignup ? 'signup-password-policy' : undefined} />
                  </span>
                </label>
                {isFirebaseSignup && <>
                  <label htmlFor="firebase-password-confirm" className="block text-sm font-medium text-gray-700">Confirmar senha
                    <span className="relative mt-2 block">
                      <Lock aria-hidden="true" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
                      <input id="firebase-password-confirm" autoComplete="new-password" type="password" className="input pl-10" required aria-describedby="signup-password-policy"
                        value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
                    </span>
                  </label>
                  <PasswordChecklist status={policy.status} password={password} confirmation={confirmPassword} id="signup-password-policy" />
                  {policy.loading && <p role="status" className="text-xs text-gray-500">Verificando requisitos…</p>}
                  {policy.error && <div role="alert" className="text-sm text-red-800">
                    Não foi possível consultar os requisitos da senha. Verifique sua conexão e tente novamente.
                    <button type="button" className="ml-2 underline" onClick={policy.retry}>Tentar novamente</button>
                  </div>}
                </>}
                <Button type="submit" className="w-full" loading={loading}
                  disabled={!emailAuthEnabled || (isFirebaseSignup && (!policy.valid || !passwordsMatch))}>{isFirebaseSignup ? 'Criar conta' : 'Entrar'}</Button>
              </form>
              {!isFirebaseSignup && <div className="mt-4 flex flex-col items-center gap-3 text-sm">
                <button type="button" className="text-primary-800 hover:text-primary-900" disabled={loading || !emailAuthEnabled} onClick={() => { setMode('recover'); clearFeedback() }}>
                  Esqueci minha senha
                </button>
              </div>}
            </>
          ) : (
            <>
              <p className="mb-4 text-sm text-gray-600">Confirme seu acesso antigo. Em Minha conta, conecte Google ou e-mail para continuar usando a mesma conta e seus dados.</p>
              <form onSubmit={handleLocalSubmit} className="space-y-4">
                <label htmlFor="login-username" className="block text-sm font-medium text-gray-700">Usuário
                  <span className="relative mt-2 block">
                    <User aria-hidden="true" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
                    <input id="login-username" autoComplete="username" type="text" value={username}
                      onChange={(event) => setUsername(event.target.value)} className="input pl-10" required />
                  </span>
                </label>
                <label htmlFor="login-password" className="block text-sm font-medium text-gray-700">Senha
                  <span className="relative mt-2 block">
                    <Lock aria-hidden="true" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
                    <input id="login-password" autoComplete="current-password" type="password"
                      value={password} onChange={(event) => setPassword(event.target.value)} className="input pl-10" placeholder="********"
                      required />
                  </span>
                </label>
                <Button type="submit" className="w-full" loading={loading}>Entrar</Button>
              </form>
              {emailAuthEnabled && <button type="button" className="mt-4 w-full text-sm text-primary-800" disabled={loading} onClick={selectFirebaseLogin}>
                Voltar ao acesso por e-mail
              </button>}
            </>
          )}

          {error && <p role="alert" className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
          {needsAccessUpdate && <Link className="mt-3 block text-sm text-primary-800 underline" to={`/login?legacy=1${guestQuery ? `&${guestQuery.slice(1)}` : '&returnTo=%2Fsettings'}`}>Atualizar método de acesso</Link>}
          {notice && !verificationPending && <p role="status" className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">{notice}</p>}
          <div className="mt-5 flex flex-col items-center gap-3 text-sm text-primary-800">
            {!verificationPending && !isRecovery && !localMode && <Link to={`${signup ? '/login' : '/signup'}${guestQuery}`}>
              {signup ? 'Já tenho conta' : 'Criar uma conta'}
            </Link>}
            <Link className="text-gray-600 hover:text-gray-900" to="/">Continuar sem conta</Link>
          </div>
          {!configLoaded && <p role="status" className="mt-4 text-sm text-gray-500">Verificando formas de acesso…</p>}
          {configLoaded && !config && <p role="alert" className="mt-4 text-sm text-red-800">Não foi possível consultar as formas de acesso. Recarregue a página para tentar novamente.</p>}
          {configLoaded && config && !emailAuthEnabled && !legacyMode && <p role="status" className="mt-4 text-sm text-gray-600">O acesso por e-mail está indisponível neste ambiente. {googleEnabled ? 'Use Google ou continue sem conta.' : 'Você pode continuar sem conta.'}</p>}
          {!verificationPending && <p className="mt-5 text-center text-sm text-gray-500">Depois de entrar, você volta à transcrição em que estava trabalhando.</p>}
        </CardContent>
      </Card>
    </section>
  )
}
