import { LogOut, Mic2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

export default function Navbar() {
  const { user, token, logout } = useAuthStore()

  return (
    <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
      {/* Logo e Nome */}
      <div className="flex items-center gap-3">
        <div className="bg-gradient-to-br from-primary-600 to-primary-700 p-2 rounded-lg">
          <Mic2 className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900">Transcritor AI</h1>
          <p className="text-xs text-gray-500">Sistema Inteligente de Transcrição</p>
        </div>
      </div>

      {/* Informações do Usuário */}
      <div className="flex items-center gap-3">
        {!token && (
          <div className="flex items-center gap-3">
          <Link
            to="/login"
            className="px-3 py-1.5 text-xs font-medium rounded-lg text-primary-700 bg-primary-50 hover:bg-primary-100 transition-colors"
          >
            Entrar
          </Link>
          <Link to="/signup" className="text-xs font-medium text-primary-700">Criar conta</Link>
          </div>
        )}
        {token && <button
          type="button"
          onClick={logout}
          className="p-2 rounded-lg text-gray-500 hover:text-gray-800 hover:bg-gray-100 transition-colors"
          title="Sair"
        >
          <LogOut className="w-4 h-4" />
        </button>}
        <div className="text-right">
          <p className="text-sm font-medium text-gray-900">{user?.name}</p>
          <p className="text-xs text-gray-500">{user?.email}</p>
        </div>
        
        {user?.avatar ? (
          <img
            src={user.avatar}
            alt={user.name}
            className="w-10 h-10 rounded-full ring-2 ring-primary-100"
          />
        ) : (
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center text-white font-semibold ring-2 ring-primary-100">
            {user?.initials || 'V'}
          </div>
        )}
      </div>
    </nav>
  )
}
