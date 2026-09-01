import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { JSDOM } from 'jsdom'

const indexSource = await readFile(new URL('../index.html', import.meta.url), 'utf8')
const socialImage = await readFile(
  new URL('../public/og-makeitgreen.png', import.meta.url),
)

test('social preview metadata uses the project-owned large image asset', () => {
  const document = new JSDOM(indexSource).window.document

  assert.equal(
    document.querySelector('meta[property="og:image"]')?.getAttribute('content'),
    '/og-makeitgreen.png',
  )
  assert.equal(
    document.querySelector('meta[name="twitter:card"]')?.getAttribute('content'),
    'summary_large_image',
  )
  assert.equal(
    document.querySelector('meta[name="twitter:image"]')?.getAttribute('content'),
    '/og-makeitgreen.png',
  )
  assert.ok(socialImage.byteLength > 10_000, 'social image must not be an empty placeholder')
})
