import { useEffect, useState } from 'react'
import { authService } from '../services/authService'
import { useAuthStore } from '../stores/authStore'
import Button from './Button'
import HelpPopover from './HelpPopover'
import GoogleAccountLink from './GoogleAccountLink'
import FirebaseAccountMethods from './FirebaseAccountMethods'
import LegacyFirebaseMigration from './LegacyFirebaseMigration'

export default function AccountSettings() {
  const userId = useAuthStore(state => state.user?.id)
  const authProvider = useAuthStore(state => state.authProvider)
  const [account, setAccount] = useState(null)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)
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
  return <div className="space-y-3">
    <dl className="grid gap-3 sm:grid-cols-2 text-sm">
      <div><dt className="text-gray-500">Nome</dt><dd className="mt-1 break-words font-medium text-gray-900">{account.display_name || account.username}</dd></div>
      <div><dt className="text-gray-500">E-mail</dt><dd className="mt-1 break-words font-medium text-gray-900">{account.email || 'Não informado'}</dd></div>
    </dl>
    <div className="flex flex-wrap items-center gap-2 text-sm text-gray-700">
      <span>Senha</span><HelpPopover label="Senha">{google
        ? 'Você entra pelo Google. Gerencie a senha e a segurança na sua conta Google.'
        : firebaseAccount
          ? 'Esta conta usa acesso Firebase. Os métodos disponíveis aparecem abaixo e permanecem vinculados à mesma conta.'
        : 'Esta conta usa a senha USAGI existente. Alteração e redefinição de senha ainda não estão disponíveis nesta versão.'}</HelpPopover>
      <span className="text-gray-600">{google ? 'Gerenciada pelo Google' : firebaseAccount ? 'Gerenciada pelo Firebase' : 'Alteração não disponível'}</span>
      {google && <a className="font-medium text-primary-800 underline" href="https://myaccount.google.com/security" target="_blank" rel="noopener noreferrer">Gerenciar no Google</a>}
    </div>
    {firebaseAccount
      ? <FirebaseAccountMethods account={account} onUpdated={() => setAttempt(value => value + 1)} />
      : <>{!account.firebase_connected && <GoogleAccountLink />}<LegacyFirebaseMigration account={account} /></>}
  </div>
}
