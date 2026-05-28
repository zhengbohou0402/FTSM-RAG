# FTSM-RAG

FTSM-RAG is a FastAPI-based **Retrieval-Augmented Generation (RAG)** assistant for UKM FTSM student information. It answers questions about FTSM and UKM student life by retrieving local knowledge-base documents and generating grounded responses with a Tongyi/DashScope chat model.

## Key Features

- **Three-stage retrieval pipeline** — Multi-query vector search (ChromaDB) + BM25 keyword search, fused with Reciprocal Rank Fusion (RRF), then re-ranked by DashScope `gte-rerank-v2`
- **Semantic cache** — Cosine-similarity cache (threshold 0.92) avoids redundant LLM calls; tracks hit/miss rate at runtime
- **Semantic cache experiment** — Measures no-cache latency, cached latency, hit rate, and near-duplicate question reuse
- **LangChain ReAct agent** — Tools include `rag_summarize` (retrieval + answer) and a web-search fallback
- **Streaming responses** — SSE-based character streaming; no WebSocket complexity needed
- **Collapsible source cards** — Each answer shows cited sources with file name, chunk index, excerpt, and source credibility label
- **Conversation history (backend)** — Per-file JSON storage under `data/ukm_ftsm/conversations/`; unified DELETE API
- **Indexing status polling** — Upload → auto-index; management page shows live running / pending / success / error
- **Knowledge base stats** — `/api/knowledge/stats` returns doc count, chunk count, index version, source-type distribution, last indexed time, and cache size
- **Cache stats** — `/api/cache/stats` returns hit count, miss count, hit rate; shown on management page
- **API key masking** — Settings page shows `sk-****xxxx`; only updated if user inputs a new key
- **RAG evaluation suite** — MRR, Precision@K, Recall@K, Latency P50/P90; export to JSON / Markdown / CSV
- **Encoding health check** — scans knowledge-base and source text files before indexing to catch mojibake early
- **System dashboard** — `/dashboard` aggregates all runtime metrics in one page
- **Desktop app** — Bundled as a Windows EXE via PyInstaller + Edge WebView2 (no browser required)
- **Scheduled crawler disabled in EXE** — Dev-only Playwright crawler is automatically skipped when running as a packaged executable

## Project Layout

```text
.
├── launcher.py              # EXE entry point (PyInstaller)
├── ftsm_rag.spec            # PyInstaller spec (onedir)
├── web_app.py               # FastAPI application + all API routes
├── agent/                   # LangChain ReAct agent and tool definitions
├── rag/
│   ├── rag_service.py       # BM25 + Vector + RRF + Reranker pipeline
│   ├── vector_store.py      # ChromaDB wrapper, incremental indexing
│   └── ingestion.py         # Document loading, chunking, manifest
├── model/                   # Chat and embedding model factories
├── config/                  # YAML config (rag.yml, chroma.yml, scheduler.yml)
├── prompts/                 # System and RAG prompt templates
├── scripts/
│   ├── scrape_ftsm_website.py   # FTSM website crawler (dev-only, not bundled)
│   ├── evaluate_rag.py          # RAG evaluation: MRR, P@K, R@K, Latency
│   └── evaluate_cache.py        # Semantic cache latency and hit-rate experiment
├── services/                # Thin service layer (chat, documents, settings)
├── utils/                   # Config, scheduler, semantic cache, conversation store
├── web/                     # Static frontend (HTML/CSS/JS) + Jinja2 templates
├── data/ukm_ftsm/
│   ├── conversations/       # Per-file conversation JSON + index.json
│   └── semantic_cache.json  # Persisted semantic cache
└── chroma_db_ftsm/          # ChromaDB vector store (shipped with the release)
```

## Runtime Stack

| Component | Implementation |
| --- | --- |
| Web backend | FastAPI + Uvicorn |
| Frontend | Static HTML/CSS/JS (SSE streaming, no framework) |
| Agent framework | LangChain ReAct (`create_react_agent`) |
| Retrieval | ChromaDB (vector) + BM25 → RRF → DashScope `gte-rerank-v2` |
| Chat model | DashScope Tongyi (default `qwen3-max`, switchable in UI) |
| Embedding model | DashScope `text-embedding-v4` |
| Vector store | Chroma via `langchain-chroma` |
| Semantic cache | Cosine similarity cache, persisted to JSON |
| Conversation storage | Per-file JSON directory (no database required) |
| Image text extraction | DashScope Qwen-VL + Pillow |
| Scheduled crawling | Playwright (dev-only; auto-disabled in packaged EXE) |

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/config/status` | Whether DashScope API key is set |
| GET/POST | `/api/settings` | Read / save settings (key shown masked) |
| GET | `/api/models` | List available Qwen models + validate key |
| POST | `/api/chat` | Streaming chat (SSE) |
| GET/POST | `/api/conversations` | List / create conversations |
| GET | `/api/conversations/{id}` | Get conversation with messages |
| DELETE | `/api/conversations/{id}` | Delete a conversation |
| GET/POST | `/api/documents` | List / upload knowledge-base files |
| DELETE | `/api/documents/{filename}` | Delete a document + its vector chunks |
| GET/POST | `/api/training/status` `/api/training/start` | Indexing status and trigger |
| GET | `/api/knowledge/stats` | Doc count, chunk count, last indexed time, cache size |
| POST | `/api/knowledge/update` | Manually crawl the FTSM website and rebuild the index |
| GET | `/api/cache/stats` | Cache hit count, miss count, hit rate |
| GET | `/api/scheduler/status` | Crawler scheduler state |

## Development (running from source)

**Requirements:** Python 3.12, a DashScope API key

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Optional: install Chromium for the crawler
python -m playwright install chromium

# Create your env file (or fill via the /settings UI on first run)
Copy-Item .env.example .env
# Edit .env: set DASHSCOPE_API_KEY=sk-...

uvicorn web_app:app --host 127.0.0.1 --port 8000
```

