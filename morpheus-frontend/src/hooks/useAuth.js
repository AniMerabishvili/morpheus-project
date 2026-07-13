import { useEffect, useState } from 'react'

import { supabase } from '../lib/supabase.js'

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
      } else {
        setUser(data.session?.user || null)
        setSession(data.session || null)
      }

      setLoading(false)
    }

    const { data: listener } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setUser(nextSession?.user || null)
      setSession(nextSession || null)
      setLoading(false)
    })

    loadSession()

    return () => {
      isMounted = false
      listener.subscription.unsubscribe()
    }
  }, [])

  async function signOut() {
    await supabase.auth.signOut()
  }

  return { user, session, loading, signOut }
}
