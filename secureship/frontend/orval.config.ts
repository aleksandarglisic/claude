import { defineConfig } from 'orval'

export default defineConfig({
  secureship: {
    input: {
      target: 'http://localhost:8000/openapi.json',
    },
    output: {
      mode: 'tags-split',
      target: 'src/api/generated',
      client: 'react-query',
      override: {
        mutator: {
          path: 'src/lib/axiosInstance.ts',
          name: 'axiosInstance',
        },
      },
    },
  },
})
