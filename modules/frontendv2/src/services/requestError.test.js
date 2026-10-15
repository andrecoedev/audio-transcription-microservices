import { expect, it } from 'vitest'
import { requestErrorMessage } from './requestError'

it('translates internal queue failures into an actionable transcription message', () => {
  expect(requestErrorMessage(503, 'Job queue is temporarily unavailable')).toBe('Não foi possível iniciar a transcrição agora. Tente novamente em alguns instantes.')
})
it('preserves relevant policy explanations without returning unknown diagnostics', () => {
  expect(requestErrorMessage(429, 'Platform transcription budget exhausted')).toContain('franquia')
  expect(requestErrorMessage(503, 'Visitor transcription is unavailable')).toContain('visitantes')
  expect(requestErrorMessage(403, 'Sua conta precisa conectar AssemblyAI.')).toBe('Sua conta precisa conectar AssemblyAI.')
  expect(requestErrorMessage(500, 'synthetic-secret-diagnostic')).not.toContain('synthetic-secret')
  expect(requestErrorMessage(422, [{ input: 'synthetic-secret' }])).not.toContain('synthetic-secret')
})
it('explains size limits, rate limiting, unavailability and connection errors', () => {
  expect(requestErrorMessage(500, 'Audio could not be decoded')).toContain('Confira se ele contém som')
  expect(requestErrorMessage(500, 'Audio could not be decoded')).toContain('WAV ou MP3')
  expect(requestErrorMessage(415, 'File content does not match a supported audio/video format')).toContain('não basta trocar a extensão')
  expect(requestErrorMessage(413)).toContain('limite de envio')
  expect(requestErrorMessage(429)).toContain('Aguarde')
  expect(requestErrorMessage(502)).toContain('temporariamente indisponível')
  expect(requestErrorMessage()).toContain('Verifique sua conexão')
})

it('distinguishes settings revision conflicts from operational business conflicts', () => {
  expect(requestErrorMessage(409, { code: 'admin_settings_revision_conflict' })).toContain('outra aba')
  expect(requestErrorMessage(409, 'O máximo não pode ficar abaixo das vagas já utilizadas nesta rodada.')).toContain('limite de participantes')
  expect(requestErrorMessage(409, 'Revogue o acesso beta atual antes de conceder outro.')).toContain('acesso beta ativo')
  expect(requestErrorMessage(409, { code: 'unknown', message: 'synthetic-secret' })).not.toContain('synthetic-secret')
})
