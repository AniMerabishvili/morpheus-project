import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { supabase } from '../lib/supabase.js'

const fieldHeight = 'h-[clamp(2.5rem,5.4vh,3rem)]'
const labelClass = 'mb-[clamp(0.25rem,0.9vh,0.5rem)] block text-sm text-[#A6A69D]'
const inputClass = `${fieldHeight} w-full rounded-xl border border-[#2a2a27] bg-[#121212] px-4 text-sm text-[#F4F4F1] outline-none transition placeholder:text-[#5f5f58] focus:border-[#C7D8A6]`

const copy = {
  signIn: {
    heading: 'Welcome back',
    submit: 'Sign in',
    switchPrompt: "Don't have an account?",
    switchAction: 'Sign Up',
  },
  signUp: {
    heading: 'Create your account',
    submit: 'Create account',
    switchPrompt: 'Already have an account?',
    switchAction: 'Sign In',
  },
}

function AuthPage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState('signIn')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isPasswordVisible, setIsPasswordVisible] = useState(false)
  const [isConfirmVisible, setIsConfirmVisible] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const isSignUp = mode === 'signUp'
  const text = copy[mode]

  function switchMode() {
    setMode(isSignUp ? 'signIn' : 'signUp')
    setErrorMessage('')
    setConfirmPassword('')
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setErrorMessage('')

    if (isSignUp && password !== confirmPassword) {
      setErrorMessage('Passwords do not match.')
      return
    }

    setIsSubmitting(true)

    try {
      const credentials = {
        email: email.trim(),
        password,
      }
      const { data, error } = isSignUp
        ? await supabase.auth.signUp({
          ...credentials,
          options: {
            emailRedirectTo: `${window.location.origin}/auth`,
          },
        })
        : await supabase.auth.signInWithPassword(credentials)

      if (error) {
        throw error
      }

      if (!data.session?.access_token) {
        setErrorMessage('Check your email to confirm your account, then sign in.')
        return
      }

      navigate('/', { replace: true })
    } catch (error) {
      setErrorMessage(error.message || 'Authentication failed.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="flex h-dvh items-center justify-center overflow-y-auto bg-[#0a0a0a] p-4 md:p-6">
      <div className="w-full max-w-104 py-[clamp(0.5rem,2vh,1.5rem)]">
        <h1 className="text-[1.75rem] leading-tight tracking-tight text-[#F4F4F1]">
          {text.heading}
        </h1>

        <form
          onSubmit={handleSubmit}
          className="mt-[clamp(1rem,3.5vh,2rem)] space-y-[clamp(0.625rem,2vh,1.25rem)]"
        >
          <label className="block">
            <span className={labelClass}>
              Email address <span className="text-[#C7D8A6]">*</span>
            </span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="email"
              placeholder="e.g. andrew@example.com"
              className={inputClass}
            />
          </label>

          <div
            className={`grid gap-[clamp(0.625rem,2vh,1rem)] ${isSignUp ? 'sm:grid-cols-2' : ''}`}
          >
            <label className="block">
              <span className={labelClass}>Password</span>
              <PasswordInput
                value={password}
                onChange={setPassword}
                isVisible={isPasswordVisible}
                onToggleVisible={() => setIsPasswordVisible((visible) => !visible)}
                autoComplete={isSignUp ? 'new-password' : 'current-password'}
                minLength={isSignUp ? 8 : undefined}
                label="password"
              />
            </label>

            {isSignUp ? (
              <label className="block">
                <span className={labelClass}>Confirm password</span>
                <PasswordInput
                  value={confirmPassword}
                  onChange={setConfirmPassword}
                  isVisible={isConfirmVisible}
                  onToggleVisible={() => setIsConfirmVisible((visible) => !visible)}
                  autoComplete="new-password"
                  minLength={8}
                  label="password confirmation"
                />
              </label>
            ) : null}
          </div>

          {isSignUp ? (
            <p className="text-xs leading-relaxed text-[#6b6b64]">
              Password must be at least 8 characters, including a number and a special character.
            </p>
          ) : null}

          {errorMessage ? (
            <p className="rounded-xl border border-[#4a2626] bg-[#1d1212] px-4 py-3 text-sm text-[#D08A8A]">
              {errorMessage}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className={`mt-[clamp(0.25rem,1vh,0.5rem)] ${fieldHeight} w-full rounded-xl bg-[#C7D8A6] text-sm font-medium text-[#14160f] transition hover:brightness-105 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#C7D8A6] disabled:cursor-not-allowed disabled:opacity-60`}
          >
            {isSubmitting ? 'Working...' : text.submit}
          </button>
        </form>

        <p className="mt-[clamp(0.75rem,2.5vh,1.75rem)] text-center text-sm text-[#86867E]">
          {text.switchPrompt}{' '}
          <button
            type="button"
            onClick={switchMode}
            className="font-medium text-[#F4F4F1] transition hover:text-[#C7D8A6]"
          >
            {text.switchAction}
          </button>
        </p>
      </div>
    </main>
  )
}

function PasswordInput({ value, onChange, isVisible, onToggleVisible, autoComplete, minLength, label }) {
  return (
    <span className="relative block">
      <input
        type={isVisible ? 'text' : 'password'}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
        minLength={minLength}
        autoComplete={autoComplete}
        placeholder="••••••••••••"
        className={`${inputClass} pr-11`}
      />
      <button
        type="button"
        onClick={onToggleVisible}
        aria-label={`${isVisible ? 'Hide' : 'Show'} ${label}`}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-[#6b6b64] transition hover:text-[#A6A69D]"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z" />
          <circle cx="12" cy="12" r="2.75" />
          {isVisible ? <path d="M4 20 20 4" /> : null}
        </svg>
      </button>
    </span>
  )
}

export default AuthPage
