import { expect, it, vi } from 'vitest'

const loaderConfig = vi.hoisted(() => vi.fn())
const localMonaco = vi.hoisted(() => ({ editor: {} }))
const languageRegistrations = vi.hoisted(() => ({
  javascript: vi.fn(),
  markdown: vi.fn(),
  python: vi.fn(),
  typescript: vi.fn(),
}))

vi.mock('@monaco-editor/react', () => ({
  loader: { config: loaderConfig },
}))
vi.mock('monaco-editor/editor/editor.api', () => localMonaco)
vi.mock('monaco-editor/languages/definitions/javascript/register', () => {
  languageRegistrations.javascript()
  return {}
})
vi.mock('monaco-editor/languages/definitions/markdown/register', () => {
  languageRegistrations.markdown()
  return {}
})
vi.mock('monaco-editor/languages/definitions/python/register', () => {
  languageRegistrations.python()
  return {}
})
vi.mock('monaco-editor/languages/definitions/typescript/register', () => {
  languageRegistrations.typescript()
  return {}
})
vi.mock('monaco-editor/language/json/monaco.contribution', () => ({}))

class EditorWorker {}
class JsonWorker {}

vi.mock('monaco-editor/editor/editor.worker?worker', () => ({ default: EditorWorker }))
vi.mock('monaco-editor/language/json/json.worker?worker', () => ({ default: JsonWorker }))

it('uses the bundled Monaco instance and bundled language workers', async () => {
  await import('../src/monacoSetup')

  expect(loaderConfig).toHaveBeenCalledWith({ monaco: localMonaco })
  expect(languageRegistrations.javascript).toHaveBeenCalledOnce()
  expect(languageRegistrations.markdown).toHaveBeenCalledOnce()
  expect(languageRegistrations.python).toHaveBeenCalledOnce()
  expect(languageRegistrations.typescript).toHaveBeenCalledOnce()

  const environment = self.MonacoEnvironment
  expect(environment?.getWorker?.('', 'json')).toBeInstanceOf(JsonWorker)
  expect(environment?.getWorker?.('', 'javascript')).toBeInstanceOf(EditorWorker)
  expect(environment?.getWorker?.('', 'typescript')).toBeInstanceOf(EditorWorker)
  expect(environment?.getWorker?.('', 'python')).toBeInstanceOf(EditorWorker)
})
