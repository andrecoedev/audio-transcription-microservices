/* eslint-env node */
// Run with Playwright MCP browser_run_code_unsafe(filename=...).
// Requires the disposable compose.yaml and homologation/vite.config.js only.
async (page) => {
  const base = 'http://127.0.0.1:4180'
  const api = 'http://127.0.0.1:2029'
  const mobile = page.viewportSize()?.width < 768
  const persona = mobile ? 'mobile' : 'member'
  const email = `${persona}@example.invalid`
  const filename = mobile ? 'Reunião sintética – mobile.wav' : 'Reunião sintética – integração.wav'
  const events = [], errors = [], stages = []
  const started = Date.now()
  let clicks = 0
  const check = (condition, message) => { if (!condition) throw new Error(message) }
  await page.context().route('**/*', route => {
    const url = new URL(route.request().url())
    if ([base, api].includes(url.origin)) return route.continue()
    return route.abort('blockedbyclient')
  })
  page.on('pageerror', error => errors.push(error.message))
  page.on('response', response => {
    const url = new URL(response.url())
    if (url.origin === api) events.push({ path: url.pathname, status: response.status() })
  })
  const click = async (locator) => { await locator.click(); clicks++ }
  const waitText = async (text) => page.locator('p:visible, h1:visible, h2:visible, h3:visible')
    .filter({ hasText: text }).first().waitFor({ timeout: 25000 })
  const record = label => stages.push({ label, elapsed_seconds: Math.round((Date.now() - started) / 1000), clicks, path: new URL(page.url()).pathname })
  await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 })
  await page.goto(base)
  await page.evaluate(() => { localStorage.clear(); sessionStorage.clear() })
  await page.goto(`${base}/new-transcription`)
  await waitText('demonstração')
  check(await page.getByRole('link', { name: 'Administração', exact: true }).count() === 0, 'Guest must not see admin')
  record('Guest demonstrativo')
  await page.goto(`${base}/signup?returnTo=%2Fnew-transcription`)
  await page.getByLabel('E-mail', { exact: true }).fill(email)
  await page.getByLabel('Senha', { exact: true }).fill('Synthetic-passphrase!')
  await page.getByLabel('Confirmar senha', { exact: true }).fill('Synthetic-passphrase!')
  await click(page.getByRole('button', { name: 'Criar conta', exact: true }))
  await page.waitForURL('**/new-transcription')
  await waitText('Preferências da transcrição')
  check(await page.getByRole('button', { name: 'Transcrição do Beta', exact: true }).isDisabled(), 'New account must not have platform permission')
  record('Cadastro sem concessão automática')
  // Admin acts through the real HTTP API; only the Firebase SDK boundary is fake.
  const adminLogin = await page.request.post(`${api}/auth/login`, { data: { username: 'synthetic-admin', password: 'Synthetic-only-passphrase!' } })
  check(adminLogin.ok(), 'Synthetic admin login failed')
  const admin = await adminLogin.json()
  const adminHeaders = { Authorization: `Bearer ${admin.access_token}` }
  const accounts = await page.request.get(`${api}/admin/settings/accounts?q=${persona}`, { headers: adminHeaders })
  const accountData = await accounts.json()
  const accountsList = accountData.items
  const member = accountsList.find(item => item.email === email)
  check(member, 'Admin search must find the newly created internal account')
  const granted = await page.request.post(`${api}/admin/accounts/${member.user_id}/beta`, { headers: adminHeaders,
    data: { capabilities: ['transcription.platform', 'intelligence.platform'], round_id: 'test-round', expires_at: new Date(Date.now() + 3600000).toISOString() } })
  check(granted.status() === 201, 'Explicit synthetic beta grant failed')
  await page.reload()
  await click(page.getByRole('button', { name: 'Transcrição do Beta', exact: true }))
  record('Concessão explícita e seleção de plataforma')
  const wav = Buffer.alloc(44 + 8000 * 2 * 40)
  wav.write('RIFF'); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8)
  wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22)
  wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28); wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34)
  wav.write('data', 36); wav.writeUInt32LE(wav.length - 44, 40)
  await page.locator('input[type=file]').setInputFiles({ name: filename, mimeType: 'audio/wav', buffer: wav })
  const submit = page.getByRole('button', { name: /Iniciar Transcrição/i }).last()
  await click(submit)
  await page.waitForURL(/\/transcriptions\/\d+$/, { timeout: 20000 })
  const id = new URL(page.url()).pathname.split('/').pop()
  record('Upload e processamento')
  await page.reload()
  await waitText('Decidimos publicar o guia')
  check(await page.getByText(filename, { exact: true }).count() > 0, 'Original filename lost')
  record('Resultado após refresh')
  await page.goto(`${base}/meetings/${id}`)
  await click(page.getByRole('button', { name: 'Gerar resumo', exact: true }))
  await waitText('O grupo decidiu publicar')
  await page.reload()
  await waitText('O grupo decidiu publicar')
  record('Resumo persistido')
  await click(page.getByRole('tab', { name: 'Decisões', exact: true }))
  await waitText('Publicar o guia de integração em português.')
  await click(page.getByRole('tab', { name: 'Tarefas', exact: true }))
  await waitText('Revisar o guia.')
  await click(page.getByRole('button', { name: 'Aceitar', exact: true }).first())
  await page.getByRole('button', { name: 'Concluir', exact: true }).first().waitFor()
  record('Decisão e tarefa aceita')
  await page.screenshot({ path: `.local-artifacts/beta-e2e-${mobile ? 'mobile-flow' : 'desktop'}.png`, fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: '.local-artifacts/beta-e2e-mobile.png', fullPage: true })
  check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Horizontal overflow on mobile')
  await click(page.getByRole('button', { name: 'Abrir navegação', exact: true }))
  check(await page.getByRole('link', { name: 'Administração', exact: true }).count() === 0, 'Member must not see admin')
  await click(page.getByRole('button', { name: 'Área da conta', exact: true }).last())
  await click(page.getByRole('button', { name: 'Sair', exact: true }).last())
  await page.goto(`${base}/login?returnTo=${encodeURIComponent(`/meetings/${id}`)}`)
  await page.getByLabel('E-mail', { exact: true }).fill(email)
  await page.getByLabel('Senha', { exact: true }).fill('Synthetic-passphrase!')
  await click(page.getByRole('button', { name: 'Entrar', exact: true }))
  await page.waitForURL(`**/meetings/${id}`)
  await waitText('O grupo decidiu publicar')
  await page.goto(`${base}/meetings`)
  await click(page.getByRole('link', { name: /Reunião sintética/ }).first())
  await page.waitForURL(`**/meetings/${id}`)
  await click(page.getByRole('tab', { name: 'Tarefas', exact: true }))
  await page.getByRole('button', { name: 'Concluir', exact: true }).first().waitFor()
  await page.reload()
  await waitText('O grupo decidiu publicar')
  record('Logout, login, contexto e persistência mobile')
  check(events.filter(item => item.path === '/transcriptions/jobs' && item.status === 202).length === 1,
    'Exactly one upload submission must be authorized')
  check(errors.length === 0, 'Unexpected JavaScript error')
  return { id, viewport: mobile ? 'mobile-full' : 'desktop', clicks, stages, javascriptErrors: errors, networkErrors: events.filter(item => item.status >= 400) }
}
