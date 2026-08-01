import { useState } from 'react'
import { useVerifyCodeVerifyCodePost } from '../../api/generated/verify/verify'
import styles from './CodeModal.module.css'

interface CodeModalProps {
  sessionId: string
  onSuccess: () => void
}

export default function CodeModal({ sessionId, onSuccess }: CodeModalProps) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { mutate: submitCode, isPending } = useVerifyCodeVerifyCodePost({
    mutation: {
      onSuccess(data) {
        if (data.success) {
          onSuccess()
        } else {
          setError(data.message)
        }
      },
      onError() {
        setError('Something went wrong. Please try again.')
      },
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = code.trim()
    if (!trimmed || isPending) return
    setError(null)
    submitCode({ data: { code: trimmed, session_id: sessionId } })
  }

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <h2 className={styles.title}>Verify Your Identity</h2>
        <p className={styles.description}>
          A 6-digit code has been sent to your phone. Enter it below to continue.
        </p>
        <form onSubmit={handleSubmit} className={styles.form}>
          <input
            className={styles.codeInput}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder="000000"
            maxLength={6}
            inputMode="numeric"
            autoFocus
          />
          {error && <p className={styles.error}>{error}</p>}
          <button
            className={styles.button}
            type="submit"
            disabled={isPending || code.length !== 6}
          >
            {isPending ? 'Verifying…' : 'Verify'}
          </button>
        </form>
      </div>
    </div>
  )
}
