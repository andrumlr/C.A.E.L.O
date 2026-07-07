# C.A.E.L.O — Project Handoff

_Last updated: 2026-07-07. Living document — update it at the end of each working session._

Repo: github.com/andrumlr/C.A.E.L.O
Stack: Python / FastAPI backend, React + Vite frontend, Docker on Railway.
Live branch: `main` (pushing to `main` auto-deploys — see Deployment).

---

## 1. What C.A.E.L.O is

A personal AI companion (not a generic assistant) with persistent memory, a
mode system (presence vs execution), and a personality defined in
`personality/*.txt` and `prompts/*.txt`. Runs on Claude (Anthropic) as its
brain in production. Also supports OpenAI and Ollama (local) as alternate
brains, switchable via the `CAELO_PROVIDER` env var. No Gemini support.

## 2. Owner context & working style (read this first)

- **Owner works entirely from an iPhone — no computer.** Workflow is GitHub
  mobile web + Railway iOS app + Claude Code for all changes.
- Prefers **slow, step-by-step** explanations and **frequent check-ins**.
  Don't dump everything at once.
- **Confirm before calling something "done"; verify with a real test**, not an
  assumption about config or deploy state. Multiple bugs this project came from
  assuming a deploy/config was correct when it wasn't.
- For **visual/UX changes**, build on a branch and share screenshots for
  approval *before* merging to `main` (main = live). This is how the GUI
  redesign was handled.

---

## 3. Deployment architecture (and its gotchas)

**Two separate Railway services, both deploy from `main`:**

- **backend** — FastAPI app. Has a **Railway Volume** mounted at
  `/app/backend/data`; `CAELO_DATA_DIR=/app/backend/data` points both the
  SQLite DB and uploaded files there. Persistence across redeploys is
  **confirmed working** (verified live: facts, history, and stored files all
  survive restarts).
- **frontend** — static React/Vite build served by Caddy.

### Gotchas that bit us repeatedly — internalize these

1. **The frontend is a static build; `VITE_*` env vars are baked in at BUILD
   time.** Changing `VITE_API_BASE_URL` / `VITE_API_KEY`, or shipping any
   frontend code, requires the **frontend service to redeploy**. Several
   "it's not working" moments were the frontend service not having rebuilt, or
   the phone showing a cached old build.
   **→ After any change, confirm BOTH services redeployed, then hard-refresh
   the phone (or use a private tab).**
2. **Pushing to `main` deploys to the live app.** Do not push unreviewed
   visual/behavioral changes straight to `main`. Use a branch + screenshots,
   merge when the owner approves.
3. **DB migrations — never drop/recreate tables.** `Base.metadata.create_all()`
   creates missing tables but **does not add columns to existing ones**. The
   `documents` table already exists on the live volume. New columns are added
   by an additive startup migration in `backend/db/database.py`
   (`_migrate_added_columns`, driven by the `_ADDED_COLUMNS` dict — uses the
   SQLAlchemy inspector + `ALTER TABLE ... ADD COLUMN`). To add a column later,
   add it to the model **and** to `_ADDED_COLUMNS`. Never drop/recreate — that
   would wipe real conversation/memory history.

### Environment variables

Backend: `CAELO_PROVIDER` (default `ollama`; live uses `claude`),
`ANTHROPIC_API_KEY`, `CLAUDE_MODEL` (default `claude-sonnet-4-5`),
`OPENAI_API_KEY`, `OPENAI_MODEL` (default `gpt-4o`), `OLLAMA_BASE_URL`,
`OLLAMA_MODEL`, `OLLAMA_TIMEOUT_S`, `CAELO_DATA_DIR`, `CAELO_API_KEY`
(shared-secret gate — see Security).

Frontend (baked at build): `VITE_API_BASE_URL`, `VITE_API_KEY`.

---

## 4. Current feature set (all live unless noted)

- **Chat** with mode system (presence/execution) and short-term + long-term memory.
- **Long-term memory**: facts extracted from conversations (every ~30 messages,
  `backend/memory/fact_extractor.py`) and from uploaded documents, injected into
  the chat prompt (`get_active_facts` → prompt). `ALLOWED_CATEGORIES`: identity,
  family, preferences, projects, context, knowledge.
