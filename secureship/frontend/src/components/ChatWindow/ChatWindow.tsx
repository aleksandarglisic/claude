import { useEffect, useRef, useState } from 'react'
import { useSendMessageChatPost } from '../../api/generated/chat/chat'
import type { MessageIn } from '../../api/generated/secureShipAPI.schemas'
import styles from './ChatWindow.module.css'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const { mutate: sendMessage, isPending } = useSendMessageChatPost({
    mutation: {
      onSuccess(data) {
        setSessionId(data.session_id)
        setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }])
      },
      onError() {
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: 'Sorry, something went wrong. Please try again.' },
        ])
      },
    },
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || isPending) return

    const userMessage: Message = { role: 'user', content: text }
    const history: MessageIn[] = messages.map((m) => ({ role: m.role, content: m.content }))

    setMessages((prev) => [...prev, userMessage])
    setInput('')

    sendMessage({
      data: {
        message: text,
        session_id: sessionId ?? undefined,
        history,
      },
    })
  }

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <span className={styles.logo}>SecureShip</span>
        <span className={styles.subtitle}>Shipment Support</span>
      </header>

      <div className={styles.messages}>
        {messages.length === 0 && (
          <div className={styles.empty}>
            Hi! Ask me about your shipments or anything else I can help with.
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`${styles.bubble} ${styles[msg.role]}`}>
            <span className={styles.roleLabel}>{msg.role === 'user' ? 'You' : 'SecureShip'}</span>
            <p>{msg.content}</p>
          </div>
        ))}
        {isPending && (
          <div className={`${styles.bubble} ${styles.assistant} ${styles.typing}`}>
            <span className={styles.roleLabel}>SecureShip</span>
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
          placeholder="Type a message…"
          disabled={isPending}
          autoFocus
        />
        <button className={styles.button} type="submit" disabled={isPending || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  )
}
