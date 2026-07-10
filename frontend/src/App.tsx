import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import './App.css'

type ChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  text: string
  mode?: string
  imageUrl?: string
}

type PreparedImage = {
  mediaType: string
  base64: string
  dataUrl: string
  filename: string
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
  content_type: string | null
  uploaded_at: string | null
  has_file: boolean
}

type Panel = 'none' | 'history' | 'documents' | 'images'

const ACCEPTED_DOCUMENT_EXTENSIONS = '.txt,.md,.pdf,.docx'

// Base64 image blocks are large — keep them under the backend's limit and
// downscale big photos client-side so we don't ship a 12MP original.
const MAX_IMAGE_BYTES = 5 * 1024 * 1024
const MAX_IMAGE_DIM = 1568
const CLAUDE_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/webp'])

function base64Bytes(base64: string): number {
  // Decoded length of a base64 string (ignoring padding chars).
  const padding = base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0
  return Math.floor((base64.length * 3) / 4) - padding
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(new Error('Could not read the image.'))
    reader.readAsDataURL(file)
  })
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const el = new Image()
    el.onload = () => resolve(el)
    el.onerror = () => reject(new Error('Could not decode the image.'))
    el.src = src
  })
}

// Read a File into a base64 payload Claude vision accepts. Downscales anything
// larger than MAX_IMAGE_DIM and re-encodes unsupported types to JPEG. Throws a
// user-facing Error if the result is still over the size limit.
async function prepareImage(file: File): Promise<PreparedImage> {
  const originalUrl = await readAsDataUrl(file)
  const img = await loadImage(originalUrl)
  const scale = Math.min(1, MAX_IMAGE_DIM / Math.max(img.width, img.height))
  const supported = CLAUDE_IMAGE_TYPES.has(file.type)

  let mediaType = file.type
  let dataUrl = originalUrl
  if (scale < 1 || !supported) {
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(img.width * scale))
    canvas.height = Math.max(1, Math.round(img.height * scale))
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Could not process the image.')
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    dataUrl = canvas.toDataURL('image/jpeg', 0.85)
    mediaType = 'image/jpeg'
  }

  const base64 = dataUrl.split(',')[1] ?? ''
  if (base64Bytes(base64) > MAX_IMAGE_BYTES) {
    throw new Error(`Image is too large. Max size is ${MAX_IMAGE_BYTES / (1024 * 1024)} MB.`)
  }
  return { mediaType, base64, dataUrl, filename: file.name || 'image' }
}

function isImage(d: DocumentRecord): boolean {
  return (d.content_type ?? '').startsWith('image/')
}

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

const svgProps = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

const IconNewChat = () => (
  <svg {...svgProps}>
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </svg>
)
const IconHistory = () => (
  <svg {...svgProps}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
)
const IconDocuments = () => (
  <svg {...svgProps}>
    <path d="M8 3h6l4 4v13a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
    <path d="M14 3v5h4" />
  </svg>
)
const IconUpload = () => (
  <svg {...svgProps}>
    <path d="M12 15V4" />
    <path d="m7 9 5-5 5 5" />
    <path d="M5 15v3a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3" />
  </svg>
)
const IconCreate = () => (
  <svg {...svgProps}>
    <path d="M12 3.5 13.6 8 18 9.6 13.6 11.2 12 15.6 10.4 11.2 6 9.6 10.4 8 12 3.5Z" />
    <path d="M18 14.5 18.9 17 21.5 17.9 18.9 18.8 18 21.3 17.1 18.8 14.5 17.9 17.1 17 18 14.5Z" />
  </svg>
)
const IconImages = () => (
  <svg {...svgProps}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <circle cx="8.5" cy="8.5" r="1.5" />
    <path d="m21 15-5-5L5 21" />
  </svg>
)
const IconRefresh = () => (
  <svg {...svgProps}>
    <path d="M21 12a9 9 0 1 1-2.64-6.36" />
    <path d="M21 3v5h-5" />
  </svg>
)
const IconAttach = () => (
  <svg {...svgProps}>
    <path d="M21.44 11.05 12.25 20.24a5 5 0 0 1-7.07-7.07l9.19-9.19a3 3 0 0 1 4.24 4.24l-9.2 9.19a1 1 0 0 1-1.41-1.41l8.48-8.49" />
  </svg>
)

// <img> can't send auth headers, so fetch the file as a blob and use an object URL.
function AuthImage({ id, className, onClick }: { id: number; className?: string; onClick?: () => void }) {
  const [src, setSrc] = useState('')
  useEffect(() => {
    let objectUrl = ''
    let active = true
    fetch(`${API_BASE}/documents/${id}/file`, { headers: AUTH_HEADERS })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
      .then((blob) => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setSrc(objectUrl)
      })
      .catch(() => {})
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [id])
  return <img src={src} className={className} onClick={onClick} alt="" />
}

