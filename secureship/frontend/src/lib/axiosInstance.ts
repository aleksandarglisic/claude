import axios, { AxiosRequestConfig } from 'axios'

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
})

// Orval mutator: called for every generated API function.
export const axiosInstance = <T>(config: AxiosRequestConfig): Promise<T> => {
  return client(config).then((res) => res.data as T)
}
