import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Lock, User } from 'lucide-react'

import Button from '../components/Button'
import Card, { CardContent } from '../components/Card'
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
  const [error, setError] = useState('')

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (!username || !password) {
      setError('Informe usuário e senha.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const result = signup
        ? await authService.signup(username, email, password)
        : await authService.login(username, password)
      setSession(result.user, result.access_token)
      navigate('/', { replace: true })
    } catch {
      setError(signup
        ? 'Não foi possível criar sua conta. Confira os dados e tente novamente.'
        : 'Não foi possível entrar. Confira seu usuário e senha e tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  const guestQuery = searchParams.get('saveGuest') === '1' ? '?saveGuest=1' : ''

  return (
    <section aria-labelledby="auth-heading" className="mx-auto flex w-full max-w-md flex-col justify-center py-8">
        <div className="mb-5 text-center">
          <span className="rounded-full bg-primary-50 px-3 py-1.5 text-xs font-semibold text-primary-800">Salve seu progresso</span>
          <h1 id="auth-heading" className="mt-4 text-3xl font-semibold text-gray-900">{signup ? 'Crie sua conta' : 'Salve seu trabalho'}</h1>
          <p className="mx-auto mt-2 max-w-sm text-gray-600">{signup
            ? 'Crie uma conta para guardar transcrições e acessar seu histórico.'
            : 'Entre para salvar esta transcrição, acessar o histórico e continuar em outro dispositivo.'}</p>
        </div>

        <Card className="p-7">
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <label htmlFor="login-username" className="block text-sm font-medium text-gray-700">Usuário
                <span className="relative mt-2 block">
                  <User aria-hidden="true" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
                  <input id="login-username" autoComplete="username" type="text" value={username}
                    onChange={(event) => setUsername(event.target.value)} className="input pl-10" required />
                </span>
              </label>

              {signup && <label htmlFor="signup-email" className="block text-sm font-medium text-gray-700">E-mail
                <input id="signup-email" type="email" autoComplete="email" className="input mt-2" required maxLength={255}
                  value={email} onChange={(event) => setEmail(event.target.value)} />
              </label>}

              <label htmlFor="login-password" className="block text-sm font-medium text-gray-700">Senha
                <span className="relative mt-2 block">
                  <Lock aria-hidden="true" className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-500" />
                  <input id="login-password" autoComplete={signup ? 'new-password' : 'current-password'} type="password"
                    value={password} onChange={(event) => setPassword(event.target.value)} className="input pl-10"
                    placeholder="********"
                    required minLength={signup ? 12 : undefined} />
                </span>
              </label>
              {signup && <p className="text-xs text-gray-500">Use uma senha com pelo menos 12 caracteres.</p>}

              {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
              <Button type="submit" className="w-full" loading={loading}>{signup ? 'Criar conta' : 'Entrar'}</Button>
            </form>

            <div className="mt-5 flex flex-col items-center gap-3 text-sm text-primary-800">
              <Link to={`${signup ? '/login' : '/signup'}${guestQuery}`}>
                {signup ? 'Já tenho conta' : 'Novo na USAGI? Criar uma conta'}
              </Link>
              <Link className="text-gray-600 hover:text-gray-900" to="/">Continuar sem conta</Link>
            </div>
            <p className="mt-5 text-center text-sm text-gray-500">Depois de entrar, você volta à transcrição em que estava trabalhando.</p>
          </CardContent>
        </Card>
    </section>
  )
}
