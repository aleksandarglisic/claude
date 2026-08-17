import { useAuth0 } from '@auth0/auth0-react'
import styles from './AdminPanel.module.css'

export default function AdminPanel() {
  const { isAuthenticated, isLoading, loginWithRedirect, logout, user } = useAuth0()

  if (isLoading) {
    return (
      <div className={styles.center}>
        <p>Loading…</p>
      </div>
    )
  }

  if (!isAuthenticated) {
    // Auto-redirect to Auth0 login. Shows a brief prompt while redirecting.
    loginWithRedirect()
    return (
      <div className={styles.center}>
        <p>Redirecting to login…</p>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <span className={styles.logo}>SecureShip Admin</span>
        <div className={styles.user}>
          <span>{user?.email}</span>
          <button
            className={styles.logoutButton}
            onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
          >
            Log out
          </button>
        </div>
      </header>

      <main className={styles.main}>
        <p className={styles.notice}>
          Auth0 login is working. Full customer, shipment, and package management
          will be added in Epic E2.
        </p>
      </main>
    </div>
  )
}
