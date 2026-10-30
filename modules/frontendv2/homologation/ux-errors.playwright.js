/* eslint-env node */
// Run ONLY after the synthetic desktop/mobile journeys. No real provider calls.
// Changes and restores the disposable policy via the existing Admin API.
async (page) => {
  const base = 'http://127.0.0.1:4180', api = 'http://127.0.0.1:2029'
  const check = (value, message) => { if (!value) throw new Error(message) }
  const config = await (await page.request.get(`${api}/auth/config`)).json()
  check(config.firebase_project_id === 'usagi-beta-e2e', 'Synthetic project required')
  await page.context().route('**/*', route => [base, api].includes(new URL(route.request().url()).origin)
    ? route.continue() : route.abort())
  const signed = await page.request.post(`${api}/auth/login`, { data: {
    username: 'synthetic-admin', password: 'Synthetic-only-passphrase!',
  } })
  check(signed.ok(), 'Synthetic admin required')
  const admin = await signed.json()
  check(admin.user.email === 'admin-local@example.invalid', 'Unexpected administrator')
  const headers = { Authorization: `Bearer ${admin.access_token}` }
  const snapshot = async () => {
    const response = await page.request.get(`${api}/admin/settings`, { headers })
    check(response.ok(), 'Cannot read isolated policy')
    return response.json()
  }
  const original = await snapshot()
  check(original.values['beta.round_id'] === 'test-round', 'Synthetic round required')
  const change = async (section, values) => {
    const latest = await snapshot()
    const response = await page.request.patch(`${api}/admin/settings/${section}`, {
      headers, data: { version: latest.version, confirmed: true, ...values },
    })
    check(response.ok(), `Cannot update synthetic ${section} policy`)
  }
  const wav = Buffer.alloc(44 + 8000 * 2 * 40)
  wav.write('RIFF'); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8)
  wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22)
  wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28); wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34)
  wav.write('data', 36); wav.writeUInt32LE(wav.length - 44, 40)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${base}/login?returnTo=%2Fnew-transcription`)
  await page.getByLabel('E-mail', { exact: true }).fill('member@example.invalid')
  await page.getByLabel('Senha', { exact: true }).fill('Synthetic-passphrase!')
  await page.getByRole('button', { name: 'Entrar', exact: true }).click()
  await page.waitForURL('**/new-transcription')
  const prepare = async () => {
    await page.goto(`${base}/new-transcription`)
    const choice = page.getByRole('button', { name: 'Transcrição do Beta', exact: true })
    await choice.click()
    await page.locator('input[type=file]').setInputFiles({ name: 'Cenário de erro de exemplo.wav', mimeType: 'audio/wav', buffer: wav })
  }
  const submit = async (status, message, screenshot) => {
    const response = page.waitForResponse(response => response.url() === `${api}/transcriptions/jobs` && response.request().method() === 'POST')
    await page.getByRole('button', { name: /Iniciar transcrição/i }).last().click()
    check((await response).status() === status, 'Unexpected admission response')
    await page.getByText(message, { exact: true }).first().waitFor()
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Error state overflow')
    await page.screenshot({ path: `docs/design/product-ux-copy/${screenshot}.png`, fullPage: true })
  }
  try {
    await prepare()
    await change('beta', { quota_minutes_per_participant: 0 })
    await submit(429, 'Você atingiu a franquia desta rodada do Beta. Não há renovação automática.', 'quota-mobile')
    await change('beta', { quota_minutes_per_participant: original.values['beta.quota_minutes_per_participant'] })
    await prepare()
    await change('assemblyai', { hard_stop_usd: '0', alert_usd: '0' })
    await submit(503, 'Novas transcrições do Beta estão temporariamente indisponíveis. Tente novamente mais tarde.', 'platform-mobile')
    const text = await page.locator('main').innerText()
    check(!/\$|hard.stop|budget|saldo externo|orçamento interno/i.test(text), 'Internal finance exposed')
    await change('assemblyai', {
      hard_stop_usd: original.values['assemblyai.hard_stop_usd'], alert_usd: original.values['assemblyai.alert_usd'],
    })
    await change('beta', { enabled: false })
    await page.reload()
    const choice = page.getByRole('button', { name: 'Transcrição do Beta', exact: true })
    await choice.waitFor()
    check(await choice.isDisabled(), 'Unavailable Beta remained selectable')
    await page.screenshot({ path: 'docs/design/product-ux-copy/beta-unavailable-mobile.png', fullPage: true })
    return { actualHttp: { quota: 429, platform: 503 }, betaDisabled: true, paidCalls: 0 }
  } finally {
    await change('assemblyai', {
      hard_stop_usd: original.values['assemblyai.hard_stop_usd'], alert_usd: original.values['assemblyai.alert_usd'],
    })
    await change('beta', {
      quota_minutes_per_participant: original.values['beta.quota_minutes_per_participant'], enabled: original.values['beta.enabled'],
    })
  }
}
