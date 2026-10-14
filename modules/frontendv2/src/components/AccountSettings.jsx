import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { authService } from '../services/authService'
import { firebaseAuth } from '../services/firebaseAuth'
import { endSession } from '../services/sessionService'
import { requestErrorMessage } from '../services/requestError'
import { useAuthStore } from '../stores/authStore'
import Button from './Button'
import HelpPopover from './HelpPopover'
import GoogleAccountLink from './GoogleAccountLink'
import FirebaseAccountMethods from './FirebaseAccountMethods'
import LegacyFirebaseMigration from './LegacyFirebaseMigration'

export default function AccountSettings() {
  const navigate = useNavigate()
  const userId = useAuthStore(state => state.user?.id)
  const authProvider = useAuthStore(state => state.authProvider)
  const [account, setAccount] = useState(null)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [showDelete, setShowDelete] = useState(false)
  const [confirmation, setConfirmation] = useState('')
  const [password, setPassword] = useState('')
  const [privacyBusy, setPrivacyBusy] = useState(false)
  const [privacyError, setPrivacyError] = useState('')
  useEffect(() => {
    if (userId == null) return
    let active = true
    setAccount(null)
    setError(false)
    authService.me().then(result => {
      if (!active) return
      if (!result.authenticated || result.user?.id !== userId) { setError(true); return }
      setAccount(result.user)
    }).catch(() => { if (active) setError(true) })
    return () => { active = false }
  }, [userId, authProvider, attempt])
  if (userId == null) return <p className="text-sm text-gray-600">Entre na sua conta para ver estes dados.</p>
  if (error) return <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-red-800">
    Não foi possível consultar sua conta.
    <Button variant="outline" size="sm" onClick={() => setAttempt(value => value + 1)}>Tentar novamente</Button>
  </div>
  if (!account || account.id !== userId) return <p role="status" className="text-sm text-gray-600">Carregando conta…</p>
  const signInProvider = account.firebase_sign_in_provider
    ?? (account.auth_provider === 'firebase' ? 'google.com' : null)
  const firebaseAccount = account.auth_provider === 'firebase'
  const google = firebaseAccount && signInProvider === 'google.com'
  const localAccount = account.auth_provider === 'local'
  const firebasePassword = firebaseAccount && signInProvider === 'password'
  const downloadData = async () => {
    setPrivacyBusy(true)
    setPrivacyError('')
    let objectUrl
    try {
      const data = await authService.exportData()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      objectUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = 'usagi-dados.json'
      link.click()
    } catch (error) {
      setPrivacyError(requestErrorMessage(error?.status, error?.response?.data?.detail))
    } finally {
      if (objectUrl) URL.revokeObjectURL(objectUrl)
      setPrivacyBusy(false)
    }
  }
  const deleteAccount = async (event) => {
    event.preventDefault()
    if (confirmation !== 'EXCLUIR' || privacyBusy) return
    setPrivacyBusy(true)
    setPrivacyError('')
    const submittedPassword = password
    setPassword('')
    try {
      let token
      if (localAccount) {
        if (!submittedPassword) { setPrivacyError('Informe sua senha para confirmar a exclusão.'); return }
      } else if (google) {
        const { uid } = await firebaseAuth.reauthenticateGoogle()
        const context = await firebaseAuth.getTokenContext(true)
        if (!context || context.uid !== uid) throw Object.assign(new Error('account changed'), { code: 'auth/account-changed' })
        token = context.token
      } else if (firebasePassword) {
        const { uid } = await firebaseAuth.reauthenticatePassword(submittedPassword)
        const context = await firebaseAuth.getTokenContext(true)
        if (!context || context.uid !== uid) throw Object.assign(new Error('account changed'), { code: 'auth/account-changed' })
        token = context.token
      } else {
        setPrivacyError('Não foi possível confirmar sua identidade para excluir a conta.'); return
      }
      const currentSession = useAuthStore.getState()
      if (currentSession.user?.id !== userId || currentSession.authProvider !== authProvider) {
        throw Object.assign(new Error('account changed'), { code: 'auth/account-changed' })
      }
      const body = { confirmation: 'EXCLUIR', ...(localAccount ? { password: submittedPassword } : {}) }
      const result = await authService.deleteAccount(body, token)
      setShowDelete(false)
      setConfirmation('')
      try { await endSession() } catch {
        // Domain access is already cleared, but external sign-out failure is
        // not evidence of completed browser-session cleanup.
        toast.error('Conta excluída, mas não foi possível sair da sessão externa. Feche o navegador e tente sair novamente.')
      }
      navigate('/', { replace: true })
      const pendingMessage = result.cleanup_pending && result.identity_cleanup_pending
        ? 'Conta excluída. A limpeza de arquivos e a remoção da identidade de acesso estão pendentes.'
        : result.cleanup_pending
          ? 'Conta excluída. A limpeza de arquivos está pendente.'
          : 'Conta excluída. A remoção da identidade de acesso está pendente.'
      toast.success(result.cleanup_pending || result.identity_cleanup_pending
        ? pendingMessage
        : 'Conta USAGI excluída. Esta ação não exclui sua conta Google.')
    } catch (error) {
      if (error?.code === 'auth/account-changed') setPrivacyError('A conta mudou durante a confirmação. Entre novamente para continuar.')
      else if (error?.status === 403) setPrivacyError('Confirme sua identidade novamente e tente excluir a conta.')
      else if (error?.status === 409) setPrivacyError('A conta está em uso. Aguarde os processamentos terminarem antes de excluir a conta.')
      else setPrivacyError(requestErrorMessage(error?.status, error?.response?.data?.detail))
    } finally {
      setPassword('')
      setPrivacyBusy(false)
    }
  }
  return <div className="space-y-3">
    <dl className="grid gap-3 sm:grid-cols-2 text-sm">
      <div><dt className="text-gray-500">Nome</dt><dd className="mt-1 break-words font-medium text-gray-900">{account.display_name || account.username}</dd></div>
      <div><dt className="text-gray-500">E-mail</dt><dd className="mt-1 break-words font-medium text-gray-900">{account.email || 'Não informado'}</dd></div>
    </dl>
    <div className="flex flex-wrap items-center gap-2 text-sm text-gray-700">
      <span>Senha</span><HelpPopover label="Senha">{google
        ? 'Você entra pelo Google. Gerencie a senha e a segurança na sua conta Google.'
        : firebaseAccount
          ? 'Os métodos de acesso disponíveis aparecem abaixo e permanecem vinculados à mesma conta.'
        : 'Esta conta usa a senha USAGI existente. Alteração e redefinição de senha ainda não estão disponíveis nesta versão.'}</HelpPopover>
      <span className="text-gray-600">{google ? 'Gerenciada pelo Google' : firebaseAccount ? 'Gerenciada pelo método conectado' : 'Alteração não disponível'}</span>
      {google && <a className="font-medium text-primary-800 underline" href="https://myaccount.google.com/security" target="_blank" rel="noopener noreferrer">Gerenciar no Google</a>}
    </div>
    {firebaseAccount
      ? <FirebaseAccountMethods account={account} onUpdated={() => setAttempt(value => value + 1)} />
      : <>{!account.firebase_connected && <GoogleAccountLink />}<LegacyFirebaseMigration account={account} /></>}
    <section aria-labelledby="privacy-title" className="space-y-3 border-t border-gray-200 pt-4">
      <div>
        <h3 id="privacy-title" className="text-sm font-semibold text-gray-900">Privacidade e seus dados</h3>
        <p className="mt-1 text-sm text-gray-600">Os resultados ficam disponíveis até você excluí-los ou excluir a conta. O áudio é removido após o processamento, mas falhas de limpeza podem deixar a remoção pendente. Áudios, transcrições e resumos enviados a serviços externos seguem também as condições desses serviços. Esta versão beta pode apresentar falhas; tente novamente se uma solicitação não funcionar.</p>
      </div>
      <Button variant="outline" size="sm" loading={privacyBusy} disabled={privacyBusy} onClick={downloadData}>Baixar meus dados</Button>
      {!showDelete ? <Button variant="danger" size="sm" disabled={privacyBusy} onClick={() => { setShowDelete(true); setPrivacyError('') }}>Excluir minha conta</Button> : <form onSubmit={deleteAccount} className="space-y-3 rounded-lg border border-red-200 bg-red-50 p-3">
        <p className="text-sm text-red-900">A exclusão é irreversível e remove sua conta e dados da USAGI. Para contas Google, isso também remove a identidade Firebase vinculada ao projeto USAGI, mas não exclui sua conta Google global.</p>
        <label className="block text-sm font-medium text-gray-800" htmlFor="delete-confirmation">Digite EXCLUIR para confirmar</label>
        <input id="delete-confirmation" value={confirmation} onChange={event => setConfirmation(event.target.value)} autoComplete="off" className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm" />
        {(localAccount || firebasePassword) && <label className="block text-sm font-medium text-gray-800" htmlFor="delete-password">{localAccount ? 'Senha da conta USAGI' : 'Senha da conta' }<input id="delete-password" type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" /></label>}
        <div className="flex flex-wrap gap-2"><Button type="submit" variant="danger" size="sm" loading={privacyBusy} disabled={privacyBusy || confirmation !== 'EXCLUIR' || ((localAccount || firebasePassword) && !password)}>Confirmar exclusão</Button><Button type="button" variant="outline" size="sm" disabled={privacyBusy} onClick={() => { setShowDelete(false); setConfirmation(''); setPassword(''); setPrivacyError('') }}>Cancelar exclusão</Button></div>
      </form>}
      {privacyError && <p role="alert" className="text-sm text-red-800">{privacyError}</p>}
    </section>
  </div>
}
