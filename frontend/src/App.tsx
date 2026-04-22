import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  mode?: string
}

type ChatApiResponse = {
  response?: string
  mode?: string
  error_type?: string
  error_message?: string
}

const STORAGE_KEY = 'caelo.conversation_id'
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

function createConversationId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `caelo-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function App() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [conversationId, setConversationId] = useState<string>(() => {
    const existing = window.localStorage.getItem(STORAGE_KEY)
    return existing && existing.trim() ? existing : createConversationId()
  })
  const listEndRef = useRef<HTMLDivElement | null>(null)

  const canSend = useMemo(() => input.trim().length > 0 && !loading, [input, loading])

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, conversationId)
  }, [conversationId])

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const appendMessage = (message: ChatMessage) => {
    setMessages((prev) => [...prev, message])
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')

    const trimmed = input.trim()
    if (!trimmed) {
      setError('Please enter a message.')
      return
    }

    appendMessage({
      id: `${Date.now()}-user`,
      role: 'user',
      text: trimmed,
    })
    setInput('')
    setLoading(true)
    try {
      const apiResponse = await fetch(`${API_BASE}/chat/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: trimmed,
          conversation_id: conversationId,
        }),
      })

      const data: ChatApiResponse = await apiResponse.json()
      if (!apiResponse.ok || data.error_message) {
        const errorMessage =
          data.error_message ?? `Request failed with status ${apiResponse.status}`
        setError(errorMessage)
        return
      }

      appendMessage({
        id: `${Date.now()}-assistant`,
        role: 'assistant',
        text: data.response ?? '',
        mode: data.mode,
      })
    } catch (err) {
      console.error(err)
      setError('Could not reach backend. Is FastAPI running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  const handleNewConversation = () => {
    const newId = createConversationId()
    setConversationId(newId)
    setMessages([])
    setError('')
    setInput('')
  }

  return (
    <main className="chat-page">
      <header className="chat-header">
        <div>
          <h1>Caelo</h1>
          <p className="chat-subtitle">Local conversation</p>
        </div>
        <button type="button" className="ghost-button" onClick={handleNewConversation}>
          New chat
        </button>
      </header>

      <section className="chat-thread" aria-live="polite">
        {messages.length === 0 ? (
          <p className="empty-state">Start a conversation.</p>
        ) : (
          messages.map((msg) => (
            <article key={msg.id} className={`bubble ${msg.role}`}>
              <p>{msg.text}</p>
              {msg.role === 'assistant' && msg.mode ? (
                <span className="mode-tag">{msg.mode}</span>
              ) : null}
            </article>
          ))
        )}
        {loading ? <p className="typing">Caelo is thinking...</p> : null}
        <div ref={listEndRef} />
      </section>

      <form onSubmit={handleSubmit} className="chat-form">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Type your message..."
          disabled={loading}
          rows={2}
        />
        <button type="submit" disabled={!canSend}>
          {loading ? 'Sending...' : 'Send'}
        </button>
      </form>

      <footer className="chat-footer">
        <span className="conversation-id">conversation_id: {conversationId}</span>
        {error ? <p className="error">Error: {error}</p> : null}
      </footer>
    </main>
  )
}

export default App
