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

type ConversationSummary = {
  id: string
  created_at: string | null
  preview: string
}

type ConversationMessage = {
  role: string
  content: string
  mode?: string | null
  created_at?: string | null
}

type DocumentRecord = {
  id: number
  filename: string
  facts_saved: number
  summary: string | null
  uploaded_at: string | null
  has_file: boolean
}

type Panel = 'none' | 'history' | 'documents'

const ACCEPTED_DOCUMENT_EXTENSIONS = '.txt,.md,.pdf,.docx'

function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

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
  const [panel, setPanel] = useState<Panel>('none')
  const [panelLoading, setPanelLoading] = useState(false)
  const [panelError, setPanelError] = useState('')
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [createTitle, setCreateTitle] = useState('')
  const [createInstructions, setCreateInstructions] = useState('')
  const [creating, setCreating] = useState(false)
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

  const openHistory = async () => {
    setPanel('history')
    setPanelError('')
    setPanelLoading(true)
    try {
      const res = await fetch(`${API_BASE}/conversations/`, { headers: AUTH_HEADERS })
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
      setConversations(await res.json())
    } catch (err) {
      console.error(err)
      setPanelError('Could not load past chats.')
    } finally {
      setPanelLoading(false)
    }
  }

  const refreshDocuments = async () => {
    const res = await fetch(`${API_BASE}/documents/`, { headers: AUTH_HEADERS })
    if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
    setDocuments(await res.json())
  }

  const openDocuments = async () => {
    setPanel('documents')
    setPanelError('')
    setShowCreateForm(false)
    setPanelLoading(true)
    try {
      await refreshDocuments()
    } catch (err) {
      console.error(err)
      setPanelError('Could not load uploaded documents.')
    } finally {
      setPanelLoading(false)
    }
  }

  const handleCreateDocument = async () => {
    const title = createTitle.trim()
    const instructions = createInstructions.trim()
    if (!title || !instructions) {
      setPanelError('Give the document a title and some instructions.')
      return
    }
    setPanelError('')
    setCreating(true)
    try {
      const res = await fetch(`${API_BASE}/documents/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...AUTH_HEADERS },
        body: JSON.stringify({ title, instructions }),
      })
      const data: DocumentRecord & { error_message?: string } = await res.json()
      if (!res.ok || data.error_message) {
        setPanelError(data.error_message ?? `Request failed with status ${res.status}`)
        return
      }
      setCreateTitle('')
      setCreateInstructions('')
      setShowCreateForm(false)
      await refreshDocuments()
    } catch (err) {
      console.error(err)
      setPanelError('Could not create the document.')
    } finally {
      setCreating(false)
    }
  }

  const loadConversation = async (id: string) => {
    setPanelError('')
    setPanelLoading(true)
    try {
      const res = await fetch(`${API_BASE}/conversations/${id}/messages`, { headers: AUTH_HEADERS })
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
      const data: { conversation_id: string; messages: ConversationMessage[] } = await res.json()
      const mapped: ChatMessage[] = data.messages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .map((m, idx) => ({
          id: `${id}-${idx}`,
          role: m.role as 'user' | 'assistant',
          text: m.content,
          mode: m.mode ?? undefined,
        }))
      setMessages(mapped)
      setConversationId(id)
      setError('')
      setPanel('none')
    } catch (err) {
      console.error(err)
      setPanelError('Could not load that conversation.')
    } finally {
      setPanelLoading(false)
    }
  }

  const handleNewConversation = () => {
    const newId = createConversationId()
    setConversationId(newId)
    setMessages([])
    setError('')
    setInput('')
    setPanel('none')
  }

  const openDocumentFile = async (id: number, filename: string) => {
    setPanelError('')
    try {
      const res = await fetch(`${API_BASE}/documents/${id}/file`, { headers: AUTH_HEADERS })
      if (!res.ok) throw new Error(`Request failed with status ${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.target = '_blank'
      link.rel = 'noopener'
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error(err)
      setPanelError(`Could not open ${filename}.`)
    }
  }

  return (
    <main className="chat-page">
      <header className="chat-header">
        <div>
          <h1>Caelo</h1>
          <p className="chat-subtitle">Local conversation</p>
        </div>
        <div className="header-actions">
          <button type="button" className="ghost-button" onClick={openHistory}>
            History
          </button>
          <button type="button" className="ghost-button" onClick={openDocuments}>
            Documents
          </button>
          <button type="button" className="ghost-button" onClick={handleNewConversation}>
            New chat
          </button>
        </div>
      </header>

      {panel !== 'none' ? (
        <section className="chat-thread panel">
          <div className="panel-header">
            <h2>{panel === 'history' ? 'Previous chats' : 'Uploaded documents'}</h2>
            <button type="button" className="ghost-button" onClick={() => setPanel('none')}>
              Back to chat
            </button>
          </div>
          {panelLoading ? <p className="typing">Loading...</p> : null}
          {panelError ? <p className="error">{panelError}</p> : null}
          {panel === 'history' &&
            (conversations.length === 0 && !panelLoading ? (
              <p className="empty-state">No past chats yet.</p>
            ) : (
              conversations.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className="list-item"
                  onClick={() => loadConversation(c.id)}
                >
                  <span className="list-item-preview">{c.preview || '(empty)'}</span>
                  <span className="list-item-meta">{formatDate(c.created_at)}</span>
                </button>
              ))
            ))}
          {panel === 'documents' ? (
            <>
              {showCreateForm ? (
                <div className="create-doc-form">
                  <input
                    type="text"
                    className="create-doc-title"
                    placeholder="Document title"
                    value={createTitle}
                    onChange={(e) => setCreateTitle(e.target.value)}
                    disabled={creating}
                  />
                  <textarea
                    className="create-doc-instructions"
                    placeholder="What should Caelo write?"
                    value={createInstructions}
                    onChange={(e) => setCreateInstructions(e.target.value)}
                    disabled={creating}
                    rows={3}
                  />
                  <div className="create-doc-actions">
                    <button
                      type="button"
                      className="ghost-button small"
                      onClick={() => setShowCreateForm(false)}
                      disabled={creating}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="ghost-button small"
                      onClick={handleCreateDocument}
                      disabled={creating}
                    >
                      {creating ? 'Writing...' : 'Create'}
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => setShowCreateForm(true)}
                >
                  Create document
                </button>
              )}
              {documents.length === 0 && !panelLoading ? (
                <p className="empty-state">No documents yet.</p>
              ) : (
                documents.map((d, idx) => (
                  <div key={`${d.filename}-${idx}`} className="list-item static">
                    <div className="list-item-row">
                      <span className="list-item-preview">{d.filename}</span>
                      {d.has_file ? (
                        <button
                          type="button"
                          className="ghost-button small"
                          onClick={() => openDocumentFile(d.id, d.filename)}
                        >
                          Open
                        </button>
                      ) : null}
                    </div>
                    <span className="list-item-meta">
                      {d.facts_saved} {d.facts_saved === 1 ? 'fact' : 'facts'} · {formatDate(d.uploaded_at)}
                    </span>
                    {d.summary ? <p className="list-item-summary">{d.summary}</p> : null}
                  </div>
                ))
              )}
            </>
          ) : null}
        </section>
      ) : (
        <>
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
        </>
      )}

      <footer className="chat-footer">
        <span className="conversation-id">conversation_id: {conversationId}</span>
        {error ? <p className="error">Error: {error}</p> : null}
      </footer>
    </main>
  )
}

export default App