- **Document upload** (`.txt/.md/.pdf/.docx`): extracts text → distills facts
  into memory (source-prefixed, e.g. "From resume.pdf: ...") → generates an
  in-voice summary → **saves the original file to disk** → records the upload in
  chat history so Caelo knows it happened.
- **Document creation**: Caelo writes a document from a title + instructions,
  saved as a real `.md` file (same storage as uploads).
- **Documents panel**: lists uploaded + created docs with summary, fact count,
  date, and an **Open** button (downloads the original file; only shown when a
  file exists on disk — pre-storage uploads have none). **Excludes images.**
- **Image upload + Images panel**: images are stored as plain files (same
  `Document` row + `uploads/` dir + download route as documents) with **no text
  or fact extraction**. The Images panel is a thumbnail grid with an upload
  control and tap-to-enlarge full-screen viewer. Thumbnails/viewer fetch each
  image as an **authed blob** (see lesson 5) rather than a bare `<img src>`.
- **History panel**: browse past conversations and tap one to reload/resume it.
- **Security**: shared-secret API gate, per-IP rate limiting, tightened CORS,
  sanitized error responses (see Security).
- **GUI (redesigned, live)**: mobile-first warm-dark theme. Plain chat screen +
  a floating gradient orb (bottom-right). Tapping the orb dims/blurs and fans
  out a bubble menu: **New Chat · History · Documents · Images · Upload · Create
  · Refresh**. `Refresh` hard-reloads the page (`window.location.reload`) — the
  recovery path for the occasional frozen-UI state (roadmap 4a). The menu is a
  single data-driven array in `frontend/src/App.tsx` (`menuItems`) — **add new
  options there** (label + icon + action) and the layout adapts.

## 5. API surface (all require `X-API-Key` header when `CAELO_API_KEY` is set)

- `POST /chat/` — send a message. Body `{message, conversation_id?}`.
- `GET  /documents/` — list documents + images (incl. `id`, `content_type`,
  `has_file`). The frontend splits documents vs images by `content_type`.
