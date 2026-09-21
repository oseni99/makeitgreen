import { useEffect, useReducer, useState } from 'react'

const languageLoaders: Record<string, () => Promise<unknown>> = {
  javascript: () => import('monaco-editor/languages/definitions/javascript/register'),
  json: () => import('monaco-editor/language/json/monaco.contribution'),
  markdown: () => import('monaco-editor/languages/definitions/markdown/register'),
  python: () => import('monaco-editor/languages/definitions/python/register'),
  typescript: () => import('monaco-editor/languages/definitions/typescript/register'),
}

const loadedLanguages = new Set(['plaintext'])
const pendingLanguages = new Map<string, Promise<void>>()

export function isMonacoLanguageLoaded(language: string): boolean {
  return loadedLanguages.has(language) || !(language in languageLoaders)
}

export function ensureMonacoLanguage(language: string): Promise<void> {
  if (isMonacoLanguageLoaded(language)) return Promise.resolve()

  const pending = pendingLanguages.get(language)
  if (pending) return pending

  const load = languageLoaders[language]()
    .then(() => {
      loadedLanguages.add(language)
      pendingLanguages.delete(language)
    })
    .catch((error: unknown) => {
      pendingLanguages.delete(language)
      throw error
    })
  pendingLanguages.set(language, load)
  return load
}

export function useMonacoLanguage(language: string): string | null {
  const [, languageLoaded] = useReducer((version: number) => version + 1, 0)
  const [failedLanguage, setFailedLanguage] = useState<string | null>(null)
  const ready = isMonacoLanguageLoaded(language)

  useEffect(() => {
    let cancelled = false
    if (ready) return

    void ensureMonacoLanguage(language).then(
      () => {
        if (!cancelled) languageLoaded()
      },
      () => {
        if (!cancelled) setFailedLanguage(language)
      },
    )
    return () => {
      cancelled = true
    }
  }, [language, ready])

  if (ready) return language
  if (failedLanguage === language) return 'plaintext'
  return null
}
