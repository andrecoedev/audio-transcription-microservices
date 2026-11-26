import { useId, useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { ChevronUp, LogOut, X } from 'lucide-react'
import Brand from './Brand'
import { useAuthStore } from '../stores/authStore'
import { endSession } from '../services/sessionService'
import toast from 'react-hot-toast'

const navigation = [
  { name: 'Início', href: '/' },
  { name: 'Nova transcrição', href: '/new-transcription' },
  { name: 'Minhas transcrições', href: '/transcriptions' },
  { name: 'Reuniões', href: '/meetings' },
  { name: 'Tarefas', href: '/tasks' },
]

const linkClass = ({ isActive }) => `relative flex min-h-10 items-center rounded-lg px-4 py-2 text-[15px] transition-colors ${isActive ? 'font-semibold text-ink before:absolute before:inset-y-2.5 before:left-0 before:w-[3px] before:rounded-full before:bg-primary-600' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'}`

export default function Sidebar({ onNavigate, onClose, compact = false }) {
  const { user, isAuthenticated } = useAuthStore()
  const isAdmin = isAuthenticated && user?.roles?.includes('admin')
  const [accountOpen, setAccountOpen] = useState(false)
  const adminHeadingId = useId()
  return <aside className={`flex min-h-full shrink-0 flex-col border-r border-gray-200 bg-shell px-4 ${compact ? 'w-[240px] py-5' : 'w-[240px] pb-6 pt-10'}`}>
    <div className={`mb-10 flex items-start justify-between ${compact ? 'px-3 py-1' : 'px-3 py-2'}`}>
      <Link to="/" onClick={onNavigate}>
        <Brand className={compact ? 'text-lg' : 'text-xl'} />
      </Link>
      {compact && <button type="button" aria-label="Fechar navegação" onClick={onClose} className="-mr-1 -mt-1 rounded-lg p-2 text-ink hover:bg-gray-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"><X className="h-4 w-4" aria-hidden="true" /></button>}
    </div>
    <nav aria-label="Navegação principal" className="space-y-0.5">
      {navigation.map(({ name, href }) => <NavLink key={href} to={href} end={href === '/'} onClick={onNavigate} className={linkClass}>
        {name}
      </NavLink>)}
    </nav>
    {isAdmin && <section aria-labelledby={adminHeadingId} className="mt-4 border-t border-gray-200 pt-4">
      <h2 id={adminHeadingId} className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">Administração</h2>
      <nav aria-label="Administração" className="space-y-1">
        <NavLink to="/admin/settings" onClick={onNavigate} className={linkClass}>
          Administração
        </NavLink>
      </nav>
    </section>}
    <div className="mt-auto pt-6">
      <nav aria-label="Conta" className="border-t border-gray-200 pt-3">
        <NavLink to="/settings" onClick={onNavigate} className={linkClass}>Configurações</NavLink>
      </nav>
      {accountOpen && <div className="mb-2 space-y-1 rounded-xl border border-gray-200 bg-surface p-2 text-sm shadow-popover">
        {isAuthenticated ? <><Link to="/settings" onClick={() => { setAccountOpen(false); onNavigate?.() }} className="block rounded-lg p-2 hover:bg-gray-50">Minha conta</Link>
          <button type="button" onClick={async () => {
            try { await endSession(); setAccountOpen(false); onNavigate?.() }
            catch { toast.error('Não foi possível encerrar a sessão Google. Tente novamente.') }
          }} className="flex w-full items-center gap-2 rounded-lg p-2 text-left hover:bg-gray-50"><LogOut className="h-4 w-4" aria-hidden="true" />Sair</button></>
          : <><Link to="/login" onClick={() => { setAccountOpen(false); onNavigate?.() }} className="block rounded-lg p-2 hover:bg-gray-50">Entrar</Link><Link to="/signup" onClick={() => { setAccountOpen(false); onNavigate?.() }} className="block rounded-lg p-2 hover:bg-gray-50">Criar conta</Link></>}
      </div>}
      <button type="button" aria-label="Área da conta" aria-expanded={accountOpen} onClick={() => setAccountOpen(!accountOpen)} className="flex w-full items-center gap-2 rounded-lg p-2 text-left hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-600 text-xs font-semibold text-white">{user?.initials || 'V'}</span>
        <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{user?.name || 'Visitante'}</span><span className="block truncate text-xs text-gray-500">{user?.email || 'Salvar com uma conta'}</span></span>
        <ChevronUp className="h-4 w-4 text-gray-500" aria-hidden="true" />
      </button>
      {!isAuthenticated && <div className="mt-3 flex justify-center gap-3 text-sm text-primary-700"><Link to="/login" onClick={onNavigate}>Entrar</Link><Link to="/signup" onClick={onNavigate}>Criar conta</Link></div>}
    </div>
  </aside>
}