The management page includes an **Update from FTSM site** button. Source builds use Playwright when Chromium is installed; packaged EXE builds use a lightweight HTTP/BeautifulSoup fallback so the button can still refresh `data/ukm_ftsm/ftsm_official_website.txt` and rebuild Chroma without bundling Chromium.

Open <http://127.0.0.1:8000/>. If no API key is set, you are redirected to `/settings` automatically.

## Running the RAG Evaluation

```powershell
# Retrieval-only (fast)
python scripts/evaluate_rag.py

# Retrieval-only with JSON / Markdown / CSV report files
python scripts/evaluate_rag.py --report-dir results/rag_eval

# Full evaluation with LLM answers + JSON / Markdown / CSV report files
python scripts/evaluate_rag.py --with-answer --report-dir results/rag_eval_answer
```

Metrics reported: Source Hit Rate, first-hit rank, MRR, Precision@5, Recall@5, Answer Hit Rate, source coverage, failed cases, and Latency P50/P90.

## Checking Text Encoding

```powershell
python scripts/encoding_health.py --json results/encoding_health.json --fail-on-warning
```

This scans the knowledge base and project text files for common mojibake markers before the documents are indexed into ChromaDB. TXT loading also records the detected encoding and a mojibake score in chunk metadata.

## Running the Cache Experiment

```powershell
python scripts/evaluate_cache.py --report-dir results/cache_eval
```

This produces JSON, Markdown, and CSV reports comparing no-cache answer latency, exact cache reuse, near-duplicate question reuse, cache hit rate, and similarity scores. The experiment uses an in-memory cache and does not clear the app's persisted `semantic_cache.json`.

## Packaging as a Windows Installer (GitHub Releases)

```powershell
# Builds frontend, PyInstaller backend, and Tauri NSIS setup.exe
python scripts/build_windows_installer.py
```

Output: `dist/FTSM-RAG-0.1.1-windows-x64-setup.exe` and the original Tauri artifact under `desktop/src-tauri/target/release/bundle/nsis/`. Upload the copied setup EXE to GitHub Releases. The NSIS installer provides a language selector, current-user/all-users install mode, Start Menu entry, and an install directory page.

## Packaging as a Portable ZIP (Windows)

```powershell
# From the activated .venv
pyinstaller ftsm_rag.spec

# Build a safe distributable zip
python scripts/build_release_zip.py
```

Output: `dist/FTSM-RAG/` and `dist/FTSM-RAG-windows.zip`. Send the zip file or zip the entire `dist/FTSM-RAG/` folder. Do not send only `FTSM-RAG.exe`, because `_internal/python312.dll` and other bundled resources must stay next to the executable.

**Packaged EXE differences from source:**
- Scheduled Playwright crawler is **automatically disabled** (Playwright not bundled)
- ChromaDB vector store and knowledge-base files are copied next to the EXE on first run
- Edge WebView2 runtime required (pre-installed on Windows 11 / recent Windows 10)

If WebView2 is unavailable, the EXE falls back to the default browser. Force browser mode: set `FTSM_BROWSER_MODE=1`.

## Adding Documents

1. Open `/manage` in the browser → drag & drop files → indexing starts automatically
2. Or place files into `data/ukm_ftsm/` and run `python rag/vector_store.py` from source

Supported: TXT, PDF, PNG, JPG, JPEG, WEBP, GIF (max 50 MB each).

## Settings UI (`/settings`)

- **API Key** — saved to `.env`; displayed masked (`sk-****xxxx`); only overwritten when you enter a new key
- **Service Region** — China (`dashscope.aliyuncs.com`) or International (`dashscope-intl.aliyuncs.com`)
- **Chat Model** — pick from `qwen3-max`, `qwen-plus`, `qwen-turbo`, `qwen3.6-plus`, etc.

Changes apply immediately without restart.

## System Dashboard (`/dashboard`)

Real-time view of:
- Knowledge base statistics (documents, indexed chunks, last indexed)
- Semantic cache performance (hit rate, hit/miss counts, valid entries)
- Indexing worker status (running / idle / last result)
- Scheduler/manual crawler status (next crawl time, last manual update, errors)

## Ignored Local Files

Generated at runtime, excluded from git:

- `.venv/`
- `logs/`, `dist/`, `build/`
- `.env`
- `data/ukm_ftsm/conversations/`
- `data/ukm_ftsm/semantic_cache.json`
- `data/ukm_ftsm/.last_crawl`
