import { NavLink } from 'react-router-dom'
import { 
  LayoutDashboard, 
  FileAudio, 
  PlusCircle, 
  Settings,
  Activity,
  Users,
  Sparkles
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Nova Transcrição', href: '/new-transcription', icon: PlusCircle },
  { name: 'Transcrições', href: '/transcriptions', icon: FileAudio },
  { name: 'Reuniões', href: '/meetings', icon: Users },
  { name: 'Atas legadas (IA)', href: '/meeting-minutes', icon: Sparkles },
  { name: 'Configurações', href: '/settings', icon: Settings },
]

const secondaryNav = [
  { name: 'Status do Sistema', href: '/settings', icon: Activity },
]

export default function Sidebar() {
  return (
    <aside className="w-64 bg-white border-r border-gray-200 overflow-y-auto">
      <div className="p-4">
        {/* Navegação Principal */}
        <nav className="space-y-1">
          <p className="px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Principal
          </p>
          {navigation.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              end={item.href === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                  isActive
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-gray-700 hover:bg-gray-50'
                }`
              }
            >
              <item.icon className="w-5 h-5" />
              {item.name}
            </NavLink>
          ))}
        </nav>

        {/* Divisor */}
        <div className="my-4 border-t border-gray-200" />

        {/* Navegação Secundária */}
        <nav className="space-y-1">
          <p className="px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            Informações
          </p>
          {secondaryNav.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              className="w-full flex items-center gap-3 px-3 py-2 text-sm font-medium text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <item.icon className="w-5 h-5" />
              {item.name}
            </NavLink>
          ))}
        </nav>

        {/* Card de Informação */}
        <div className="mt-6 p-4 bg-gradient-to-br from-primary-50 to-primary-100 rounded-lg">
          <h3 className="text-sm font-semibold text-primary-900 mb-1">
            💡 Dica Rápida
          </h3>
          <p className="text-xs text-primary-700">
            Use a detecção de falantes para identificar quem está falando no áudio.
          </p>
        </div>
      </div>
    </aside>
  )
}
