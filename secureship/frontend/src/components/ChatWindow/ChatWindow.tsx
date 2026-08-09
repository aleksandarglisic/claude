import { useEffect, useRef, useState } from 'react'
import { useGetSessionStateChatSessionIdStateGet, useSendMessageChatPost } from '../../api/generated/chat/chat'
import type { MessageIn } from '../../api/generated/secureShipAPI.schemas'
import CodeModal from '../CodeModal/CodeModal'
import styles from './ChatWindow.module.css'

const SESSION_KEY = 'secureship_session_id'

interface Message {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(
    () => sessionStorage.getItem(SESSION_KEY)
  )
  const [sessionState, setSessionState] = useState<string>('anonymous')
  const [showModal, setShowModal] = useState(false)
  // suppressModal prevents the modal from auto-reopening after the user dismisses it.
  // It clears only when the backend confirms a new code was sent (send_verification_code tool call).
  const [suppressModal, setSuppressModal] = useState(false)
  const [escalated, setEscalated] = useState(false)
  const [knownFirstName, setKnownFirstName] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Persist sessionId to sessionStorage so page refreshes within the same tab
  // reuse the session. New tabs start fresh (sessionStorage is tab-scoped).
  useEffect(() => {
    if (sessionId) {
      sessionStorage.setItem(SESSION_KEY, sessionId)
    } else {
      sessionStorage.removeItem(SESSION_KEY)
    }
  }, [sessionId])

  // On mount, restore session state from the backend (verified badge, modal, escalation).
  // Runs only once; staleTime: Infinity prevents refetching on window focus.
  const { data: restoredState } = useGetSessionStateChatSessionIdStateGet(sessionId ?? '', {
    query: { enabled: !!sessionId, staleTime: Infinity, retry: false },
  })
  useEffect(() => {
    if (!restoredState) return
    const state = restoredState.session_state ?? 'anonymous'
    setSessionState(state)
    if (restoredState.known_first_name) setKnownFirstName(restoredState.known_first_name)
    if (restoredState.show_modal && !suppressModal) setShowModal(true)
    if (state === 'escalated_to_human') setEscalated(true)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [restoredState])

  const { mutate: sendMessage, isPending } = useSendMessageChatPost({
    mutation: {
      onSuccess(data) {
        setSessionId(data.session_id)
        setSessionState(data.session_state ?? 'anonymous')
        if (data.known_first_name) setKnownFirstName(data.known_first_name)

        if (data.escalated) {
          setEscalated(true)
          playEscalationTheater(data.reply, data.known_first_name ?? null)
          return
        }

        if (data.reply) {
          setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }])
        }

        if (data.show_modal) {
          const codeWasResent = data.tool_calls?.some((tc) => tc.name === 'send_verification_code') ?? false
          if (!suppressModal || codeWasResent) {
            setSuppressModal(false)
            setShowModal(true)
          }
        }
      },
      onError() {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: 'Sorry, something went wrong. Please try again.' },
        ])
      },
    },
  })

  function playEscalationTheater(handoffMessage: string, firstName: string | null) {
    setMessages((prev) => [...prev, { role: 'assistant', content: handoffMessage }])
    setTimeout(() => {
      setMessages((prev) => [...prev, { role: 'system', content: 'Melany has entered the chat' }])
    }, 1500)
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Hello, let me just read through the chat…' },
      ])
    }, 3500)
    setTimeout(() => {
      const greeting = firstName
        ? `Hey ${firstName}, I'm up to speed — how can I help you?`
        : "Hey there, I'm all caught up — how can I help you?"
      setMessages((prev) => [...prev, { role: 'assistant', content: greeting }])
    }, 6500)
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || isPending || showModal) return

    const userMessage: Message = { role: 'user', content: text }
    const history: MessageIn[] = messages
      .filter((m) => m.role !== 'system')
      .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }))

    setMessages((prev) => [...prev, userMessage])
    setInput('')
    sendMessage({ data: { message: text, session_id: sessionId ?? undefined, history } })
  }

  function handleVerified() {
    setShowModal(false)
    setSuppressModal(false)
    setSessionState('verified')
    setMessages((prev) => [
      ...prev,
      { role: 'system', content: 'Identity verified ✓ — you can now ask about your shipments.' },
    ])
  }

  function handleModalClose() {
    setShowModal(false)
    setSuppressModal(true)
  }

  // Sends a canned resend request to the backend — the model calls send_verification_code(),
  // the response comes back with tool_calls containing it, which clears suppressModal.
  function handleRequestResend() {
    setShowModal(false)
    setSuppressModal(true)
    const history: MessageIn[] = messages
      .filter((m) => m.role !== 'system')
      .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }))
    sendMessage({
      data: {
        message: "I didn't receive the verification code. Please resend it.",
        session_id: sessionId ?? undefined,
        history,
      },
    })
  }

  const isVerified = sessionState === 'verified'
  const containerClass = [styles.container, escalated ? styles.escalated : ''].filter(Boolean).join(' ')

  return (
    <div className={containerClass}>
      {showModal && sessionId && (
        <CodeModal
          sessionId={sessionId}
          onSuccess={handleVerified}
          onClose={handleModalClose}
          onRequestResend={handleRequestResend}
        />
      )}

      <header className={styles.header}>
        <span className={styles.logo}>SecureShip</span>
        <span className={styles.subtitle}>{escalated ? 'Human Support' : 'Shipment Support'}</span>
        {isVerified && !escalated && (
          <span className={styles.verifiedBadge}>✓ Verified</span>
        )}
      </header>

      <div className={styles.messages}>
        {messages.length === 0 && (
          <div className={styles.empty}>
            Hi! Ask me about your shipments or anything else I can help with.
          </div>
        )}
        {messages.map((msg, i) => {
          if (msg.role === 'system') {
            return (
              <div key={i} className={styles.systemNotice}>
                {msg.content}
              </div>
            )
          }
          return (
            <div key={i} className={`${styles.bubble} ${styles[msg.role]}`}>
              <span className={styles.roleLabel}>
                {msg.role === 'user' ? 'You' : escalated ? 'Melany' : 'SecureShip'}
              </span>
              <p>{msg.content}</p>
            </div>
          )
        })}
        {isPending && (
          <div className={`${styles.bubble} ${styles.assistant} ${styles.typing}`}>
            <span className={styles.roleLabel}>{escalated ? 'Melany' : 'SecureShip'}</span>
            <p>
              <span className={styles.dot} />
              <span className={styles.dot} />
              <span className={styles.dot} />
            </p>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form className={styles.form} onSubmit={handleSubmit}>
        <input
          className={styles.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={showModal ? 'Enter your code in the box above…' : 'Type a message…'}
          disabled={isPending || showModal}
          autoFocus={!showModal}
        />
        <button className={styles.button} type="submit" disabled={isPending || !input.trim() || showModal}>
          Send
        </button>
      </form>
    </div>
  )
}
