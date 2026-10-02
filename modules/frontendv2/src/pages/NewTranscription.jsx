import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { Upload, FileAudio, X, Zap, Users } from 'lucide-react'
import Card, { CardHeader, CardTitle, CardContent } from '../components/Card'
import Button from '../components/Button'
import { audioService } from '../services/audioService'
import { MAX_FILE_SIZE } from '../utils/constants'
import toast from 'react-hot-toast'

export default function NewTranscription() {
  const navigate = useNavigate()
  const [file, setFile] = useState(null)
  const [options, setOptions] = useState({
    useDiarization: false,
    transcriptionModel: 'whisper'
  })
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)

  const onDrop = useCallback((acceptedFiles) => {
    if (acceptedFiles.length > 0) {
      const selectedFile = acceptedFiles[0]
      
      if (selectedFile.size > MAX_FILE_SIZE) {
        toast.error(`Arquivo muito grande! Máximo: ${(MAX_FILE_SIZE / (1024 * 1024)).toFixed(0)}MB`)
        return
      }
      
      setFile(selectedFile)
      toast.success('Arquivo carregado com sucesso!')
    }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'audio/*': ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.opus'],
      'video/*': ['.mp4']
    },
    maxFiles: 1,
    multiple: false
  })

  const handleSubmit = async () => {
    if (!file) {
      toast.error('Selecione um arquivo primeiro')
      return
    }

    try {
      setUploading(true)
      setProgress(0)

      const result = await audioService.createTranscriptionJob(file, {
        ...options,
        onUploadProgress: (progressEvent) => {
          const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total)
          setProgress(percentCompleted)
        }
      })

      toast.success('Arquivo enviado. Job de transcrição enfileirado!')
      navigate(`/transcriptions/${result.id}`)
    } catch (error) {
      console.error('Erro ao transcrever:', error)
      toast.error(error.message || 'Erro ao processar arquivo')
    } finally {
      setUploading(false)
      setProgress(0)
    }
  }

  const removeFile = () => {
    setFile(null)
    setProgress(0)
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Nova Transcrição</h1>
        <p className="text-gray-600 mt-1">Faça upload de um arquivo de áudio ou vídeo para transcrever</p>
      </div>

      {/* Upload Area */}
      <Card>
        <CardHeader>
          <CardTitle>📁 Upload de Arquivo</CardTitle>
        </CardHeader>
        <CardContent>
          {!file ? (
            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
                isDragActive
                  ? 'border-primary-500 bg-primary-50'
                  : 'border-gray-300 hover:border-primary-400'
              }`}
            >
              <input {...getInputProps()} />
              <Upload className="w-12 h-12 text-gray-400 mx-auto mb-4" />
              <p className="text-lg font-medium text-gray-900 mb-2">
                {isDragActive ? 'Solte o arquivo aqui' : 'Arraste um arquivo ou clique para selecionar'}
              </p>
              <p className="text-sm text-gray-500">
                Formatos suportados: MP3, WAV, MP4, M4A, FLAC, OGG, OPUS (máx. {(MAX_FILE_SIZE / (1024 * 1024)).toFixed(0)}MB)
              </p>
            </div>
          ) : (
            <div className="border border-gray-200 rounded-lg p-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="p-3 bg-primary-100 rounded-lg">
                    <FileAudio className="w-6 h-6 text-primary-600" />
                  </div>
                  <div>
                    <p className="font-medium text-gray-900">{file.name}</p>
                    <p className="text-sm text-gray-500">
                      {(file.size / (1024 * 1024)).toFixed(2)} MB
                    </p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={removeFile}
                  disabled={uploading}
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>

              {uploading && (
                <div className="mt-4">
                  <div className="flex items-center justify-between text-sm mb-2">
                    <span className="text-gray-600">Processando...</span>
                    <span className="font-medium text-primary-600">{progress}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-primary-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Opções */}
      <Card>
        <CardHeader>
          <CardTitle>⚙️ Configurações</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Modelo de Transcrição */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Modelo de Transcrição
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => setOptions({ ...options, transcriptionModel: 'whisper' })}
                disabled={uploading}
                className={`p-4 border-2 rounded-lg transition-all ${
                  options.transcriptionModel === 'whisper'
                    ? 'border-primary-600 bg-primary-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Zap className={`w-5 h-5 ${
                    options.transcriptionModel === 'whisper' ? 'text-primary-600' : 'text-gray-400'
                  }`} />
                  <div className="text-left">
                    <p className="font-medium text-gray-900">Whisper</p>
                    <p className="text-xs text-gray-500">Local, mais rápido</p>
                  </div>
                </div>
              </button>

              <button
                onClick={() => setOptions({ ...options, transcriptionModel: 'assemblyai' })}
                disabled={uploading}
                className={`p-4 border-2 rounded-lg transition-all ${
                  options.transcriptionModel === 'assemblyai'
                    ? 'border-primary-600 bg-primary-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Zap className={`w-5 h-5 ${
                    options.transcriptionModel === 'assemblyai' ? 'text-primary-600' : 'text-gray-400'
                  }`} />
                  <div className="text-left">
                    <p className="font-medium text-gray-900">AssemblyAI</p>
                    <p className="text-xs text-gray-500">Cloud, maior precisão</p>
                  </div>
                </div>
              </button>
            </div>
          </div>

          {/* Diarização */}
          <div className="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
            <div className="flex items-center gap-3">
              <Users className="w-5 h-5 text-gray-600" />
              <div>
                <p className="font-medium text-gray-900">Segmentação de Falantes</p>
                <p className="text-sm text-gray-500">Identifica diferentes falantes no áudio</p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={options.useDiarization}
                onChange={(e) => setOptions({ ...options, useDiarization: e.target.checked })}
                disabled={uploading}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
            </label>
          </div>
        </CardContent>
      </Card>

      {/* Ações */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          onClick={() => navigate('/transcriptions')}
          disabled={uploading}
        >
          Cancelar
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={!file || uploading}
          loading={uploading}
        >
          Iniciar Transcrição
        </Button>
      </div>
    </div>
  )
}
