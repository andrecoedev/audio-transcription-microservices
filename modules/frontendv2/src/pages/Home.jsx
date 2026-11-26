import { Link } from 'react-router-dom'
import { FileAudio } from 'lucide-react'
import PageHeader from '../components/PageHeader'
import { useAuthStore } from '../stores/authStore'
import Dashboard from './Dashboard'
import Guest from './Guest'
import VisitorHome from './VisitorHome'

export default function Home() {
  const authenticated = useAuthStore((state) => state.isAuthenticated)

  if (!authenticated) return <VisitorHome />

  return <div className="mx-auto max-w-6xl space-y-6">
    <PageHeader title="Início" description="Acesse suas transcrições e reuniões ou comece uma nova." />
    <section className="flex flex-wrap items-center justify-between gap-6 border-b border-gray-200 pb-6">
      <div className="flex min-w-0 items-start gap-4">
        <FileAudio aria-hidden="true" className="h-10 w-10 shrink-0 rounded-lg bg-primary-50 p-2 text-primary-700" />
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Transforme seu áudio em texto</h2>
          <p className="mt-1 max-w-xl text-sm text-gray-600">Envie um áudio para criar uma transcrição e revisar o conteúdo.</p>
        </div>
      </div>
      <Link to="/new-transcription" className="btn-primary inline-flex items-center gap-2">Nova transcrição</Link>
    </section>
    <Guest />
    <nav aria-label="Suas áreas" className="flex flex-wrap gap-x-5 gap-y-2 text-sm font-medium">
      <Link className="text-primary-700 hover:underline" to="/transcriptions">Ver minhas transcrições</Link>
      <Link className="text-primary-700 hover:underline" to="/meetings">Ver minhas reuniões</Link>
    </nav>
    <Dashboard />
  </div>
}