type MenuItem = { key: string; label: string; icon: ReactNode; action: () => void }

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
  const [menuOpen, setMenuOpen] = useState(false)
  const [imageUploading, setImageUploading] = useState(false)
  const [imageNote, setImageNote] = useState('')
  const [viewerImageId, setViewerImageId] = useState<number | null>(null)
  const [chatImage, setChatImage] = useState<PreparedImage | null>(null)
  const listEndRef = useRef<HTMLDivElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const imageInputRef = useRef<HTMLInputElement | null>(null)
  const chatImageInputRef = useRef<HTMLInputElement | null>(null)

  const canSend = useMemo(
    () => (input.trim().length > 0 || chatImage !== null) && !loading,
    [input, chatImage, loading],
  )

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, conversationId)
  }, [conversationId])

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Image viewer: closeable via Escape and hardware/browser back, and it locks
  // background scroll while open. The X button and backdrop close it directly.
  useEffect(() => {
    if (viewerImageId === null) return
    const close = () => setViewerImageId(null)
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    const onPop = () => close()
    window.addEventListener('keydown', onKey)
    window.addEventListener('popstate', onPop)
    // Push a history entry so Android back / swipe-back dismisses the viewer
    // instead of leaving the app.
    window.history.pushState({ caeloViewer: true }, '')
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('popstate', onPop)
      document.body.style.overflow = prevOverflow
      // If we closed via the X/backdrop/Escape, our pushed entry is still on top —
      // pop it so back doesn't just re-trigger a no-op. If we closed via back,
      // it's already gone and this is skipped.
      if (window.history.state && window.history.state.caeloViewer) {
        window.history.back()
      }
    }
  }, [viewerImageId])

  const appendMessage = (message: ChatMessage) => {
    setMessages((prev) => [...prev, message])
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setError('')

    const trimmed = input.trim()
    const image = chatImage
    if (!trimmed && !image) {
      setError('Please enter a message.')
      return
    }

    appendMessage({
      id: `${Date.now()}-user`,
      role: 'user',
      text: trimmed,
      imageUrl: image?.dataUrl,
    })
    setInput('')
    setChatImage(null)
    setLoading(true)
    try {
      const apiResponse = await fetch(`${API_BASE}/chat/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...AUTH_HEADERS },
        body: JSON.stringify({
          message: trimmed,
          conversation_id: conversationId,
          image: image
            ? { media_type: image.mediaType, data: image.base64, filename: image.filename }
            : undefined,
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

    setPanel('none')
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

  const openCreate = async () => {
    await openDocuments()
    setShowCreateForm(true)
  }

  const openImages = async () => {
    setPanel('images')
    setPanelError('')
    setImageNote('')
    setPanelLoading(true)
    try {
      await refreshDocuments()
    } catch (err) {
      console.error(err)
      setPanelError('Could not load images.')
    } finally {
      setPanelLoading(false)
    }
  }

  const handleImageSelected = async (event: FormEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0]
    event.currentTarget.value = ''
    if (!file) return

    setPanelError('')
    setImageNote('')
    setImageUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch(`${API_BASE}/documents/images`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: formData,
      })
      const data: DocumentRecord & { summary?: string; error_message?: string } = await res.json()
      if (!res.ok || data.error_message) {
        setPanelError(data.error_message ?? `Upload failed with status ${res.status}`)
        return
      }
      if (data.summary && data.summary.trim()) {
        setImageNote(data.summary.trim())
      }
      await refreshDocuments()
    } catch (err) {
      console.error(err)
      setPanelError('Could not upload the image.')
    } finally {
      setImageUploading(false)
    }
  }

  const handleChatImageSelected = async (event: FormEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0]
    event.currentTarget.value = ''
    if (!file) return
    setError('')
    try {
      const prepared = await prepareImage(file)
      setChatImage(prepared)
    } catch (err) {
      console.error(err)
      setError(err instanceof Error ? err.message : 'Could not attach that image.')
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

  // The bubble menu. Add new entries here as features land — the layout adapts.
  const menuItems: MenuItem[] = [
    { key: 'new', label: 'New Chat', icon: <IconNewChat />, action: handleNewConversation },
    { key: 'history', label: 'History', icon: <IconHistory />, action: openHistory },
    { key: 'documents', label: 'Documents', icon: <IconDocuments />, action: openDocuments },
    { key: 'images', label: 'Images', icon: <IconImages />, action: openImages },
    { key: 'upload', label: 'Upload', icon: <IconUpload />, action: () => fileInputRef.current?.click() },
    { key: 'create', label: 'Create', icon: <IconCreate />, action: openCreate },
    { key: 'refresh', label: 'Refresh', icon: <IconRefresh />, action: () => window.location.reload() },
  ]

  const runMenuAction = (action: () => void) => {
    setMenuOpen(false)
    action()
  }

  return (
    <main className="app-shell">
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_DOCUMENT_EXTENSIONS}
        className="upload-input"
        onChange={handleFileSelected}
        disabled={uploading}
      />
      <input
        ref={imageInputRef}
        type="file"
        accept="image/*"
        className="upload-input"
        onChange={handleImageSelected}
        disabled={imageUploading}
      />
      <input
        ref={chatImageInputRef}
        type="file"
        accept="image/*"
        className="upload-input"
        onChange={handleChatImageSelected}
      />

      {panel === 'none' ? (
        <div className="screen chat-screen">
          <header className="app-topbar">
            <h1 className="brand">Caelo</h1>
          </header>

          <section className="chat-thread" aria-live="polite">
            {messages.length === 0 ? (
              <p className="empty-state">What's on your mind?</p>
            ) : (
              messages.map((msg) => (
                <article key={msg.id} className={`bubble ${msg.role}`}>
                  {msg.imageUrl ? (
                    <img src={msg.imageUrl} className="bubble-image" alt="shared" />
                  ) : null}
                  {msg.text ? <p>{msg.text}</p> : null}
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

          <form onSubmit={handleSubmit} className="composer">
            {chatImage ? (
              <div className="composer-attachment">
                <img src={chatImage.dataUrl} className="attachment-thumb" alt="attachment" />
                <button
                  type="button"
                  className="attachment-remove"
                  onClick={() => setChatImage(null)}
                  aria-label="Remove image"
                >
                  <svg {...svgProps}>
                    <path d="M6 6l12 12" />
                    <path d="M18 6 6 18" />
                  </svg>
                </button>
              </div>
            ) : null}
            <div className="composer-row">
              <button
                type="button"
                className="attach-btn"
                onClick={() => chatImageInputRef.current?.click()}
                disabled={loading}
                aria-label="Attach image"
              >
                <IconAttach />
              </button>
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="Message Caelo..."
                disabled={loading}
                rows={1}
              />
              <button type="submit" className="send-btn" disabled={!canSend} aria-label="Send">
                <svg {...svgProps}>
                  <path d="M5 12h14" />
                  <path d="m13 6 6 6-6 6" />
                </svg>
              </button>
            </div>
          </form>
        </div>
      ) : (
        <div className="screen panel-screen">
          <div className="panel-header">
            <h2>{panel === 'history' ? 'Previous chats' : panel === 'images' ? 'Images' : 'Documents'}</h2>
            <button type="button" className="ghost-button" onClick={() => setPanel('none')}>
              Back
            </button>
          </div>
          <div className="panel-body">
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
                        className="accent-button small"
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
                    className="accent-button block"
                    onClick={() => setShowCreateForm(true)}
                  >
                    Create document
                  </button>
                )}
                {documents.filter((d) => !isImage(d)).length === 0 && !panelLoading ? (
                  <p className="empty-state">No documents yet.</p>
                ) : (
                  documents
                    .filter((d) => !isImage(d))
                    .map((d, idx) => (
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
            {panel === 'images' ? (
              <>
                <button
                  type="button"
                  className="accent-button block"
                  onClick={() => imageInputRef.current?.click()}
                  disabled={imageUploading}
                >
                  {imageUploading ? 'Uploading...' : 'Upload image'}
                </button>
                {imageNote ? (
                  <div className="list-item static">
                    <p className="list-item-summary">{imageNote}</p>
                  </div>
                ) : null}
                {documents.filter(isImage).length === 0 && !panelLoading ? (
                  <p className="empty-state">No images yet.</p>
                ) : (
                  <div className="image-grid">
                    {documents.filter(isImage).map((d) => (
                      <AuthImage
                        key={d.id}
                        id={d.id}
                        className="image-thumb"
                        onClick={() => setViewerImageId(d.id)}
                      />
                    ))}
                  </div>
                )}
              </>
            ) : null}
          </div>
        </div>
      )}

      {viewerImageId !== null ? (
        <div className="image-viewer" onClick={() => setViewerImageId(null)}>
          <button
            type="button"
            className="viewer-close"
            onClick={() => setViewerImageId(null)}
            aria-label="Close image"
          >
            <svg {...svgProps}>
              <path d="M6 6l12 12" />
              <path d="M18 6 6 18" />
            </svg>
          </button>
          <AuthImage id={viewerImageId} className="viewer-img" />
        </div>
      ) : null}

      {error ? <div className="toast">{error}</div> : null}

      {menuOpen ? (
        <div className="menu-overlay" onClick={() => setMenuOpen(false)}>
          <div className="menu-grid" onClick={(e) => e.stopPropagation()}>
            {menuItems.map((item) => (
              <button
                key={item.key}
                type="button"
                className="menu-item"
                onClick={() => runMenuAction(item.action)}
              >
                <span className="menu-icon">{item.icon}</span>
                <span className="menu-label">{item.label}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <button
        type="button"
        className={`fab ${menuOpen ? 'open' : ''}`}
        onClick={() => setMenuOpen((o) => !o)}
        aria-label={menuOpen ? 'Close menu' : 'Open menu'}
      >
        <span className="fab-orb" />
        <span className="fab-x">
          <svg {...svgProps}>
            <path d="M6 6l12 12" />
            <path d="M18 6 6 18" />
          </svg>
        </span>
      </button>
    </main>
  )
}

export default App
