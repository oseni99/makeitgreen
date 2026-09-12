import { expect, it, vi } from 'vitest'

const loaderConfig = vi.hoisted(() => vi.fn())
const localMonaco = vi.hoisted(() => ({ editor: {} }))

vi.mock('@monaco-editor/react', () => ({
  loader: { config: loaderConfig },
}))
vi.mock('monaco-editor', () => localMonaco)

class EditorWorker {}
class JsonWorker {}
class CssWorker {}
class HtmlWorker {}
class TypeScriptWorker {}

vi.mock('monaco-editor/editor/editor.worker?worker', () => ({ default: EditorWorker }))
vi.mock('monaco-editor/language/json/json.worker?worker', () => ({ default: JsonWorker }))
vi.mock('monaco-editor/language/css/css.worker?worker', () => ({ default: CssWorker }))
vi.mock('monaco-editor/language/html/html.worker?worker', () => ({ default: HtmlWorker }))
vi.mock('monaco-editor/language/typescript/ts.worker?worker', () => ({
  default: TypeScriptWorker,
}))

it('uses the bundled Monaco instance and bundled language workers', async () => {
  await import('../src/monacoSetup')

  expect(loaderConfig).toHaveBeenCalledWith({ monaco: localMonaco })

  const environment = self.MonacoEnvironment
  expect(environment?.getWorker?.('', 'json')).toBeInstanceOf(JsonWorker)
  expect(environment?.getWorker?.('', 'css')).toBeInstanceOf(CssWorker)
  expect(environment?.getWorker?.('', 'html')).toBeInstanceOf(HtmlWorker)
  expect(environment?.getWorker?.('', 'javascript')).toBeInstanceOf(TypeScriptWorker)
  expect(environment?.getWorker?.('', 'python')).toBeInstanceOf(EditorWorker)
})
