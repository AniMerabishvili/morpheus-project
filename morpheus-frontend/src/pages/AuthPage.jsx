import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { supabase } from '../lib/supabase.js'

const modes = {
  signIn: 'Sign In',
  signUp: 'Sign Up',
}

function AuthPage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState('signIn')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setErrorMessage('')
    setIsSubmitting(true)

    try {
      const credentials = {
        email: email.trim(),
        password,
      }
      const { data, error } = mode === 'signIn'
        ? await supabase.auth.signInWithPassword(credentials)
        : await supabase.auth.signUp(credentials)

      if (error) {
        throw error
      }

      if (!data.session?.access_token) {
        setErrorMessage('Check your email to confirm your account, then sign in.')
        return
      }

      localStorage.setItem('morpheus_session_token', data.session.access_token)
      navigate('/', { replace: true })
    } catch (error) {
      setErrorMessage(error.message || 'Authentication failed.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#0f0f0f] px-4 py-10 text-[#E6DFA9]">
      <section className="w-full max-w-md">
        <div className="mb-10 text-center">
          <p className="mb-3 text-5xl font-black leading-none text-[#FFDE6E]">✦ Morpheus</p>
          <p className="text-lg font-semibold text-[#E6DFA9]">Your dreams, decoded</p>
        </div>

        <div className="mb-5 grid grid-cols-2 gap-2 rounded-lg border border-[#1f1f1f] bg-[#141414] p-1">
          {Object.entries(modes).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => {
                setMode(key)
                setErrorMessage('')
              }}
              className={`rounded-md px-4 py-3 text-sm font-black transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E] ${
                mode === key
                  ? 'bg-[#FFDE6E] text-[#0f0f0f]'
                  : 'text-[#E6DFA9] hover:text-[#FFDE6E]'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="block">
            <span className="mb-2 block text-sm font-bold text-[#E6DFA9]">Email</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="email"
              className="w-full rounded-lg border border-[#1f1f1f] bg-[#141414] px-4 py-3 text-[#E6DFA9] outline-none transition placeholder:text-[#8A7129] focus:border-[#FFDE6E]"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-bold text-[#E6DFA9]">Password</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={6}
              autoComplete={mode === 'signIn' ? 'current-password' : 'new-password'}
              className="w-full rounded-lg border border-[#1f1f1f] bg-[#141414] px-4 py-3 text-[#E6DFA9] outline-none transition placeholder:text-[#8A7129] focus:border-[#FFDE6E]"
            />
          </label>

          {errorMessage ? (
            <p className="rounded-lg border border-[#5c2b2b] bg-[#2a1515] px-4 py-3 text-sm font-bold text-[#C96F6F]">
              {errorMessage}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg border border-[#FFDE6E] bg-[#FFDE6E] px-4 py-3 font-black text-[#0f0f0f] transition hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FFDE6E] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? 'Working...' : modes[mode]}
          </button>
        </form>
      </section>
    </main>
  )
}

export default AuthPage
