import axios, { AxiosRequestConfig } from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
})

// Set by AdminPanel after Auth0 authentication so admin API calls include the JWT.
let _getToken: (() => Promise<string>) | null = null

export const setTokenGetter = (fn: () => Promise<string>) => {
  _getToken = fn
}

client.interceptors.request.use(async (config) => {
  if (_getToken) {
    const token = await _getToken()
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Orval mutator: called for every generated API function.
export const axiosInstance = <T>(config: AxiosRequestConfig): Promise<T> => {
  return client(config).then((res) => res.data as T)
}
