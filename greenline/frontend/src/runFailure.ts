export function formatRunFailureOutput(
  message: string,
  streamedOutput = '',
  hosted = import.meta.env.PROD,
): string {
  const sections = []
  const partialOutput = streamedOutput.trim()
  if (partialOutput) sections.push(partialOutput)
  sections.push('The test run could not be completed.', message)
  sections.push(
    hosted
      ? 'Your code is saved. Try running the tests again. If the problem continues, contact support and include the time of the failed run.'
      : 'Check that uvicorn is running on http://127.0.0.1:8000 and open the app through http://localhost:5173 so Vite can proxy /api.',
  )
  return sections.join('\n\n')
}
