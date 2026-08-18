import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { setTokenGetter } from '../../lib/axiosInstance'
import CustomerManager from './CustomerManager'
import ShipmentManager from './ShipmentManager'
import styles from './AdminPanel.module.css'

type Tab = 'customers' | 'shipments'

export default function AdminPanel() {
  const { isAuthenticated, isLoading, loginWithRedirect, logout, user, getAccessTokenSilently } = useAuth0()
  const [tab, setTab] = useState<Tab>('customers')

  useEffect(() => {
    if (isAuthenticated) {
      setTokenGetter(getAccessTokenSilently)
    }
  }, [isAuthenticated, getAccessTokenSilently])

  if (isLoading) {
    return <div className={styles.center}><p>Loading…</p></div>
  }

  if (!isAuthenticated) {
    loginWithRedirect()
    return <div className={styles.center}><p>Redirecting to login…</p></div>
  }

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <span className={styles.logo}>SecureShip Admin</span>
        <nav className={styles.nav}>
          <button
            className={`${styles.navBtn} ${tab === 'customers' ? styles.navActive : ''}`}
            onClick={() => setTab('customers')}
          >
            Customers
          </button>
          <button
            className={`${styles.navBtn} ${tab === 'shipments' ? styles.navActive : ''}`}
            onClick={() => setTab('shipments')}
          >
            Shipments
          </button>
        </nav>
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
        {tab === 'customers' && <CustomerManager />}
        {tab === 'shipments' && <ShipmentManager />}
      </main>
    </div>
  )
}
