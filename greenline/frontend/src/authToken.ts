type TokenProvider = () => Promise<string | null>

let tokenProvider: TokenProvider | null = null

export function setAuthTokenProvider(provider: TokenProvider | null): void {
  tokenProvider = provider
}

export async function getAuthToken(): Promise<string | null> {
  return tokenProvider ? tokenProvider() : null
}
