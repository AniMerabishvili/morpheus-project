import { Component, useEffect, useState } from 'react'
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'

import Dashboard from './components/Dashboard.jsx'
import MainGraph from './components/MainGraph.jsx'
import Logo from './components/Logo.jsx'
import VoiceRecorder from './components/VoiceRecorder.jsx'
import { useAuth } from './hooks/useAuth.js'
import AuthPage from './pages/AuthPage.jsx'
import CardPreview from './pages/CardPreview.jsx'

const SHARED_DREAM_KEY = 'morpheus-shared-dream'

// Capture text shared into the installed app (PWA share target) before auth routing,
// so it survives a sign-in redirect.
function captureSharedDream() {
  if (typeof window === 'undefined' || window.location.pathname !== '/share') return
  const params = new URLSearchParams(window.location.search)
  const text = [params.get('title'), params.get('text'), params.get('url')]
    .filter(Boolean)
    .join('\n\n')
    .trim()
    .slice(0, 20000)
  try {
    if (text) window.sessionStorage.setItem(SHARED_DREAM_KEY, text)
  } catch {
    // storage blocked — the share is dropped, app still opens
  }
  window.history.replaceState(null, '', '/')
}

captureSharedDream()

function takeSharedDream() {
  try {
    const text = window.sessionStorage.getItem(SHARED_DREAM_KEY) || ''
    window.sessionStorage.removeItem(SHARED_DREAM_KEY)
    return text
  } catch {
    return ''
  }
}

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </ErrorBoundary>
  )
}

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error) {
    console.error(error)
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="flex min-h-screen items-center justify-center bg-[#0f0f0f] px-6 text-center text-[#E6DFA9]">
          <p className="text-lg font-bold">Something went wrong. Refresh to continue.</p>
        </main>
      )
    }

    return this.props.children
  }
}

function AppShell() {
  const { loading, session, signOut } = useAuth()
  const [isRecorderOpen, setIsRecorderOpen] = useState(false)
  const [showToast, setShowToast] = useState(false)
  const [journalRefreshKey, setJournalRefreshKey] = useState(0)
  const [graphStats, setGraphStats] = useState({
    nodes: 0,
    dreams: 0,
    symbols: 0,
    links: 0,
  })
  const location = useLocation()
  const isAuthRoute = location.pathname === '/auth'

  const [sharedText, setSharedText] = useState('')

  useEffect(() => {
    setIsRecorderOpen(false)
  }, [location.pathname])

  // Runs after the effect above, so a shared note re-opens the recorder.
  useEffect(() => {
    if (!session) return
    const text = takeSharedDream()
    if (text) {
      setSharedText(text)
      setIsRecorderOpen(true)
    }
  }, [session])

  function handleDreamRecorded() {
    setJournalRefreshKey((key) => key + 1)
    setShowToast(true)
    window.setTimeout(() => setShowToast(false), 3000)
  }

  async function handleSignOut() {
    await signOut()
    window.location.assign('/auth')
  }

  if (location.pathname === '/__card-preview') {
    return <CardPreview />
  }

  if (loading) {
    return <AuthLoadingScreen />
  }

  if (!session) {
    return (
      <Routes>
        <Route path="/auth" element={<AuthPage />} />
        <Route path="*" element={<Navigate to="/auth" replace />} />
      </Routes>
    )
  }

  if (isAuthRoute) {
    return <Navigate to="/" replace />
  }

  return (
    <>
      <AppNavigation onRecordDream={() => setIsRecorderOpen(true)} onSignOut={handleSignOut} />

      <div className="min-h-screen bg-[#0f0f0f] transition-opacity duration-300">
        <Routes>
          <Route
            path="/"
            element={
              <Dashboard
                onRecordDream={() => setIsRecorderOpen(true)}
                refreshKey={journalRefreshKey}
              />
            }
          />
          <Route
            path="/graph"
            element={<MainGraph stats={graphStats} onStatsChange={setGraphStats} />}
          />
          <Route path="/auth" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>

      <button
        type="button"
        onClick={() => setIsRecorderOpen(true)}
        className="fixed bottom-24 right-5 z-40 flex h-14 w-14 items-center justify-center rounded-full border border-[#FFDE6E] bg-[#FFDE6E] text-[#0f0f0f] shadow-2xl transition hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E] md:hidden"
        aria-label="Record dream"
      >
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z" />
          <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
          <path d="M12 19v3" />
        </svg>
      </button>

      {isRecorderOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0f0f0f]/95 p-4 opacity-100 transition-opacity duration-300">
          <div className="no-scrollbar relative max-h-[92dvh] w-full max-w-xl overflow-y-auto">
            <button
              type="button"
              onClick={() => {
                setIsRecorderOpen(false)
                setSharedText('')
              }}
              className="absolute right-4 top-4 z-10 flex h-8 w-8 items-center justify-center rounded-full border border-[#2a2a27] bg-[#141414] text-lg leading-none text-[#9b9164] transition hover:border-[#8A7129] hover:text-[#FFDE6E] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
              aria-label="Close recorder"
            >
              ×
            </button>
            <VoiceRecorder
              initialText={sharedText}
              onDreamRecorded={handleDreamRecorded}
              onClose={() => {
                setIsRecorderOpen(false)
                setSharedText('')
              }}
            />
          </div>
        </div>
      ) : null}

      <div
        className={`fixed left-1/2 top-20 z-[60] -translate-x-1/2 rounded-xl border border-[#8A7129] bg-[#141414] px-5 py-3 font-black text-[#FFDE6E] shadow-2xl transition-all duration-500 ${
          showToast ? 'translate-y-0 opacity-100' : '-translate-y-3 opacity-0 pointer-events-none'
        }`}
      >
        Dream recorded ✦
      </div>
    </>
  )
}

