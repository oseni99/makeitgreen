import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const mainSource = await readFile(new URL('../src/main.tsx', import.meta.url), 'utf8')
const globalStyles = await readFile(
  new URL('../src/styles/globals.css', import.meta.url),
  'utf8',
)
const appSource = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8')
const landingSource = await readFile(new URL('../src/pages/Landing.tsx', import.meta.url), 'utf8')
const designSpec = await readFile(new URL('../../DESIGN.md', import.meta.url), 'utf8')
const indexSource = await readFile(new URL('../index.html', import.meta.url), 'utf8')
const socialImage = await readFile(
  new URL('../public/og-makeitgreen.png', import.meta.url),
)

test('Tailwind globals are the application stylesheet', () => {
  assert.doesNotMatch(mainSource, /import ['"]\.\/styles\.css['"]/, 'legacy CSS must remain unimported')
  assert.match(mainSource, /import ['"]\.\/styles\/globals\.css['"]/, 'Tailwind globals must be active')
})

test('primary navigation condenses to an accessible mobile menu', () => {
  assert.match(appSource, /aria-expanded=/)
  assert.match(appSource, /aria-controls=/)
  assert.match(appSource, /md:hidden/)
  assert.match(appSource, /hidden[^"']*md:(?:flex|inline-flex|block)/)
})

test('decorative landing chrome does not consume the primary action color', () => {
  assert.doesNotMatch(appSource, /MakeItGreen<span className="text-primary">/)
  assert.doesNotMatch(landingSource, /text-primary">0[123]</)
  assert.doesNotMatch(landingSource, /text-primary">LIVE</)
})

test('product semantic colors are part of the canonical design contract', () => {
  for (const color of ['#c9362b', '#16833d', '#a95c00']) {
    assert.match(designSpec, new RegExp(color), `missing semantic color ${color}`)
  }
  assert.match(designSpec, /restricted to product validation, status, and error chrome/)
})

test('Monaco tokens live in the active global theme', () => {
  for (const token of [
    '--editor-background',
    '--editor-foreground',
    '--editor-comment',
    '--editor-string',
    '--editor-keyword',
    '--editor-number',
    '--editor-selection',
  ]) {
    assert.match(globalStyles, new RegExp(`${token}:`), `missing ${token}`)
  }
})

test('social preview metadata uses the project-owned large image asset', () => {
  assert.match(indexSource, /property="og:image" content="\/og-makeitgreen\.png"/)
  assert.match(indexSource, /name="twitter:card" content="summary_large_image"/)
  assert.match(indexSource, /name="twitter:image" content="\/og-makeitgreen\.png"/)
  assert.ok(socialImage.byteLength > 10_000, 'social image must not be an empty placeholder')
})
