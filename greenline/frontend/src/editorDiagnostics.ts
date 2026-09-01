import type { Monaco, OnMount } from '@monaco-editor/react'

import type { FileEntry, TestCase } from './api'

export const TEST_RESULT_MARKER_OWNER = 'makeitgreen-test-results'

export type WorkspaceEditor = Parameters<OnMount>[0]
export type PendingLocation = { path: string; line: number }

const SOURCE_EXTENSIONS = ['.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx']

export function selectInitialEditableFile(files: FileEntry[]): FileEntry | undefined {
  const editable = files.filter((file) => !file.readonly)
  return editable.find((file) =>
    SOURCE_EXTENSIONS.some((extension) => file.path.endsWith(extension)) &&
    !file.path.endsWith('conftest.py') &&
    !file.path.endsWith('__init__.py'),
  ) ?? editable[0]
}

function normalizePath(path: string): string {
  let decoded = path
  try {
    decoded = decodeURIComponent(path)
  } catch {
    // A malformed URI component is still safe to compare as plain text.
  }
  return decoded.replace(/\\/g, '/').replace(/^\/+/, '').replace(/^\.\//, '')
}

export function modelHasPath(editor: WorkspaceEditor, path: string): boolean {
  const modelPath = editor.getModel()?.uri.path
  return !!modelPath && normalizePath(modelPath) === normalizePath(path)
}

export function revealEditorLocation(
  editor: WorkspaceEditor,
  location: PendingLocation,
): boolean {
  const model = editor.getModel()
  if (!model || !modelHasPath(editor, location.path)) return false

  const line = Math.max(1, Math.min(location.line, model.getLineCount()))
  editor.revealLineInCenter(line)
  editor.setPosition({ lineNumber: line, column: 1 })
  editor.focus()
  return true
}

function failureLocation(test: TestCase): PendingLocation | null {
  if (test.outcome !== 'failed' && test.outcome !== 'error') return null
  if (test.crash_file && test.crash_line) {
    return { path: test.crash_file, line: test.crash_line }
  }
  if (test.file && test.line) return { path: test.file, line: test.line }
  return null
}

export function updateTestResultMarkers(
  monaco: Monaco,
  editor: WorkspaceEditor,
  tests: TestCase[],
): void {
  const model = editor.getModel()
  if (!model) return

  const modelPath = model.uri.path
  const markers = tests.flatMap((test) => {
    const location = failureLocation(test)
    if (!location || normalizePath(location.path) !== normalizePath(modelPath)) return []

    const line = Math.max(1, Math.min(location.line, model.getLineCount()))
    return [{
      severity: monaco.MarkerSeverity.Error,
      message: test.message.trim() || `${test.id} ${test.outcome}`,
      source: 'pytest',
      startLineNumber: line,
      startColumn: 1,
      endLineNumber: line,
      endColumn: model.getLineMaxColumn(line),
    }]
  })

  monaco.editor.setModelMarkers(model, TEST_RESULT_MARKER_OWNER, markers)
}
