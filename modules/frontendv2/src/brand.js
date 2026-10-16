export const brand = Object.freeze({
  company: 'USAGI',
  jp: 'うさぎ',
  product: 'Transcrição',
  descriptor: 'Compreensão de reuniões',
})

export const browserTitle = `${brand.company} — ${brand.product}`

export function applyBrowserTitle(targetDocument = document) {
  targetDocument.title = browserTitle
}
