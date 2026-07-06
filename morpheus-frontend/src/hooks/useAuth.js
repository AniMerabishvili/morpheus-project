import { useEffect, useState } from 'react'

import { supabase } from '../lib/supabase.js'

function storeSessionToken(session) {
  if (session?.access_token) {
    localStorage.setItem('morpheus_session_token', session.access_token)
  } else {
    localStorage.removeItem('morpheus_session_token')
  }
}

export function useAuth() {
  const [user, setUser] = useState(null)
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let isMounted = true

    async function loadSession() {
      const { data, error } = await supabase.auth.getSession()

      if (!isMounted) {
        return
      }

      if (error) {
        setUser(null)
        setSession(null)
        storeSessionToken(null)
      } else {
        setUser(data.session?.user || null)
        setSession(data.session || null)
        storeSessionToken(data.session)
      }

      setLoading(false)
    }

    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setUser(nextSession?.user || null)
      setSession(nextSession || null)
      storeSessionToken(nextSession)
      setLoading(false)
    })

    loadSession()

    return () => {
      isMounted = false
      listener.subscription.unsubscribe()
    }
  }, [])

  async function signOut() {
    storeSessionToken(null)
    await supabase.auth.signOut()
  }

  return { user, session, loading, signOut }
}
