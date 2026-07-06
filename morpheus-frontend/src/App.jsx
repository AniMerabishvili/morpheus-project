import { Component, useEffect, useState } from 'react'
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'

import Dashboard from './components/Dashboard.jsx'
import MainGraph from './components/MainGraph.jsx'
import VoiceRecorder from './components/VoiceRecorder.jsx'
import { useAuth } from './hooks/useAuth.js'
import AuthPage from './pages/AuthPage.jsx'

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

  useEffect(() => {
    setIsRecorderOpen(false)
  }, [location.pathname])

  function handleDreamRecorded() {
    setJournalRefreshKey((key) => key + 1)
    setShowToast(true)
    window.setTimeout(() => setShowToast(false), 3000)
  }

  async function handleSignOut() {
    await signOut()
    window.location.assign('/auth')
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

      {location.pathname !== '/graph' ? <AppFooter /> : null}

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
          <div className="relative max-h-[92vh] w-full max-w-3xl overflow-y-auto">
            <button
              type="button"
              onClick={() => setIsRecorderOpen(false)}
              className="absolute right-4 top-4 z-10 rounded-xl border border-[#8A7129] bg-[#141414] px-3 py-2 text-xl font-black leading-none text-[#E6DFA9] transition hover:border-[#FFDE6E] hover:text-[#FFDE6E] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
              aria-label="Close recorder"
            >
              ×
            </button>
            <VoiceRecorder
              onDreamRecorded={handleDreamRecorded}
              onClose={() => setIsRecorderOpen(false)}
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

function AppFooter() {
  return (
    <footer className="bg-[#0f0f0f] px-4 pb-24 pt-6 text-center text-xs font-bold text-[#8A7129] md:pb-8">
      Built for Bachelor's Thesis — [Your Name] — [University] — 2025
    </footer>
  )
}

function AppNavigation({ onRecordDream, onSignOut }) {
  const linkClass = ({ isActive }) =>
    `border-b-2 px-1 py-1 text-sm font-bold transition hover:text-[#FFDE6E] ${
      isActive
        ? 'border-[#FFDE6E] text-[#FFDE6E]'
        : 'border-transparent text-[#E6DFA9]'
    }`

  const mobileLinkClass = ({ isActive }) =>
    `flex flex-1 flex-col items-center justify-center border-t-2 py-3 text-sm font-black transition ${
      isActive
        ? 'border-[#FFDE6E] text-[#FFDE6E]'
        : 'border-transparent text-[#E6DFA9]'
    }`

  return (
    <>
      <nav className="fixed left-0 top-0 z-40 w-full border-b border-[#1f1f1f] bg-[#0f0f0f] px-5 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <NavLink to="/" className="block text-lg font-bold tracking-wide text-[#FFDE6E]">
            ✦ Morpheus
          </NavLink>
          <div className="hidden items-center gap-6 md:flex">
            <button
              type="button"
              onClick={onRecordDream}
              className="rounded-xl border border-[#FFDE6E] bg-[#FFDE6E] px-4 py-2 text-sm font-black text-[#0f0f0f] transition hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
            >
              Record Dream
            </button>
            <NavLink to="/" className={linkClass}>
              Journal
            </NavLink>
            <NavLink to="/graph" className={linkClass}>
              Graph
            </NavLink>
            <button
              type="button"
              onClick={onSignOut}
              className="border-b-2 border-transparent px-1 py-1 text-sm font-bold text-[#E6DFA9] transition hover:text-[#FFDE6E] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
            >
              Sign Out
            </button>
          </div>
        </div>
      </nav>

      <nav className="fixed bottom-0 left-0 z-40 grid w-full grid-cols-3 border-t border-[#1f1f1f] bg-[#0f0f0f] md:hidden">
        <NavLink to="/" className={mobileLinkClass}>
          Journal
        </NavLink>
        <NavLink to="/graph" className={mobileLinkClass}>
          Graph
        </NavLink>
        <button
          type="button"
          onClick={onSignOut}
          className="flex flex-1 flex-col items-center justify-center border-t-2 border-transparent py-3 text-sm font-black text-[#E6DFA9] transition hover:text-[#FFDE6E] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E]"
        >
          Sign Out
        </button>
      </nav>
    </>
  )
}

export default App
