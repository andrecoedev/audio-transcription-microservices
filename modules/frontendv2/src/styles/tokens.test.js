// @vitest-environment node
import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'

const css = readFileSync(new URL('./tokens.css', import.meta.url), 'utf8')
const tokens = Object.fromEntries([...css.matchAll(/--usagi-([\w-]+):\s*(#[\da-f]{6});/g)]
  .map(([, name, value]) => [name, value]))
// RGB channels also support Tailwind's existing /opacity variants.
for (const [, name, channels] of css.matchAll(/--usagi-([\w-]+)-rgb:\s*([\d ]+);/g)) {
  tokens[name] = '#' + channels.trim().split(/\s+/).map(value => Number(value).toString(16).padStart(2, '0')).join('')
}
function luminance(hex) {
  const linear = hex.match(/[\da-f]{2}/g).map(value => parseInt(value, 16) / 255)
    .map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
  return linear.reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0)
}
it.each([
  ['ink', 'canvas'], ['text-secondary', 'canvas'], ['muted', 'canvas'],
  ['muted', 'shell'], ['muted', 'surface-secondary'], ['on-primary', 'primary'],
  ['on-primary', 'primary-hover'], ['success', 'success-soft'],
  ['warning', 'warning-soft'], ['danger', 'danger-soft'], ['info', 'info-soft'],
])('keeps normal %s text readable on %s', (foreground, background) => {
  const [bright, dark] = [luminance(tokens[foreground]), luminance(tokens[background])].sort((a, b) => b - a)
  expect((bright + 0.05) / (dark + 0.05)).toBeGreaterThanOrEqual(4.5)
})

it('gives controls a distinguishable boundary on their white surface', () => {
  expect((luminance(tokens.surface) + 0.05) / (luminance(tokens['control-border']) + 0.05)).toBeGreaterThanOrEqual(3)
})
