import { expect, it } from 'vitest'
import { requestErrorMessage } from './requestError'

it('translates internal queue failures into an actionable transcription message', () => {
  expect(requestErrorMessage(503, 'Job queue is temporarily unavailable')).toBe('Não foi possível iniciar a transcrição agora. Tente novamente em alguns instantes.')
})
it('preserves relevant policy explanations without returning unknown diagnostics', () => {
  expect(requestErrorMessage(429, 'Platform transcription budget exhausted')).toBe('Novas transcrições do Beta estão temporariamente indisponíveis. Tente novamente mais tarde.')
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

it('distinguishes the actual Beta quota response from rate limiting', () => {
  expect(requestErrorMessage(429, 'A franquia da rodada beta está esgotada; não há renovação automática.'))
    .toBe('Você atingiu a franquia desta rodada do Beta. Não há renovação automática.')
})

it.each([403, 409, 429, 503])('shows platform admission unavailability without disclosing finance at HTTP %s', status => {
  const message = requestErrorMessage(status, 'Este recurso está temporariamente indisponível no Beta.')
  expect(message).toBe('Novas transcrições do Beta estão temporariamente indisponíveis. Tente novamente mais tarde.')
  expect(message).not.toMatch(/franquia|budget|orçamento|saldo|dólar|\$/i)
})

it('keeps concurrency, queue, storage, monthly quota and generic rate limits distinct', () => {
  expect(requestErrorMessage(429, 'O limite de transcrições simultâneas foi atingido.')).toContain('em processamento')
  expect(requestErrorMessage(429, 'Sua fila está cheia. Aguarde uma transcrição terminar.')).toContain('fila está cheia')
  expect(requestErrorMessage(429, 'O limite de armazenamento foi atingido. Exclua arquivos que não precisa manter.')).toContain('armazenamento está cheio')
  expect(requestErrorMessage(429, 'Sua franquia mensal está esgotada. Aguarde a renovação.')).toContain('franquia mensal')
  expect(requestErrorMessage(429)).toContain('Muitas solicitações')
})
