import type { Monaco } from '@monaco-editor/react'

function cssColor(name: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  if (!value) throw new Error(`Missing CSS color token ${name}`)
  return value
}

function tokenColor(name: string): string {
  return cssColor(name).replace(/^#/, '')
}

export function defineGreenlineTheme(monaco: Monaco) {
  monaco.editor.defineTheme('greenline', {
    base: 'vs-dark',
    inherit: true,
    rules: [
      { token: 'comment', foreground: tokenColor('--editor-comment'), fontStyle: 'italic' },
      { token: 'string', foreground: tokenColor('--editor-string') },
      { token: 'keyword', foreground: tokenColor('--editor-keyword') },
      { token: 'number', foreground: tokenColor('--editor-number') },
    ],
    colors: {
      'editor.background': cssColor('--editor-background'),
      'editor.foreground': cssColor('--editor-foreground'),
      'editor.lineHighlightBackground': cssColor('--editor-line-highlight'),
      'editorLineNumber.foreground': cssColor('--editor-line-number'),
      'editorCursor.foreground': cssColor('--editor-cursor'),
      'editor.selectionBackground': cssColor('--editor-selection'),
      'diffEditor.insertedTextBackground': cssColor('--editor-diff-inserted-text'),
      'diffEditor.removedTextBackground': cssColor('--editor-diff-removed-text'),
      'diffEditor.insertedLineBackground': cssColor('--editor-diff-inserted-line'),
      'diffEditor.removedLineBackground': cssColor('--editor-diff-removed-line'),
    },
  })
}
