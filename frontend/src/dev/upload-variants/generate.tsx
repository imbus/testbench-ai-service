/* Throwaway: renders the upload dialog variants to static HTML pages.
   Run: npx vitest run --config src/dev/upload-variants/vitest.config.ts
   Output: OUT_DIR (default ../.superpowers/sdd/2026-11-18-upload-dialog-variants). */
import { copyFileSync, mkdirSync, readdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { renderToStaticMarkup } from 'react-dom/server'
import { it } from 'vitest'
import { STATES, VARIANTS } from './variants'

const ROOT = resolve(__dirname, '../../..')
const OUT = process.env.OUT_DIR ?? resolve(ROOT, '../.superpowers/sdd/2026-11-18-upload-dialog-variants')
const THEME = join(ROOT, 'node_modules/primereact/resources/themes/lara-light-amber')
const STYLES = join(ROOT, 'src/styles')
const CSS = ['theme.css', 'fonts.css', 'industry.css', 'brand.css', 'brand-orange.css', 'prime-bridge.css']

function copyAssets() {
  const assets = join(OUT, 'assets')
  mkdirSync(join(assets, 'fonts'), { recursive: true })
  copyFileSync(join(THEME, 'theme.css'), join(assets, 'theme.css'))
  for (const file of CSS.slice(1)) copyFileSync(join(STYLES, file), join(assets, file))
  for (const dir of [join(THEME, 'fonts'), join(STYLES, 'fonts')])
    for (const font of readdirSync(dir)) copyFileSync(join(dir, font), join(assets, 'fonts', font))
}

const PAGE_CSS = `
  body { margin: 0; background: var(--color-bg); color: var(--color-text); font-family: var(--font-body, inherit); }
  main { padding: 28px 32px 60px; display: flex; flex-direction: column; gap: 22px; }
  header.page h1 { margin: 0; font-family: var(--font-heading); font-size: 28px; }
  header.page p { margin: 4px 0 0; color: var(--color-muted); font-size: 13px; max-width: 900px; }
  nav.variants { display: flex; gap: 8px; flex-wrap: wrap; }
  nav.variants a { font-size: 13px; padding: 4px 10px; border: 1px solid var(--color-divider); border-radius: 999px; color: inherit; text-decoration: none; }
  nav.variants a.current { background: var(--color-text); color: var(--color-bg); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 900px), 1fr)); gap: 22px; }
  figure { margin: 0; display: flex; flex-direction: column; gap: 8px; }
  figcaption { font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--color-muted); }
  figcaption a { color: inherit; }
  .mask { background: rgba(0,0,0,.42); border-radius: 10px; padding: 32px 24px; display: flex; justify-content: center; align-items: flex-start; overflow-x: auto; }
`

function page(title: string, intro: string, current: string, body: string) {
  const nav = [
    `<a href="index.html"${current === 'index' ? ' class="current"' : ''}>Übersicht</a>`,
    ...VARIANTS.map(
      (v) =>
        `<a href="variant-${v.key}.html"${current === v.key ? ' class="current"' : ''}>${v.name}</a>`,
    ),
  ].join('')
  const links = CSS.map((f) => `<link rel="stylesheet" href="assets/${f}">`).join('\n  ')
  return `<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${title}</title>
  ${links}
  <style>${PAGE_CSS}</style>
</head>
<body>
<main>
  <header class="page"><h1>${title}</h1><p>${intro}</p></header>
  <nav class="variants">${nav}</nav>
  ${body}
</main>
</body>
</html>
`
}

function frame(caption: string, html: string) {
  return `<figure><figcaption>${caption}</figcaption><div class="mask">${html}</div></figure>`
}

it('writes the variant pages', () => {
  copyAssets()
  for (const v of VARIANTS) {
    const frames = STATES.map((s) => frame(s.label, renderToStaticMarkup(<v.Component state={s.key} />)))
    writeFileSync(
      join(OUT, `variant-${v.key}.html`),
      page(v.name, v.pitch, v.key, `<div class="grid">${frames.join('\n')}</div>`),
    )
  }
  const overview = VARIANTS.map((v) =>
    frame(
      `<a href="variant-${v.key}.html">${v.name}</a> — ${v.pitch}`,
      renderToStaticMarkup(<v.Component state="result" />),
    ),
  )
  writeFileSync(
    join(OUT, 'index.html'),
    page(
      'Upload-Dialog · 5 Varianten',
      'Alle Varianten im Zustand „Prüfbericht mit Befunden“, gebaut aus PrimeReact-Komponenten mit dem Console-Theme (Lara Amber + brand + prime-bridge). Die Seiten der einzelnen Varianten zeigen alle vier Zustände.',
      'index',
      `<div class="grid">${overview.join('\n')}</div>`,
    ),
  )
})
