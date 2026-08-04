import axios, { type AxiosRequestConfig } from 'axios'

const TOKEN_KEY = 'boltzfold_token'

export const api = axios.create({
  baseURL: '',
  timeout: 120_000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem('boltzfold_user')
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    const detail = err.response?.data?.detail
    const message = typeof detail === 'string' ? detail : err.message || '请求失败'
    return Promise.reject(new Error(message))
  },
)

export async function apiJson<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await api.request<T>({ url, ...config })
  return data
}

export { TOKEN_KEY }
