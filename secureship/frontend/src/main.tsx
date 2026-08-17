import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Auth0Provider } from '@auth0/auth0-react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'

const queryClient = new QueryClient()

const auth0Domain = import.meta.env.VITE_AUTH0_DOMAIN ?? ''
const auth0ClientId = import.meta.env.VITE_AUTH0_CLIENT_ID ?? ''
const auth0Audience = import.meta.env.VITE_AUTH0_AUDIENCE ?? ''

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Auth0Provider
        domain={auth0Domain}
        clientId={auth0ClientId}
        authorizationParams={{
          redirect_uri: `${window.location.origin}/admin`,
          audience: auth0Audience,
        }}
        cacheLocation="localstorage"
      >
        <QueryClientProvider client={queryClient}>
          <App />
        </QueryClientProvider>
      </Auth0Provider>
    </BrowserRouter>
  </StrictMode>,
)
