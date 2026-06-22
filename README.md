# Noema — How to run

Two apps run side by side: the **backend** (FastAPI, port 8000) and the
**frontend** (Vite + React, port 5173). Start the backend first.

The only thing that differs between machines is `backend/.env` (which LLM
provider + credentials). The code is the same on both.

## Prerequisites

- Python 3.10+
- Node.js 18+

---

## macOS (local dev — personal OpenAI key)

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env`:

```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...your personal key...
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBED_MODEL=text-embedding-3-small
```

Run:

```bash
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (second terminal)

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

---

## Windows (company machine — OpenAI-compatible endpoint)

Do **not** copy `.venv/` or `node_modules/` from the Mac — recreate them here.

### 1. Backend (PowerShell)

```powershell
cd backend
python -m venv .venv
# Allow venv activation for THIS terminal only (no admin, reverts on close):
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

> The `Set-ExecutionPolicy` line is per-session — rerun it in each new terminal
> before activating. Alternative: skip activation and call
> `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000` directly.

Edit `backend\.env` with the company endpoint:

```
LLM_PROVIDER=llmaas
LLMAAS_BASE_URL=https://<company-host>/v1
LLMAAS_CHAT_MODEL=<a chat model the endpoint exposes>
LLMAAS_API_KEY=
```

- Leave `LLMAAS_API_KEY` blank for a **keyless** endpoint (the app passes a
  placeholder the server ignores); fill it if the gateway requires a key.
- `LLMAAS_BASE_URL` usually ends in `/v1` — the SDK appends `/chat/completions`
  and `/models`. If you get 404s, fix the suffix.

Run:

```powershell
uvicorn app.main:app --reload --port 8000
```

Verify: <http://localhost:8000/health> returns `{"status":"ok"}`, and
<http://localhost:8000/models> lists the endpoint's models.

### 2. Frontend (second terminal)

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173> and send a test message.

---

## Switching providers

`LLM_PROVIDER` selects the backend at runtime — no code change:

| Value    | Use                          | Required vars                                                        |
| -------- | ---------------------------- | ------------------------------------------------------------------- |
| `openai` | local dev (Mac)                                 | `OPENAI_API_KEY` (+ optional model names)            |
| `llmaas` | prod — the Azure-hosted OpenAI-compatible `/v1` | `LLMAAS_BASE_URL`, `LLMAAS_CHAT_MODEL` (key optional) |

(There is no separate `azure` provider — the company endpoint is OpenAI-compatible,
so it's reached through `llmaas`.)

A second, independent switch — `PARSER` — selects the PDF backend: `vision` (default,
works everywhere) or `docintel` (Azure Document Intelligence; needs `DOCINTEL_ENDPOINT`
+ `DOCINTEL_KEY`). See `backend/app/parsing/PARSING.md`.

## Troubleshooting (secure / corporate machine)

- **`pip install` fails on `chromadb`** — it's not used yet (RAG isn't built).
  Comment it out of `requirements.txt`; you only need `pypdfium2` and
  `python-multipart` for the PDF feature (plus `azure-ai-documentintelligence`
  only if you set `PARSER=docintel`).
- **Proxy / TLS errors** (pip, npm, or the backend reaching the LLM) — set
  `HTTPS_PROXY` / `HTTP_PROXY`, and for self-signed certs point `SSL_CERT_FILE`
  (or `REQUESTS_CA_BUNDLE`) at the corporate CA bundle.
- **Streams but no token counts** — the endpoint doesn't return usage on
  streamed responses; harmless, chat still works.
- **Non-GPT-4o model** — the live "input tokens" estimate is approximate; turn
  off "Live token estimate" in Settings if you don't want it.
