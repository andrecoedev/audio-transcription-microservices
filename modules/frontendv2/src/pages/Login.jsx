import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Lock, User } from 'lucide-react'

import Button from '../components/Button'
import { authService } from '../services/authService'
import { useAuthStore } from '../stores/authStore'

export default function Login({ signup = false }) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { setSession } = useAuthStore()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!username || !password) {
      toast.error('Informe usuário e senha')
      return
    }

    try {
      setLoading(true)
      const result = signup
        ? await authService.signup(username, email, password)
        : await authService.login(username, password)
      setSession(result.user, result.access_token)
      toast.success(signup ? 'Conta criada com sucesso' : 'Login realizado com sucesso')
      navigate(searchParams.get('saveGuest') === '1' ? '/guest' : '/', { replace: true })
    } catch (error) {
      toast.error(error.message || 'Falha no login')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-100 via-blue-50 to-cyan-100 flex items-center justify-center p-6">
      <div className="w-full max-w-md bg-white/90 backdrop-blur rounded-2xl shadow-xl border border-white/70 p-8">
        <h1 className="text-2xl font-bold text-slate-900 mb-2">{signup ? 'Criar conta' : 'Entrar'}</h1>
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
                required
              />
            </div>
          </div>

          {signup && <div>
            <label htmlFor="signup-email" className="block text-sm font-medium text-gray-700 mb-2">Email</label>
            <input id="signup-email" type="email" autoComplete="email" className="input" required
              maxLength={255} value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>}

          <div>
            <label htmlFor="login-password" className="block text-sm font-medium text-gray-700 mb-2">Senha</label>
            <div className="relative">
              <Lock className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                id="login-password"
                autoComplete={signup ? 'new-password' : 'current-password'}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input pl-10"
                placeholder="********"
                required
                minLength={signup ? 12 : undefined}
              />
            </div>
          </div>

          <Button type="submit" className="w-full" loading={loading}>
            {signup ? 'Criar conta' : 'Entrar'}
          </Button>
        </form>
        {signup && <p className="text-sm text-gray-600 mt-3">Senha: 12 a 72 bytes. Providers externos exigirão sua própria credencial; conectar credenciais ainda não está disponível.</p>}
        <div className="mt-4 flex justify-between text-primary-700">
          <Link to={`${signup ? '/login' : '/signup'}${searchParams.get('saveGuest') === '1' ? '?saveGuest=1' : ''}`}>
            {signup ? 'Já tenho conta' : 'Criar conta'}
          </Link>
          <Link to="/guest">Continuar como visitante</Link>
        </div>
      </div>
    </div>
  )
}
