import { expect, it, vi } from 'vitest'

const loaderConfig = vi.hoisted(() => vi.fn())
const localMonaco = vi.hoisted(() => ({ editor: {} }))

vi.mock('@monaco-editor/react', () => ({
  loader: { config: loaderConfig },
}))
vi.mock('monaco-editor/editor/editor.api', () => localMonaco)

class EditorWorker {}
class JsonWorker {}

vi.mock('monaco-editor/editor/editor.worker?worker', () => ({ default: EditorWorker }))
vi.mock('monaco-editor/language/json/json.worker?worker', () => ({ default: JsonWorker }))

it('uses the bundled Monaco instance and bundled language workers', async () => {
  await import('../src/monacoSetup')

  expect(loaderConfig).toHaveBeenCalledWith({ monaco: localMonaco })

  const environment = self.MonacoEnvironment
  expect(environment?.getWorker?.('', 'json')).toBeInstanceOf(JsonWorker)
  expect(environment?.getWorker?.('', 'javascript')).toBeInstanceOf(EditorWorker)
  expect(environment?.getWorker?.('', 'typescript')).toBeInstanceOf(EditorWorker)
  expect(environment?.getWorker?.('', 'python')).toBeInstanceOf(EditorWorker)
})