function AuthLoadingScreen() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#0f0f0f]">
      <div
        className="h-12 w-12 animate-spin rounded-full border-2 border-[#1f1f1f] border-t-[#FFDE6E]"
        aria-label="Loading session"
        role="status"
      />
    </main>
  )
}

const icon = {
  width: 18,
  height: 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.7,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
}

function JournalIcon() {
  return (
    <svg {...icon}>
      <path d="M5 4.5A1.5 1.5 0 0 1 6.5 3H19v15H6.5A1.5 1.5 0 0 0 5 19.5v-15Z" />
      <path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19v-3M9 7.5h6" />
    </svg>
  )
}

function GraphIcon() {
  return (
    <svg {...icon}>
      <circle cx="6" cy="7" r="2.2" />
      <circle cx="18" cy="6" r="2.2" />
      <circle cx="12" cy="17.5" r="2.2" />
      <path d="M8 8.2l2.9 7.3M16.6 7.7l-3.5 7.9M8.2 6.8l7.6-.6" />
    </svg>
  )
}

function SignOutIcon() {
  return (
    <svg {...icon}>
      <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 16l-4-4 4-4M6 12h10" />
    </svg>
  )
}

function MicIcon({ size = 15 }) {
  return (
    <svg {...icon} width={size} height={size} strokeWidth={2}>
      <path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3" />
    </svg>
  )
}

const focusRing =
  'focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]'

function AppNavigation({ onRecordDream, onSignOut }) {
  const linkClass = ({ isActive }) =>
    `rounded-full px-3.5 py-1.5 text-[13px] font-medium transition ${focusRing} ${
      isActive
        ? 'bg-[#FFDE6E]/[0.12] text-[#FFDE6E]'
        : 'text-[#E6DFA9]/65 hover:text-[#E6DFA9]'
    }`

  const mobileLinkClass = ({ isActive }) =>
    `flex flex-1 flex-col items-center justify-center gap-1 py-2.5 text-[11px] font-medium transition ${
      isActive ? 'text-[#FFDE6E]' : 'text-[#E6DFA9]/60'
    }`

  return (
    <>
      <nav className="fixed left-0 top-0 z-40 w-full border-b border-white/[0.06] bg-[#0f0f0f]/75 backdrop-blur-xl">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-5">
          <NavLink to="/" className={`rounded-md ${focusRing}`} aria-label="Morpheus home">
            <Logo />
          </NavLink>

          <div className="hidden items-center gap-3 md:flex">
            <div className="flex items-center gap-0.5 rounded-full border border-[#1f1f1f] bg-[#121212] p-1">
              <NavLink to="/" end className={linkClass}>
                Journal
              </NavLink>
              <NavLink to="/graph" className={linkClass}>
                Graph
              </NavLink>
            </div>
            <button
              type="button"
              onClick={onRecordDream}
              className={`flex items-center gap-1.5 rounded-full bg-[#FFDE6E] px-4 py-2 text-[13px] font-semibold text-[#0f0f0f] transition hover:brightness-105 active:scale-[0.98] ${focusRing}`}
            >
              <MicIcon />
              Record dream
            </button>
            <button
              type="button"
              onClick={onSignOut}
              title="Sign out"
              aria-label="Sign out"
              className={`flex h-9 w-9 items-center justify-center rounded-full text-[#E6DFA9]/55 transition hover:bg-white/[0.05] hover:text-[#E6DFA9] ${focusRing}`}
            >
              <SignOutIcon />
            </button>
          </div>
        </div>
      </nav>

      <nav className="fixed bottom-0 left-0 z-40 grid w-full grid-cols-3 border-t border-white/[0.06] bg-[#0f0f0f]/85 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden">
        <NavLink to="/" end className={mobileLinkClass}>
          <JournalIcon />
          Journal
        </NavLink>
        <NavLink to="/graph" className={mobileLinkClass}>
          <GraphIcon />
          Graph
        </NavLink>
        <button
          type="button"
          onClick={onSignOut}
          className="flex flex-1 flex-col items-center justify-center gap-1 py-2.5 text-[11px] font-medium text-[#E6DFA9]/60 transition hover:text-[#E6DFA9]"
        >
          <SignOutIcon />
          Sign out
        </button>
      </nav>
    </>
  )
}

export default App
