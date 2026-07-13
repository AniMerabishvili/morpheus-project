import { supabase } from './supabase.js'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

function buildApiUrl(path) {
  if (/^https?:\/\//i.test(path)) {
    return path
  }

  return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

async function redirectToAuth() {
  await supabase.auth.signOut()

  if (window.location.pathname !== '/auth') {
    window.location.assign('/auth')
  }
}

export async function apiFetch(path, options = {}) {
  const {
    headers,
    ...fetchOptions
  } = options
  const { data, error } = await supabase.auth.getSession()
  if (error) {
    await redirectToAuth()
    throw new Error('Your session expired. Please sign in again.')
  }

  const token = data.session?.access_token

  if (!token) {
    await redirectToAuth()
    throw new Error('Authentication required.')
  }

  const requestHeaders = new Headers(headers || {})
  requestHeaders.set('Authorization', `Bearer ${token}`)

  const response = await fetch(buildApiUrl(path), {
    ...fetchOptions,
    headers: requestHeaders,
  })

  if (response.status === 401) {
    await redirectToAuth()
    throw new Error('Your session expired. Please sign in again.')
  }

  if (!response.ok) {
    let detail = `Request failed: ${response.status}`
    try {
      const body = await response.json()
      if (body?.detail) detail = body.detail
    } catch {
      // non-JSON error body — keep the status message
    }
    throw new Error(detail)
  }

  return response
}
