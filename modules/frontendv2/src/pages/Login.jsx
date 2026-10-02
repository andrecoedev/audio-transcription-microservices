import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Lock, User } from 'lucide-react'

import Button from '../components/Button'
import { authService } from '../services/authService'
import { useAuthStore } from '../stores/authStore'

export default function Login() {
  const navigate = useNavigate()
  const { setSession } = useAuthStore()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!username || !password) {
      toast.error('Informe usuário e senha')
      return
    }

    try {
      setLoading(true)
      const result = await authService.login(username, password)
      setSession(result.user, result.access_token)
      toast.success('Login realizado com sucesso')
      navigate('/', { replace: true })
    } catch (error) {
      toast.error(error.message || 'Falha no login')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-100 via-blue-50 to-cyan-100 flex items-center justify-center p-6">
      <div className="w-full max-w-md bg-white/90 backdrop-blur rounded-2xl shadow-xl border border-white/70 p-8">
        <h1 className="text-2xl font-bold text-slate-900 mb-2">Entrar</h1>
        <p className="text-sm text-slate-600 mb-6">Autentique-se para acessar recursos protegidos.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="login-username" className="block text-sm font-medium text-gray-700 mb-2">Usuário</label>
            <div className="relative">
              <User className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                id="login-username"
                autoComplete="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="input pl-10"
                placeholder="admin"
              />
            </div>
          </div>

          <div>
            <label htmlFor="login-password" className="block text-sm font-medium text-gray-700 mb-2">Senha</label>
            <div className="relative">
              <Lock className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                id="login-password"
                autoComplete="current-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input pl-10"
                placeholder="********"
              />
            </div>
          </div>

          <Button type="submit" className="w-full" loading={loading}>
            Entrar
          </Button>
        </form>
      </div>
    </div>
  )
}
