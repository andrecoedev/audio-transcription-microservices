// Run after journey.playwright.js and the isolated server presentation command.
async (page) => {
  const base = 'http://127.0.0.1:4180'
  const login = async () => {
    await page.goto(`${base}/login?returnTo=%2Ftranscriptions`)
    await page.getByLabel('E-mail', { exact: true }).fill('member@example.invalid')
    await page.getByLabel('Senha', { exact: true }).fill('Synthetic-passphrase!')
    await page.getByRole('button', { name: 'Entrar', exact: true }).click()
    await page.waitForURL('**/transcriptions')
  }
  await login()
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('link', { name: 'Fixture sintética longa.wav', exact: true }).click()
  await page.getByText('Decidimos publicar o guia de integração em português.', { exact: true }).first().waitFor()
  const longId = new URL(page.url()).pathname.split('/').pop()
  await page.goto(`${base}/meetings/${longId}`)
  // UI currently uses aria-label on a generic scroll container, not region role.
  const transcript = page.locator('[aria-label="Trechos da transcrição"]')
  await transcript.locator('article').last().waitFor()
  if (await transcript.locator('article').count() !== 200) throw new Error('Long transcript truncated')
  await page.getByRole('tabpanel').getByText('Esta reunião ainda não tem resumo.', { exact: true }).waitFor()
  await transcript.evaluate(element => { element.scrollTop = element.scrollHeight })
  await page.screenshot({ path: 'docs/design/product-ux-copy/long-desktop.png', fullPage: false })
  await page.setViewportSize({ width: 390, height: 844 })
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Mobile overflow')
  await page.screenshot({ path: 'docs/design/product-ux-copy/long-mobile.png', fullPage: false })
  await page.goto(`${base}/transcriptions`)
  await page.getByRole('link', { name: 'Fixture sintética silêncio.wav', exact: true }).click()
  await page.getByRole('heading', { name: 'Transcrição completa', exact: true }).waitFor()
  const silenceText = await page.locator('main').innerText()
  if (!silenceText.includes('Nenhuma fala foi identificada neste áudio.')) throw new Error('Missing silence message')
  await page.getByText('Nenhuma fala foi identificada neste áudio.', { exact: true }).scrollIntoViewIfNeeded()
  await page.screenshot({ path: 'docs/design/product-ux-copy/silence-mobile.png', fullPage: false })
  const silentId = new URL(page.url()).pathname.split('/').pop()
  await page.goto(`${base}/meetings/${silentId}`)
  await page.getByText('Nenhuma fala foi identificada neste áudio.', { exact: true }).waitFor()
  await page.screenshot({ path: 'docs/design/product-ux-copy/silence-meeting-mobile.png', fullPage: false })
  await page.goto(`${base}/transcriptions`)
  await page.getByRole('link', { name: 'Fixture sintética falha.wav', exact: true }).click()
  await page.getByRole('alert').first().waitFor()
  const failure = await page.getByRole('alert').first().innerText()
  // A revoked/expired synthetic identity must not render protected content.
  await page.evaluate(() => localStorage.setItem('beta-e2e-synthetic-identity', JSON.stringify({ uid: 'member', token: 'beta-e2e-expired' })))
  await page.reload()
  await page.getByRole('heading', { name: 'Entre para continuar', exact: true }).waitFor()
  await login()
  await page.getByRole('link', { name: 'Reunião sintética – integração.wav', exact: true }).waitFor()
  await page.goto(`${base}/login?returnTo=%2Fnew-transcription`)
  await page.getByRole('button', { name: 'Continuar com Google', exact: true }).click()
  await page.waitForURL('**/new-transcription')
  await page.getByRole('button', { name: 'Transcrição do Beta', exact: true }).waitFor()
  const googleWithoutBeta = await page.getByRole('button', { name: 'Transcrição do Beta', exact: true }).isDisabled()
  if (!googleWithoutBeta) throw new Error('Google account received implicit Beta')
  return { longSegments: 200, silenceShowsEmptyMessage: /nenhum trecho|nenhuma fala|não foi detectada fala/i.test(silenceText),
    safeFailure: failure, expiredSessionBlocked: true, reauthenticationWorked: true,
    googleMockWithoutBeta: googleWithoutBeta }
}
