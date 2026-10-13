import { useEffect, useLayoutEffect, useRef, useState } from 'react'

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
                onOpen={(letterRect) => setSelectedDream({ dream, letterRect })}
                onDelete={handleDeleteDream}
              />
            ))}
          </div>
        ) : null}
      </section>

      {selectedDream ? (
        <DreamModal
          dream={selectedDream.dream}
          letterRect={selectedDream.letterRect}
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
          <span className="absolute inset-x-12 top-1 h-10 rounded-t-md bg-[#262520]" />
          <span className="absolute inset-x-8 top-2.5 h-10 rounded-t-lg bg-[#38362F]" />
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
  const letterRef = useRef(null)

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
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-12 top-1 h-10 rounded-t-md bg-[#262520] transition-transform duration-300 group-hover:-translate-y-1"
      />
      <span
        ref={letterRef}
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-8 top-2.5 h-10 rounded-t-lg bg-[#38362F] transition-transform duration-300 group-hover:-translate-y-2"
      />

      <button
        type="button"
        onClick={() => onOpen(letterRef.current?.getBoundingClientRect())}
        className="absolute inset-0 rounded-[1.75rem] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
        aria-label={`Open ${dream.title || 'dream'}`}
      />

      <div className="pointer-events-none relative flex min-h-64 flex-col rounded-[1.75rem] bg-[#1a1a1a] px-11 pb-8 pt-18">
        <div className="mt-auto flex items-end justify-between gap-3">
          <h2 className="line-clamp-3 min-w-0 flex-1 text-lg font-bold leading-[1.35] text-[#F7F7F5] [overflow-wrap:anywhere]">
            {dream.title || 'Untitled Dream'}
          </h2>
          <button
            type="button"
            onClick={() => {
              setIsConfirmingDelete(true)
              setDeleteError('')
            }}
            className="pointer-events-auto rounded-lg p-1.5 text-[#8E8E88] opacity-0 transition hover:bg-[#262626] hover:text-[#F7F7F5] group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
            aria-label={`Delete ${dream.title || 'dream'}`}
          >
            <TrashIcon />
          </button>
        </div>

        {isConfirmingDelete ? (
          <div className="pointer-events-auto mt-5 border-t border-[#262626] pt-4">
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

function DreamModal({ dream, letterRect, onClose }) {
  const sheetRef = useRef(null)
  const contentRef = useRef(null)

  // Slide the sheet out of the folder from where the card's letter sat, then unfold it.
  useLayoutEffect(() => {
    const sheet = sheetRef.current
    const content = contentRef.current
    if (!sheet || !content) {
      return
    }
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      return
    }

    const duration = 720
    const slideOut = 'cubic-bezier(0.33, 0, 0.67, 1)'
    const unfold = 'cubic-bezier(0.22, 1, 0.36, 1)'
    const target = sheet.getBoundingClientRect()
    const sheetFrames = []

    if (letterRect && target.width > 0 && target.height > 0) {
      const scaleX = letterRect.width / target.width
      const scaleY = letterRect.height / target.height
      const dx =
        letterRect.left + letterRect.width / 2 - (target.left + target.width / 2)
      const dy = letterRect.top - target.top
      // Keep the strip on screen for cards sitting near the top of the viewport.
      const slideDy = Math.max(8, letterRect.top - 44) - target.top

      sheetFrames.push(
        {
          offset: 0,
          transform: `translate(${dx}px, ${dy}px) scale(${scaleX}, ${scaleY})`,
          borderRadius: '0.5rem 0.5rem 0 0',
          easing: slideOut,
        },
        {
          offset: 0.34,
          transform: `translate(${dx}px, ${slideDy}px) scale(${scaleX}, ${scaleY})`,
          borderRadius: '0.5rem 0.5rem 0 0',
          easing: unfold,
        },
        { offset: 1, transform: 'none', borderRadius: '0.125rem' },
      )
    } else {
      sheetFrames.push(
        { offset: 0, transform: 'translateY(2rem) scaleY(0.88)', opacity: 0, easing: unfold },
        { offset: 1, transform: 'none', opacity: 1 },
      )
    }

    const sheetAnimation = sheet.animate(sheetFrames, {
      duration,
      easing: 'linear',
      fill: 'both',
    })
    const contentAnimation = content.animate(
      [
        { offset: 0, opacity: 0 },
        { offset: 0.52, opacity: 0 },
        { offset: 1, opacity: 1 },
      ],
      { duration, easing: 'linear', fill: 'both' },
    )

    return () => {
      sheetAnimation.cancel()
      contentAnimation.cancel()
    }
  }, [letterRect])

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [onClose])

  return (
    <div
      className="letter-backdrop fixed inset-0 z-50 flex items-center justify-center bg-[#0f0f0f]/90 p-4 sm:p-8"
      role="dialog"
      aria-modal="true"
      aria-labelledby="dream-modal-title"
      onClick={onClose}
    >
      <div
        ref={sheetRef}
        className="relative flex max-h-full w-full min-w-0 max-w-2xl origin-top flex-col rounded-sm border border-[#332F28] bg-[#1F1E1A] shadow-[0_30px_90px_rgba(0,0,0,0.75)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div ref={contentRef} className="flex min-h-0 flex-col">
          <button
            type="button"
            onClick={onClose}
            className="absolute right-4 top-4 z-10 flex h-9 w-9 items-center justify-center rounded-full bg-[#1F1E1A] text-xl leading-none text-[#8A857A] transition hover:bg-[#2C2A24] hover:text-[#F2EDE1] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8A857A]"
            aria-label="Close letter"
          >
            ×
          </button>

          <div className="min-h-0 overflow-y-auto px-7 py-9 sm:px-14 sm:py-14">
            <p className="text-[11px] uppercase tracking-[0.22em] text-[#8A857A]">
              {relativeDate(dream.created_at)}
            </p>
            <h2
              id="dream-modal-title"
              className="mt-3 text-2xl font-bold leading-snug text-[#F2EDE1] [overflow-wrap:anywhere] sm:text-3xl"
            >
              {dream.title || 'Untitled Dream'}
            </h2>

            {dream.raw_text ? (
              <div className="mt-9">
                <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.18em] text-[#8A857A]">
                  Your dream
                </p>
                <p className="whitespace-pre-wrap text-base leading-[1.8] text-[#BDB9AE] [overflow-wrap:anywhere]">
                  {dream.raw_text}
                </p>
              </div>
            ) : null}

            <div className="mt-9 border-t border-dashed border-[#352F28] pt-9">
              <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.18em] text-[#8A857A]">
                Interpretation
              </p>
              <p className="whitespace-pre-wrap text-base leading-[1.8] text-[#E2DDD2] [overflow-wrap:anywhere]">
                {dream.analysis || 'No analysis available yet.'}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
