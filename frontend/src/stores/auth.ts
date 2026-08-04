import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiJson, TOKEN_KEY } from '@/api/client'

export interface AuthUser {
  id: string
  username: string
}

function loadStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem('boltzfold_user')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<AuthUser | null>(loadStoredUser())

  const isLoggedIn = computed(() => !!token.value)

  function setSession(newToken: string, newUser: AuthUser) {
    token.value = newToken
    user.value = newUser
    localStorage.setItem(TOKEN_KEY, newToken)
    localStorage.setItem('boltzfold_user', JSON.stringify(newUser))
  }

  function clearSession() {
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem('boltzfold_user')
  }

  async function login(username: string, password: string) {
    const data = await apiJson<{ access_token: string; user: AuthUser }>('/api/auth/login', {
      method: 'POST',
      data: { username, password },
    })
    setSession(data.access_token, data.user)
  }

  async function register(username: string, password: string) {
    await apiJson('/api/auth/register', {
      method: 'POST',
      data: { username, password },
    })
    await login(username, password)
  }

  async function fetchMe() {
    const me = await apiJson<AuthUser>('/api/auth/me')
    user.value = me
    localStorage.setItem('boltzfold_user', JSON.stringify(me))
    return me
  }

  async function bootstrap() {
    if (!token.value) return false
    try {
      await fetchMe()
      return true
    } catch {
      clearSession()
      return false
    }
  }

  function logout() {
    clearSession()
  }

  return {
    token,
    user,
    isLoggedIn,
    login,
    register,
    bootstrap,
    logout,
  }
})
