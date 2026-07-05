import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type ChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  text: string
  mode?: string
}

type ChatApiResponse = {
  response?: string
  mode?: string
  error_type?: string
  error_message?: string
}

type DocumentUploadResponse = {
  filename?: string
  chars_extracted?: number
  facts_saved?: number
  summary?: string
  error_type?: string
  error_message?: string
}

const ACCEPTED_DOCUMENT_EXTENSIONS = '.txt,.md,.pdf,.docx'

const STORAGE_KEY = 'caelo.conversation_id'
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const API_KEY = import.meta.env.VITE_API_KEY ?? ''
const AUTH_HEADERS: HeadersInit = API_KEY ? { 'X-API-Key': API_KEY } : {}

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
  const [uploading, setUploading] = useState(false)
  const [conversationId, setConversationId] = useState<string>(() => {
    const existing = window.localStorage.getItem(STORAGE_KEY)
    return existing && existing.trim() ? existing : createConversationId()
  })
  const listEndRef = useRef<HTMLDivElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

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
        headers: { 'Content-Type': 'application/json', ...AUTH_HEADERS },
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

  const handleFileSelected = async (event: FormEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0]
    event.currentTarget.value = ''
    if (!file) return

    setError('')
    setUploading(true)
    appendMessage({
      id: `${Date.now()}-upload-user`,
      role: 'user',
      text: `Uploaded document: ${file.name}`,
    })

    try {
      const formData = new FormData()
      formData.append('file', file)

      const apiResponse = await fetch(`${API_BASE}/documents/`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: formData,
      })

      const data: DocumentUploadResponse = await apiResponse.json()
      if (!apiResponse.ok || data.error_message) {
        const errorMessage =
          data.error_message ?? `Upload failed with status ${apiResponse.status}`
        setError(errorMessage)
        appendMessage({
          id: `${Date.now()}-upload-error`,
          role: 'system',
          text: `Couldn't process ${file.name}: ${errorMessage}`,
        })
        return
      }

      const factsSaved = data.facts_saved ?? 0
      const factsLabel = factsSaved === 1 ? 'fact' : 'facts'
      appendMessage({
        id: `${Date.now()}-upload-result`,
        role: 'system',
        text: `Learned ${factsSaved} ${factsLabel} from ${data.filename ?? file.name}.`,
      })
      if (data.summary && data.summary.trim()) {
        appendMessage({
          id: `${Date.now()}-upload-summary`,
          role: 'assistant',
          text: data.summary.trim(),
        })
      }
    } catch (err) {
      console.error(err)
      setError('Could not reach backend to upload the document.')
    } finally {
      setUploading(false)
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
        {uploading ? <p className="typing">Reading document...</p> : null}
        <div ref={listEndRef} />
      </section>

      <div className="upload-row">
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_DOCUMENT_EXTENSIONS}
          className="upload-input"
          onChange={handleFileSelected}
          disabled={uploading}
        />
        <button
          type="button"
          className="ghost-button"
          disabled={uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? 'Uploading...' : 'Upload document'}
        </button>
        <span className="upload-hint">.txt, .md, .pdf, .docx</span>
      </div>

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
