// Books from Morpheus's RAG library that the dreamer reads their dreams through.
import { apiFetch } from './api.js'

const STORAGE_KEY = 'morpheus-books'
let libraryPromise = null

/** Books available in the knowledge base: [{ id, title, author, passages }]. Cached per session. */
export function fetchLibrary() {
  if (!libraryPromise) {
    libraryPromise = apiFetch('/v1/library')
      .then((response) => response.json())
      .then((books) => (Array.isArray(books) ? books : []))
      .catch((error) => {
        libraryPromise = null
        throw error
      })
  }
  return libraryPromise
}

export function loadSavedBooks() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(saved) ? saved.filter((id) => typeof id === 'string') : []
  } catch {
    return []
  }
}

export function saveBooks(ids) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
  } catch {
    // storage unavailable — selection still applies to this dream
  }
}
