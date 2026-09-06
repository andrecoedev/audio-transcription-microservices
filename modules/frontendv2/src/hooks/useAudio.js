import { useState, useEffect } from 'react'
import { audioService } from '../services/audioService'
import toast from 'react-hot-toast'

export function useTranscriptions(options = {}) {
  const [transcriptions, setTranscriptions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [pagination, setPagination] = useState({
    skip: options.skip || 0,
    limit: options.limit || 10,
  })

  useEffect(() => {
    loadTranscriptions()
  }, [pagination])

  const loadTranscriptions = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await audioService.listTranscriptions(pagination)
      setTranscriptions(data.transcriptions || [])
    } catch (err) {
      const message = err.message || 'Erro ao carregar transcrições'
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  const deleteTranscription = async (id) => {
    try {
      await audioService.deleteTranscription(id)
      toast.success('Transcrição excluída')
      loadTranscriptions()
    } catch (err) {
      toast.error('Erro ao excluir transcrição')
      throw err
    }
  }

  const refresh = () => loadTranscriptions()

  return {
    transcriptions,
    loading,
    error,
    pagination,
    setPagination,
    deleteTranscription,
    refresh,
  }
}

export function useTranscription(id) {
  const [transcription, setTranscription] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (id) {
      loadTranscription()
    }
  }, [id])

  const loadTranscription = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await audioService.getTranscription(id)
      setTranscription(data)
    } catch (err) {
      const message = err.message || 'Erro ao carregar transcrição'
      setError(message)
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  const refresh = () => loadTranscription()

  return { transcription, loading, error, refresh }
}

export function useSystemHealth() {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    checkHealth()
  }, [])

  const checkHealth = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await audioService.checkHealth()
      setHealth(data)
    } catch (err) {
      const message = err.message || 'Erro ao verificar status do sistema'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const refresh = () => checkHealth()

  return { health, loading, error, refresh }
}

export function useStats() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadStats()
  }, [])

  const loadStats = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await audioService.getStats()
      setStats(data)
    } catch (err) {
      const message = err.message || 'Erro ao carregar estatísticas'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  const refresh = () => loadStats()

  return { stats, loading, error, refresh }
}
