import { useEffect, useState } from 'react'

import { apiFetch } from '../lib/api.js'

function dateParts(value) {
  const date = new Date(value)
  if (!value || Number.isNaN(date.getTime())) {
    return { day: '--', month: '' }
  }

  return {
    day: String(date.getDate()).padStart(2, '0'),
    month: date.toLocaleDateString(undefined, { month: 'short' }),
  }
}

function relativeDate(value) {
  if (!value) {
    return 'Unknown date'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'Unknown date'
  }

  const diffMs = Date.now() - date.getTime()
  const diffSeconds = Math.max(0, Math.floor(diffMs / 1000))
  const diffMinutes = Math.floor(diffSeconds / 60)
  const diffHours = Math.floor(diffMinutes / 60)
  const diffDays = Math.floor(diffHours / 24)
  const diffWeeks = Math.floor(diffDays / 7)
  const diffMonths = Math.floor(diffDays / 30)
  const diffYears = Math.floor(diffDays / 365)

  if (diffSeconds < 60) {
    return 'Just now'
  }
  if (diffMinutes < 60) {
    return `${diffMinutes} minute${diffMinutes === 1 ? '' : 's'} ago`
  }
  if (diffHours < 24) {
    return `${diffHours} hour${diffHours === 1 ? '' : 's'} ago`
  }
  if (diffDays < 7) {
    return `${diffDays} day${diffDays === 1 ? '' : 's'} ago`
  }
  if (diffWeeks < 5) {
    return `${diffWeeks} week${diffWeeks === 1 ? '' : 's'} ago`
  }
  if (diffMonths < 12) {
    return `${diffMonths} month${diffMonths === 1 ? '' : 's'} ago`
  }
  return `${diffYears} year${diffYears === 1 ? '' : 's'} ago`
}

function Dashboard({ onRecordDream, refreshKey = 0 }) {
  const [dreams, setDreams] = useState([])
  const [selectedDream, setSelectedDream] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    const controller = new AbortController()

    async function loadDreams() {
      setIsLoading(true)
      setErrorMessage('')

      try {
        const response = await apiFetch('/v1/dreams', {
          signal: controller.signal,
        })
        const data = await response.json()

        if (!response.ok) {
          throw new Error(data?.detail || `Request failed with status ${response.status}`)
        }

        setDreams(Array.isArray(data) ? data : [])
      } catch (error) {
        if (error.name !== 'AbortError') {
          setErrorMessage(error.message || 'Could not load dream journal.')
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
        }
      }
    }

    loadDreams()
    return () => controller.abort()
  }, [refreshKey])

  async function handleDeleteDream(dreamId) {
    await apiFetch(`/v1/dreams/${encodeURIComponent(dreamId)}`, {
      method: 'DELETE',
    })
    setDreams((currentDreams) => currentDreams.filter((dream) => dream.id !== dreamId))
    setSelectedDream((currentDream) => (
      currentDream?.id === dreamId ? null : currentDream
    ))
  }

  return (
    <main className="relative min-h-screen bg-[#0f0f0f] px-4 pb-28 pt-28 text-[#E6DFA9] transition-opacity duration-300 sm:px-6 lg:px-8">
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-4">
        {errorMessage ? (
          <p className="rounded-xl border border-[#1f1f1f] bg-[#141414] p-4 text-[#E6DFA9]">
            {errorMessage}
          </p>
        ) : null}

        {isLoading ? <SkeletonGrid /> : null}

        {!isLoading && !errorMessage && dreams.length === 0 ? (
          <EmptyState onRecord={onRecordDream} />
        ) : null}

        {!isLoading && dreams.length > 0 ? (
          <div className="grid min-w-0 grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {dreams.map((dream) => (
              <DreamCard
                key={dream.id}
                dream={dream}
                onOpen={() => setSelectedDream(dream)}
                onDelete={handleDeleteDream}
              />
            ))}
          </div>
        ) : null}
      </section>

      {selectedDream ? (
        <DreamModal
          dream={selectedDream}
          onClose={() => setSelectedDream(null)}
        />
      ) : null}
    </main>
  )
}

function SkeletonGrid() {
  return (
    <div className="grid min-w-0 grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="relative animate-pulse pt-5">
          <div className="relative min-h-64 rounded-[1.75rem] bg-[#1a1a1a] px-11 pb-8 pt-18">
            <div className="space-y-3">
              <div className="h-5 rounded bg-[#262626]" />
              <div className="h-5 w-2/3 rounded bg-[#262626]" />
            </div>
          </div>
          <span className="absolute right-0 top-0 h-12 w-[52%] rounded-tl-[0.875rem] rounded-tr-[1.75rem] bg-[#1a1a1a]" />
          <span className="absolute right-[52%] top-1 h-4 w-4 bg-[radial-gradient(circle_at_0_0,transparent_15.5px,#1a1a1a_16px)]" />
          <div className="absolute right-7 top-8 z-10 h-8 w-20 rounded bg-[#262626]" />
        </div>
      ))}
    </div>
  )
}

