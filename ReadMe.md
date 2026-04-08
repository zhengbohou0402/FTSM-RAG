# FTSM-RAG

FTSM-RAG is a FastAPI-based Retrieval-Augmented Generation (RAG) assistant for UKM FTSM student information. It answers questions about FTSM and UKM student life by retrieving local knowledge base documents from Chroma and generating grounded responses with a Tongyi/DashScope chat model.

The current implementation is a local web application with:

- FastAPI backend and a static HTML/JavaScript chat UI
- LangChain agent with a `rag_summarize` retrieval tool
- Chroma persistent vector store
- DashScope Tongyi chat model and DashScope embedding model
- Local knowledge base under `data/ukm_ftsm`
- FTSM website crawler under `scripts/scrape_ftsm_website.py`
- Document upload and background vector-store rebuild endpoints
- Conversation history and semantic response cache stored locally

## Project Layout

```text
.
|-- web_app.py                  # FastAPI application entry point
|-- agent/                      # LangChain agent and tools
|-- rag/                        # RAG retrieval and vector-store services
|-- model/                      # Chat and embedding model factories
|-- config/                     # YAML configuration
|-- prompts/                    # System and RAG prompt templates
|-- scripts/                    # FTSM website crawler
|-- utils/                      # Config, scheduling, cache, file loading helpers
|-- web/                        # Static frontend and Jinja template
|-- data/ukm_ftsm/              # Local source documents
|-- chroma_db_ftsm/             # Generated Chroma database, ignored by git
```

## Runtime Stack

| Component | Current Implementation |
| --- | --- |
| Web backend | FastAPI + Uvicorn |
| Frontend | Static HTML/CSS/JavaScript served by FastAPI |
| Agent framework | LangChain `create_agent` |
| Chat model | DashScope Tongyi, configured as `qwen3-max` |
| Embedding model | DashScope `text-embedding-v4` |
| Vector store | Chroma via `langchain-chroma` |
| Text splitting | `RecursiveCharacterTextSplitter` |
| PDF loading | LangChain `PyPDFLoader` |
| Image text extraction | DashScope Qwen-VL + Pillow |
| Scheduled crawling | Local background scheduler using Playwright crawler |

Model names and vector-store settings are configured in:

- `config/rag.yml`
- `config/chroma.yml`
- `config/scheduler.yml`

## Requirements

- Python 3.12 is recommended, matching the existing local `.venv`.
- A DashScope API key is required for chat, embedding, and image text extraction.
- Chromium browser files are required if you run the Playwright crawler.

## Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

If you plan to run the crawler, install the Playwright browser runtime:

```powershell
python -m playwright install chromium
```

Create a local environment file from the example:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and set your DashScope key:

```text
DASHSCOPE_API_KEY=your_dashscope_api_key_here
```

Before starting the app, load the key into your shell. For example:

```powershell
$env:DASHSCOPE_API_KEY="your_dashscope_api_key_here"
```

Alternatively, use your deployment platform's secret manager or environment-variable configuration.

## Run The Web App

Start the FastAPI application:

```powershell
uvicorn web_app:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

The web UI requires a local FTSM student account. Students can register and sign in from the login screen. Accounts are stored locally in `data/ukm_ftsm/student_accounts.json` with PBKDF2 password hashes; this file is ignored by git.

Management endpoints for uploading, deleting, and re-indexing documents are separate from student login and require the `X-Admin-API-Key` header configured by `ADMIN_API_KEY`.

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

For LAN or server deployment, bind to all interfaces:

```powershell
uvicorn web_app:app --host 0.0.0.0 --port 8000
```

## Build Or Refresh The Vector Store

The source documents live in `data/ukm_ftsm`. The vector store is generated into `chroma_db_ftsm`, which is intentionally ignored by git.

During ingestion, each local file is normalized into a source-document record with a stable `doc_id`, content `hash`, `title`, `updated_at`, `file_path`, `source_type`, and `permission_scope`. Chunk metadata is written into Chroma with `doc_id`, `chunk_id`, `chunk_index`, `hash`, and source fields so retrieved answers can be traced back to the indexed document.

Index state is stored in `data/ukm_ftsm/ingestion_manifest.json`. If a file hash is unchanged, indexing skips it. If a known file changes, the old chunk ids are deleted from Chroma before new chunks are added.

Run indexing manually:

```powershell
python rag/vector_store.py
```

Or call the API after the web app is running:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/training/start
```

You can also upload documents from the UI or through `/api/upload`; uploaded files are saved into the configured knowledge-base directory and trigger background training.

## Crawl FTSM Website

Run the crawler:

```powershell
python scripts/scrape_ftsm_website.py
```

Limit the number of crawled pages:

```powershell
python scripts/scrape_ftsm_website.py --max-pages 80
```

Skip training after crawling:

```powershell
python scripts/scrape_ftsm_website.py --no-train
```

The scheduler can also run crawling periodically when the FastAPI app starts. Configure it in `config/scheduler.yml`.

## Important Local Files

The following are generated at runtime and ignored by git:

- `.venv/`
- `logs/`
- `chroma_db_ftsm/`
- nested `**/chroma_db/`
- `md5_ftsm.text`
- `data/ukm_ftsm/chat_sessions.json`
- `data/ukm_ftsm/semantic_cache.json`
- `data/ukm_ftsm/.last_crawl`

## Notes

This repository currently represents a local/demo RAG application. Before using it in production, add authentication for document upload, deletion, and training endpoints; implement vector deletion/update by document ID; and add evaluation tests for retrieval and answer quality.
