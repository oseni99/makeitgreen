import { expect, it, vi } from 'vitest'

const registrations = vi.hoisted(() => ({
  javascript: vi.fn(),
  json: vi.fn(),
  markdown: vi.fn(),
  python: vi.fn(),
  typescript: vi.fn(),
}))

vi.mock('monaco-editor/languages/definitions/javascript/register', () => {
  registrations.javascript()
  return {}
})
vi.mock('monaco-editor/language/json/monaco.contribution', () => {
  registrations.json()
  return {}
})
vi.mock('monaco-editor/languages/definitions/markdown/register', () => {
  registrations.markdown()
  return {}
})
vi.mock('monaco-editor/languages/definitions/python/register', () => {
  registrations.python()
  return {}
})
vi.mock('monaco-editor/languages/definitions/typescript/register', () => {
  registrations.typescript()
  return {}
})

it('loads and caches only the requested Monaco language', async () => {
  const { ensureMonacoLanguage, isMonacoLanguageLoaded } = await import(
    '../src/monacoLanguages'
  )

  expect(isMonacoLanguageLoaded('plaintext')).toBe(true)
  expect(isMonacoLanguageLoaded('python')).toBe(false)
  expect(registrations.python).not.toHaveBeenCalled()
  expect(registrations.javascript).not.toHaveBeenCalled()

  await ensureMonacoLanguage('python')
  await ensureMonacoLanguage('python')

  expect(isMonacoLanguageLoaded('python')).toBe(true)
  expect(registrations.python).toHaveBeenCalledOnce()
  expect(registrations.javascript).not.toHaveBeenCalled()

  await ensureMonacoLanguage('javascript')

  expect(registrations.javascript).toHaveBeenCalledOnce()
  expect(registrations.json).not.toHaveBeenCalled()
  expect(registrations.markdown).not.toHaveBeenCalled()
  expect(registrations.typescript).not.toHaveBeenCalled()
})