function EmptyState({ onRecord }) {
  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center rounded-xl border border-[#1f1f1f] bg-[#141414] p-8 text-center">
      <p className="mb-6 text-2xl font-semibold text-[#E6DFA9]">
        Record your first dream to begin
      </p>
      <button
        type="button"
        onClick={onRecord}
        className="rounded-xl border border-[#FFDE6E] bg-[#FFDE6E] px-5 py-3 font-black text-[#0f0f0f] transition hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
      >
        Record Dream
      </button>
    </div>
  )
}

function TrashIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
    >
      <path d="M3 6h18" />
      <path d="M8 6V4h8v2" />
      <path d="M19 6l-1 14H6L5 6" />
      <path d="M10 11v5" />
      <path d="M14 11v5" />
    </svg>
  )
}

function DreamCard({ dream, onOpen, onDelete }) {
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  async function confirmDelete() {
    setIsDeleting(true)
    setDeleteError('')

    try {
      await onDelete(dream.id)
    } catch (error) {
      setDeleteError(error.message || 'Could not delete this dream.')
      setIsDeleting(false)
    }
  }

  const { day, month } = dateParts(dream.created_at)

  return (
    <article className="group relative min-w-0 pt-5 transition hover:-translate-y-0.5">
      <div className="relative flex min-h-64 flex-col rounded-[1.75rem] bg-[#1a1a1a] px-11 pb-8 pt-18">
        <div className="mt-auto flex items-end justify-between gap-3">
          <button
            type="button"
            onClick={onOpen}
            className="min-w-0 flex-1 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
          >
            <h2 className="line-clamp-3 text-lg font-bold leading-[1.35] text-[#F7F7F5] [overflow-wrap:anywhere]">
              {dream.title || 'Untitled Dream'}
            </h2>
          </button>
          <button
            type="button"
            onClick={() => {
              setIsConfirmingDelete(true)
              setDeleteError('')
            }}
            className="rounded-lg p-1.5 text-[#8E8E88] opacity-0 transition hover:bg-[#262626] hover:text-[#F7F7F5] group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
            aria-label={`Delete ${dream.title || 'dream'}`}
          >
            <TrashIcon />
          </button>
        </div>

        {isConfirmingDelete ? (
          <div className="mt-5 border-t border-[#262626] pt-4">
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <button
                type="button"
                onClick={confirmDelete}
                disabled={isDeleting}
                className="font-bold text-[#F7F7F5] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
              >
                {isDeleting ? 'Deleting...' : 'Confirm'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsConfirmingDelete(false)
                  setDeleteError('')
                }}
                disabled={isDeleting}
                className="text-[#8E8E88] transition hover:text-[#F7F7F5] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
              >
                Cancel
              </button>
            </div>
            {deleteError ? (
              <p className="mt-3 text-sm text-[#F7F7F5]">
                {deleteError}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>

      <span
        aria-hidden="true"
        className="pointer-events-none absolute right-0 top-0 h-12 w-[52%] rounded-tl-[0.875rem] rounded-tr-[1.75rem] bg-[#1a1a1a]"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute right-[52%] top-1 h-4 w-4 bg-[radial-gradient(circle_at_0_0,transparent_15.5px,#1a1a1a_16px)]"
      />
      <p className="pointer-events-none absolute right-7 top-8 z-10 flex items-baseline gap-2">
        <span className="text-3xl font-bold leading-none text-[#F7F7F5]">{day}</span>
        <span className="text-sm text-[#8E8E88]">{month}</span>
      </p>
    </article>
  )
}

function DreamModal({ dream, onClose }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#0f0f0f]/95 px-4 py-8"
      role="dialog"
      aria-modal="true"
      aria-labelledby="dream-modal-title"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full min-w-0 max-w-[calc(100vw-2rem)] overflow-x-hidden overflow-y-auto rounded-xl border border-[#1f1f1f] bg-[#141414] p-6 shadow-2xl sm:max-w-3xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 id="dream-modal-title" className="text-3xl font-semibold text-[#FFDE6E] [overflow-wrap:anywhere]">
              {dream.title || 'Untitled Dream'}
            </h2>
            <p className="mt-2 text-sm font-bold text-[#8A7129]">
              {relativeDate(dream.created_at)}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-[#1f1f1f] px-3 py-2 font-bold text-[#E6DFA9] transition hover:border-[#8A7129] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
            aria-label="Close dream analysis"
          >
            Close
          </button>
        </div>
        {dream.raw_text ? (
          <div className="mb-6">
            <p className="mb-2 text-sm font-bold text-[#8A7129]">Your dream</p>
            <p className="whitespace-pre-wrap text-base leading-7 text-[#E6DFA9] [overflow-wrap:anywhere]">
              {dream.raw_text}
            </p>
          </div>
        ) : null}
        <div>
          <p className="mb-2 text-sm font-bold text-[#8A7129]">Analysis</p>
          <p className="whitespace-pre-wrap text-lg leading-8 text-[#E6DFA9] [overflow-wrap:anywhere]">
            {dream.analysis || 'No analysis available yet.'}
          </p>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
