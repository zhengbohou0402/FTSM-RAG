# FTSM-RAG

FTSM-RAG is a FastAPI-based Retrieval-Augmented Generation (RAG) assistant for UKM FTSM student information. It answers questions about FTSM and UKM student life by retrieving local knowledge base documents from Chroma and generating grounded responses with a Tongyi/DashScope chat model.

- FastAPI backend + static HTML/JS chat UI
- LangChain agent with a `rag_summarize` retrieval tool
- Chroma persistent vector store (shipped with the app)
- DashScope Tongyi chat model + DashScope embeddings
- **Zero-config single-user mode** — conversations stored in a local JSON file, no database required
- **Native desktop window** — bundled into a onedir executable that opens in its own window (Edge WebView2), no browser required. Users just double-click `FTSM-RAG.exe` and fill in their API key in the settings page.

## Project Layout

```text
.
|-- launcher.py             # exe entry point
|-- ftsm_rag.spec           # PyInstaller spec (onedir)
|-- web_app.py              # FastAPI app
|-- agent/                  # LangChain agent and tools
|-- rag/                    # Retrieval and vector-store services
|-- model/                  # Chat and embedding model factories
|-- config/                 # YAML config (models, chroma, scheduler)
|-- prompts/                # System and RAG prompt templates
|-- scripts/                # FTSM website crawler (dev-only, not bundled)
|-- utils/                  # Config, scheduler, cache, file helpers
|-- web/                    # Static frontend and Jinja templates
|-- data/ukm_ftsm/          # Local knowledge base + conversations.json
|-- chroma_db_ftsm/         # Chroma vector DB (shipped with the release)
```

## Development (running from source)

Requirements:
- Python 3.12
- A DashScope API key

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Optional: install Chromium for the crawler
python -m playwright install chromium

# Create your env file (can also be filled from the /settings UI on first run)
Copy-Item .env.example .env
# Edit .env and set DASHSCOPE_API_KEY=...

# Run the server
uvicorn web_app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/>. If no API key is configured, you will be redirected to `/settings` automatically.

## Packaging as a standalone EXE (Windows)

The project is configured for a **onedir** PyInstaller build: the final artifact is a folder containing `FTSM-RAG.exe` plus an `_internal/` dependency folder. Users double-click the exe and the app opens in a dedicated desktop window (no browser, no console).

```powershell
# From the activated .venv
pyinstaller ftsm_rag.spec
```

Output: `dist/FTSM-RAG/`. You can:
1. Zip the whole `dist/FTSM-RAG/` folder and send it to a user.
2. On first run, the user is taken to the in-app settings page to enter their DashScope API key.
3. The bundled Chroma vector store (`chroma_db_ftsm/`) is copied to the exe directory on first start, so answers work offline without re-indexing.

### What the exe actually does on first run

- Creates `chroma_db_ftsm/`, `data/`, `config/`, and `.env` next to the exe (copied from the bundle).
- Starts a local FastAPI server on `127.0.0.1` on an auto-chosen free port.
- Opens a native desktop window (Edge WebView2) pointing at the server.
- If the API key is missing, the window lands on `/settings` automatically.

### System requirement: Edge WebView2 runtime

The desktop window is rendered by **Microsoft Edge WebView2**, which is **pre-installed on Windows 11** and on most up-to-date Windows 10 machines. If the user's machine is missing it, the exe will automatically fall back to the default browser. To install it manually (free from Microsoft), grab the "Evergreen Standalone Installer" from <https://developer.microsoft.com/microsoft-edge/webview2/>.

If a user wants to force browser mode for any reason, set the environment variable `FTSM_BROWSER_MODE=1` before launching the exe.

## Runtime Stack

| Component | Implementation |
| --- | --- |
| Web backend | FastAPI + Uvicorn |
| Frontend | Static HTML/CSS/JS served by FastAPI |
| Agent framework | LangChain `create_agent` |
| Chat model | DashScope Tongyi (default `qwen3-max`, switchable in UI) |
| Embedding model | DashScope `text-embedding-v4` |
| Vector store | Chroma via `langchain-chroma` |
| Conversation storage | Local `data/ukm_ftsm/conversations.json` (no database) |
| Image text extraction | DashScope Qwen-VL + Pillow |
| Scheduled crawling (dev) | Playwright crawler |

Model names and vector-store settings live in:

- `config/rag.yml`   — chat/embedding/image model names (can be edited at runtime via `/settings`)
- `config/chroma.yml`
- `config/scheduler.yml`

## Settings UI

Open `/settings` in the browser to configure:

- **DashScope API Key** — saved into `.env`
- **Service Region** — toggle between China (default) and International endpoint (needed for `qwen3.6-plus`)
- **Chat Model** — pick one of `qwen3-max`, `qwen-plus`, `qwen-turbo`, `qwen3.6-plus`

Changes apply immediately; no restart required.

## Adding Documents

- Drag & drop files in `/manage` (no authentication required in the standalone build)
- Or place files into `data/ukm_ftsm/` and run `python rag/vector_store.py` when developing

Supported file types: TXT, PDF, PNG, JPG, JPEG, WEBP, GIF.

## Notes on the Crawler

`scripts/scrape_ftsm_website.py` uses Playwright and is **excluded from the exe bundle** (it requires a Chromium install that is too large to ship). Run it from source if you need to re-crawl the FTSM site:

```powershell
python scripts/scrape_ftsm_website.py --max-pages 80
```

## Ignored local files

These are generated at runtime and ignored by git:

- `.venv/`
- `logs/`
- `dist/`, `build/` (PyInstaller output)
- `.env`
- `data/ukm_ftsm/conversations.json`
- `data/ukm_ftsm/chat_sessions.json`
- `data/ukm_ftsm/semantic_cache.json`
- `data/ukm_ftsm/.last_crawl`
