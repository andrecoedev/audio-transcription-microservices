/* eslint-env node */
// Run only while the disposable Compose Redis is stopped; restore it afterwards.
async (page) => {
  const api = 'http://127.0.0.1:2029'
  const headers = { Authorization: 'Bearer beta-e2e-member' }
  const before = await page.request.get(`${api}/transcriptions`, { headers })
  if (before.status() !== 200) throw new Error('Persisted listing unavailable')
  const data = await before.json()
  const completed = data.transcriptions.find(item => item.original_filename === 'Reunião sintética – integração.wav')
  if (!completed) throw new Error('Complete the desktop journey first')
  const result = await page.request.get(`${api}/transcriptions/${completed.id}`, { headers })
  const upload = await page.request.post(`${api}/transcriptions/jobs`, { headers,
    multipart: { file: { name: 'synthetic-outage.wav', mimeType: 'audio/wav', buffer: Buffer.from('synthetic-only') },
      transcription_model: 'assemblyai', credential_source: 'platform', use_diarization: 'true' } })
  const after = await page.request.get(`${api}/transcriptions`, { headers })
  if (result.status() !== 200 || upload.status() !== 503 || (await after.json()).total !== data.total) {
    throw new Error('Redis outage must preserve reads and reject writes without creating a job')
  }
  return { persistedResult: result.status(), newSubmission: upload.status(), newRecords: 0 }
}
