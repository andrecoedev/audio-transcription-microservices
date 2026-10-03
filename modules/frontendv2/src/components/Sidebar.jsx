import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { Home, FileAudio, Plus, Settings, Users, ListChecks, ChevronUp, LogOut } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { endSession } from '../services/sessionService'
import toast from 'react-hot-toast'

const navigation = [
  { name: 'Início', href: '/', icon: Home },
  { name: 'Nova transcrição', href: '/new-transcription', icon: Plus },
  { name: 'Reuniões', href: '/meetings', icon: Users },
  { name: 'Histórico', href: '/transcriptions', icon: FileAudio },
  { name: 'Tarefas', href: '/tasks', icon: ListChecks },
  { name: 'Configurações', href: '/settings', icon: Settings },
]

export default function Sidebar({ onNavigate }) {
  const { user, isAuthenticated } = useAuthStore()
  const [accountOpen, setAccountOpen] = useState(false)
  return <aside className="flex h-full w-[220px] shrink-0 flex-col border-r border-gray-200 bg-white px-4 py-7">
    <Link to="/" onClick={onNavigate} className="mb-10 px-3">
      <span className="block text-2xl font-semibold tracking-[0.16em] text-primary-600">USAGI</span>
      <span className="mt-1 block text-xs text-gray-500">Inteligência de áudio</span>
    </Link>
    <nav aria-label="Navegação principal" className="space-y-1">
      {navigation.map(({ name, href, icon: Icon }) => <NavLink key={href} to={href} end={href === '/'} onClick={onNavigate}
        className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${isActive ? 'bg-primary-50 font-medium text-primary-800' : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'}`}>
        <Icon className="h-4 w-4" aria-hidden="true" />{name}
      </NavLink>)}
    </nav>
    <div className="relative mt-auto pt-8">
      {accountOpen && <div className="mb-2 space-y-1 rounded-xl border bg-white p-2 text-sm shadow-sm">
        {isAuthenticated ? <><Link to="/settings" onClick={() => { setAccountOpen(false); onNavigate?.() }} className="block rounded-lg p-2 hover:bg-gray-50">Minha conta</Link>
          <button type="button" onClick={async () => {
            try { await endSession(); setAccountOpen(false); onNavigate?.() }
            catch { toast.error('Não foi possível encerrar a sessão Google. Tente novamente.') }
          }} className="flex w-full items-center gap-2 rounded-lg p-2 text-left hover:bg-gray-50"><LogOut className="h-4 w-4" />Sair</button></>
          : <><Link to="/login" onClick={onNavigate} className="block rounded-lg p-2 hover:bg-gray-50">Entrar</Link><Link to="/signup" onClick={onNavigate} className="block rounded-lg p-2 hover:bg-gray-50">Criar conta</Link></>}
      </div>}
      <button type="button" aria-label="Área da conta" aria-expanded={accountOpen} onClick={() => setAccountOpen(!accountOpen)} className="flex w-full items-center gap-3 rounded-xl border p-3 text-left hover:bg-gray-50">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-xs font-semibold text-primary-800">{user?.initials || 'V'}</span>
        <span className="min-w-0 flex-1"><span className="block truncate text-xs font-medium">{user?.name || 'Visitante'}</span><span className="block truncate text-[11px] text-gray-500">{user?.email || 'Salvar com uma conta'}</span></span>
        <ChevronUp className="h-3 w-3 text-gray-500" aria-hidden="true" />
      </button>
      {!isAuthenticated && <div className="mt-3 flex justify-center gap-3 text-xs text-primary-700"><Link to="/login" onClick={onNavigate}>Entrar</Link><Link to="/signup" onClick={onNavigate}>Criar conta</Link></div>}
    </div>
  </aside>
}
