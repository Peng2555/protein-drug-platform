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
  const response = await api.request<T>({ url, ...config })
  const contentType = String(response.headers['content-type'] || '')
  if (url.startsWith('/api/') && contentType.includes('text/html')) {
    throw new Error('后端接口尚未加载，请重启平台服务')
  }
  const { data } = response
  return data
}

export { TOKEN_KEY }