- `POST /documents/` — multipart document upload (extraction + facts + summary).
- `POST /documents/images` — multipart image upload (image/* only, stored raw,
  no extraction).
- `POST /documents/create` — body `{title, instructions}`; Caelo writes a doc.
- `GET  /documents/{id}/file` — download original (404 if missing/no file);
  serves both documents and images.
- `GET  /conversations/` — list past chats (excludes the internal
  `document-uploads` bucket).
- `GET  /conversations/{id}/messages` — full transcript.

## 6. Security (added this project — don't be surprised by 401s)

- **Shared-secret gate** (`backend/core/auth.py`): every request to `/chat`,
  `/documents`, `/conversations` must send `X-API-Key` matching `CAELO_API_KEY`.
  If `CAELO_API_KEY` is unset (e.g. local dev), the gate is open. The frontend
  sends the key from `VITE_API_KEY`. **A 401 in the live app usually means the
  frontend build's `VITE_API_KEY` and the backend's `CAELO_API_KEY` don't match
  (often a stale frontend build).**
- **Rate limiting** (`backend/core/rate_limit.py`, in-memory, per IP):
  `POST /chat/` 20/min, `POST /documents/` and `POST /documents/create` 6/min,
  `POST /documents/images` 12/min. Keyed by `(method, path)` — GET/read
  endpoints are unlimited.
- **CORS**: `allow_credentials=False`, origin regex for `*.railway.app` + localhost.
- **Errors**: unexpected exceptions are logged server-side and return a generic
  message; only deliberately-raised user-facing errors pass through
  (`backend/core/errors.py`).

## 7. Data model

Tables: `conversations`, `messages`, `memory_entries`, `settings`, `summaries`,
`documents`. `documents` columns: id, filename (display name), facts_saved,
summary, uploaded_at, file_path, content_type, size_bytes. Files live at
`{CAELO_DATA_DIR}/uploads/<uuid>.<ext>`. **Images share the `documents` table**
— an image is just a `Document` row with an `image/*` `content_type`,
`facts_saved=0`, and `summary=NULL`; documents vs images are distinguished
purely by `content_type`.

## 8. Providers

`backend/providers/`: `claude_provider.py` (production), `openai_provider.py`,
`ollama_provider.py`. `local_provider.py` is an **unused stub** (dead code).
Selected by `CAELO_PROVIDER`. **`max_tokens` is 4096** in `claude_provider.py`
— keep it ≥ 4096 (see lesson below).

---

## 9. Key lessons learned (hard-won — don't repeat these)

1. **Don't apply Ollama's output scrubbing to Claude.**
   `_scrub_echoed_prompt_artifacts` (in `ollama_provider.py`) exists to strip
   leaked prompt text from local models. It substring-matches ordinary phrases
   ("long-term memory", "mode policy", …) and **truncates everything after a
   match**. It was wrongly applied to Claude and silently cut off responses
   mid-output — this was the real root cause of the "0 facts" document bug
   (the test doc literally contained "long-term memory"). It is **Ollama/OpenAI
   only**; Claude returns clean output and must not be scrubbed.
2. **Anthropic `max_tokens` too low truncates long JSON/replies.** It was 1024;
   long fact-extraction arrays overran it and produced invalid JSON → "0 facts".
   Now 4096.
3. **When a bug reproduces, get the real signal before "fixing."** The 0-facts
   bug got three wrong fixes (parser hardening, diagnostic logging, max_tokens)
   before the Railway logs revealed the true cause. There is a diagnostic in
   `document_service.py` that logs `length`/`ends_clean`/`head`/`tail` when
   extraction yields nothing — use it.
4. **"It's not working" is often a half-deployed frontend or a cached build**,
   not a code bug. Check both services + hard-refresh before deep-diving.
5. **`<img src>` can't send the `X-API-Key` header**, so behind the auth gate a
   bare image tag 401s. Fetch the image as a blob with `AUTH_HEADERS` and use an
   object URL instead (see the `AuthImage` component in `App.tsx`). Same reason
   the document "Open" download fetches a blob rather than linking directly.

---

## 10. Roadmap & status

1. ✅ Real file storage for uploads — **done, live-verified**.
2. ✅ Caelo can create documents — **done, live-verified**.
3. ✅ **Image folder** — Images panel + storage, separate from Documents.
   **Done, pushed.** (Reused the document storage/download mechanism.)
4. **New-chat / reopen behavior** — two distinct problems:
   - **4a (freeze recovery): partially addressed.** A **Refresh** menu item now
     hard-reloads the page, giving a recovery path without force-quitting. The
     underlying freeze itself is still **unreproduced** — next time it happens,
     capture what's on screen (blank? frozen "thinking…" spinner? dead buttons?).
   - **4b (design gap, open):** on reopen the chat starts blank — `messages`
     initializes to `[]`. The History panel already fetches any conversation by
     id, so auto-loading the last `conversationId` on mount is a small wire-up.
5. ✅ GUI redesign — **done, live** (mobile-first warm theme + bubble menu).

**Also queued — Personality overhaul (high daily impact):** responses still run
long and question-heavy in normal chat, not warm/companion-like enough. Goal:
shorter, fewer questions, no "how can I help", warmer, grows via memory. Files:
`personality/*.txt`, `prompts/SYSTEM_PROMPT.md.txt`,
`prompts/MODE_PROMPTS.md.txt`, `backend/core/prompt_builder.py`.

**Recommended next:** the **personality overhaul** — with the feature roadmap
(1–3, 5) essentially done, this is the highest felt-impact work left and what
the owner notices every session. Otherwise the small **4b** wire-up
(auto-restore last conversation on reopen) is a cheap, self-contained win.

## 11. Open housekeeping

- **Stale remote branches** that could not be deleted from the Claude Code
  environment (its git proxy rejects branch-deletion pushes): `gui-redesign`
  (merged), `claude/system-prompt-truncation-fix-eh50qb` (merged),
  `railway/fix-deploy-addf40`. All merged/obsolete and harmless. Delete from
  GitHub mobile: repo → Branches → trash icon.
- `backend/providers/local_provider.py` is dead code; can be removed anytime.
