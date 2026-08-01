import { useState } from 'react'
import { useVerifyCodeVerifyCodePost } from '../../api/generated/verify/verify'
import styles from './CodeModal.module.css'

interface CodeModalProps {
  sessionId: string
  onSuccess: () => void
  onClose: () => void
}

export default function CodeModal({ sessionId, onSuccess, onClose }: CodeModalProps) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [attemptsRemaining, setAttemptsRemaining] = useState<number | null>(null)

  const isLocked = attemptsRemaining === 0

  const { mutate: submitCode, isPending } = useVerifyCodeVerifyCodePost({
    mutation: {
      onSuccess(data) {
        if (data.success) {
          onSuccess()
          return
        }
        setError(data.message)
        if (data.attempts_remaining !== undefined && data.attempts_remaining !== null) {
          setAttemptsRemaining(data.attempts_remaining)
        }
        setCode('')
      },
      onError() {
        setError('Something went wrong. Please try again.')
      },
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = code.trim()
    if (!trimmed || isPending || isLocked) return
    setError(null)
    submitCode({ data: { code: trimmed, session_id: sessionId } })
  }

  return (
    <div className={styles.overlay}>
      <div className={styles.modal}>
        <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
          ✕
        </button>

        <h2 className={styles.title}>Verify Your Identity</h2>
        <p className={styles.description}>
          A 6-digit code has been sent to your phone. Enter it below to continue.
        </p>

        {attemptsRemaining !== null && attemptsRemaining > 0 && (
          <p className={styles.attemptsWarning}>
            {attemptsRemaining} attempt{attemptsRemaining !== 1 ? 's' : ''} remaining
          </p>
        )}

        <form onSubmit={handleSubmit} className={styles.form}>
          <input
            className={`${styles.codeInput} ${isLocked ? styles.codeInputLocked : ''}`}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder="000000"
            maxLength={6}
            inputMode="numeric"
            autoFocus={!isLocked}
            disabled={isLocked}
          />

          {error && <p className={styles.error}>{error}</p>}

          {isLocked ? (
            <button type="button" className={styles.closeLink} onClick={onClose}>
              Close and ask to resend the code
            </button>
          ) : (
            <button
              className={styles.button}
              type="submit"
              disabled={isPending || code.length !== 6}
            >
              {isPending ? 'Verifying…' : 'Verify'}
            </button>
          )}
        </form>
      </div>
    </div>
  )
}
