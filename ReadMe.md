# FTSM-RAG

A **Retrieval-Augmented Generation (RAG)** assistant for UKM FTSM student information, delivered as a **dual-stack microservices graduation project**: Java business services (Spring Boot 3) + a Python AI service (FastAPI + LangChain), integrated through **RabbitMQ events** behind a single gateway.

> Legacy monolith heritage: the retrieval core (three-stage hybrid search + rerank + evaluation suite) comes from the single-app version; the delivery has been restructured into services. The desktop (PyInstaller/Tauri) packaging of the legacy version is frozen and archived under `desktop/`.

## Architecture

```text
                        ┌─────────────────────────── Java side ───────────────────────────┐
 web/ (English UI) ──►  ftsm-gateway :8080  ──►  ftsm-user         :8101  (accounts, login)
 (static, English)      (session verify,         ftsm-conversation :8102  (chats, messages)
                         admin key,              ftsm-knowledge    :8103  (doc state machine,
                         SSE passthrough)                                 query log, quality)
                        └──────────────┬───────────────────────────────┬──────────────────┘
                                       │  MySQL 8 (authoritative state) │ RabbitMQ 3.12
                                       ▼                                ▼
                        ┌─────────── Python side ─────────────────────────────────────────┐
                        ftsm-rag :8104 — FastAPI + LangChain
                        hybrid retrieval (ChromaDB vector + BM25 → RRF → rerank),
                        semantic cache, ReAct agent, chat SSE, indexing consumer
                                       ▼
                                    ChromaDB vector store
```

**Authority boundary**: `ftsm-knowledge` owns document state (`INDEXING → READY | FAILED`) and the query log; `ftsm-rag` never writes business state. The primary path is RabbitMQ: indexing and deletion are driven by events with **atomic, idempotent state migration** on the consumer side (`UPDATE ... WHERE status = 'INDEXING'`), so duplicated deliveries are harmless. Reads (`ready-ids`) use synchronous HTTP.

**Degraded path (no MQ)**: if RabbitMQ is unreachable, `ftsm-rag` falls back to its in-process training thread, and the state machine would otherwise never leave `INDEXING`. So it also POSTs the authoritative manifest result to `ftsm-knowledge` (`POST /internal/docs/ready`, best-effort, same atomic `WHERE status = 'INDEXING'` guard). Both paths therefore converge on the same state, and either one may be retried safely.

## Key Features

- **Three-stage retrieval** — multi-query vector search (ChromaDB) + BM25 keyword search, fused with RRF, then re-ranked by the provider set in `config/rag.yml` (`rerank.provider`):

  | provider | how it re-ranks | requires | measured |
  | --- | --- | --- | --- |
  | `none` | keeps RRF order | — | — |
  | `dashscope` | `gte-rerank-v2` cross-encoder | a DashScope key **in good standing** | ~100 ms |
  | `vertex` | LLM listwise re-rank via the Vertex Gemini chat model | nothing extra (reuses the chat backend) | ~3.2 s warm |
  | `local` | `sentence-transformers` CrossEncoder | `pip install sentence-transformers` + a model name | local CPU |
  | `auto` | follows the chat backend: `dashscope` → DashScope if keyed; `vertex` → `none` | — | — |

  Re-ranking is **decoupled from the chat backend** and degrades non-silently: when the provider is unavailable the process logs one reason, keeps serving RRF order, and reports `rerank.active = false` plus `disabled_reason` from `GET /api/kb/stats`. Note `auto` resolves to `none` on the Vertex backend — the Vertex Ranking API is a separately-billed product (not enabled for this project), and the LLM listwise path costs ~3.2 s/query, so that trade-off is left to an explicit `provider: vertex`.
- **Dual-threshold rejection** — a query is answered only if one of these admits it, otherwise a fixed no-answer refusal is returned instead of a hallucination:
  1. **dense** — max cosine between the query vector and the top candidate chunks ≥ `dense_cosine_min` (0.66); computed explicitly because the Chroma collection is L2, so retrieval scores cannot be used as cosine;
  2. **BM25** — query-term coverage ≥ `bm25_coverage_min` (0.30) **and** ≥ `bm25_min_matches` (2) genuinely distinctive terms actually matched;
  3. **lexical overlap** — fallback only when the dense signal is unavailable.

  Thresholds are calibrated, not guessed: `scripts/calibrate_dense_threshold.py` runs the real retrieval path over 12 in-domain + 10 out-of-domain questions and reports recall / false-admit per branch. Current calibration: in-domain min 0.6847, out-of-domain max 0.6531 → 100% recall, 0% false-admit.
- **Event-driven indexing** — upload → knowledge service records `INDEXING` and publishes `doc.index.requested` → rag service indexes and replies `succeeded | failed`; failures after 3 retries land in `doc.index.dlq`.
- **Retrieval quality telemetry** — every retrieval publishes `retrieval.logged`; `GET /api/retrieval/quality` reports hit rate, average latency and sources.
- **Student auth** — PBKDF2-SHA256 (200k iterations) password hashing, byte-compatible with the legacy store (existing accounts importable); HMAC-signed session cookie verified at the gateway without a database round trip.
- **Semantic cache** — cosine-similarity cache (threshold 0.92) inside the rag service, with hit/miss statistics.
- **RAG evaluation suite** — `scripts/evaluate_rag.py` reports Source Hit Rate, MRR, Precision@5, Recall@5 and latency percentiles; export to JSON / Markdown / CSV.

## Services

| Service | Stack | Port | Responsibility |
| --- | --- | --- | --- |
| `ftsm-gateway` | Spring Cloud Gateway | 8080 | Routing, session verification (`X-Student-Id` injection), admin key, SSE passthrough |
| `ftsm-user` | Spring Boot 3 + MyBatis-Plus | 8101 | Student accounts, register/login/logout/me |
| `ftsm-conversation` | Spring Boot 3 + MyBatis-Plus | 8102 | Per-student conversations and messages |
| `ftsm-knowledge` | Spring Boot 3 + MyBatis-Plus + AMQP | 8103 | Doc state machine, query log, quality stats |
| `ftsm-rag` | FastAPI + LangChain (repo root Python code) | 8104 | Retrieval, rerank, generation, cache, indexing consumer, static English UI |

MQ contract: topic exchange `ftsm.doc.exchange` with `doc.index.requested | doc.index.succeeded | doc.index.failed | doc.deleted | retrieval.logged`.

## Quick Start

```bash
# 1) Infrastructure (MySQL with auto-initialized schema, RabbitMQ, Qdrant)
docker compose up -d

# 2) Java services — build once, then run the jars (each service needs its own JVM)
cd ftsm-java && mvn -DskipTests package && cd ..
./scripts/stack_up.sh          # host mode: 5 processes + readiness probes
# or: ./scripts/stack_docker.sh  # container mode (see script header)

# 3) Open the gateway
open http://127.0.0.1:8080/
```

`scripts/stack_up.sh` is the supported launcher: it loads `.env`, translates the
`MYSQL_*` names into the `FTSM_MYSQL_*` names Spring expects, preflights the jars /
venv / infrastructure, then probes each service on a **real route** and prints the
HTTP code (so a half-started service is visible instead of silently counted as up).

### Environment

⚠️ **Python reads `.env`; the Spring services do not.** They only see the process
environment, so anything they need must be exported before launch (this is what
`stack_up.sh` does). Names differ between the two sides:

| Purpose | `.env` (Python) | Environment (Spring) |
| --- | --- | --- |
| MySQL | `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` | `FTSM_MYSQL_HOST` / `FTSM_MYSQL_PORT` / `FTSM_MYSQL_USER` / `FTSM_MYSQL_PASSWORD` |
| RabbitMQ | — | `FTSM_RABBITMQ_HOST` / `FTSM_RABBITMQ_PORT` / `FTSM_RABBITMQ_USER` / `FTSM_RABBITMQ_PASSWORD` |
| Session signing | — | `FTSM_SESSION_SECRET` (shared by gateway + user service; **both fall back to the same dev default**, so overriding it on only one side breaks every login) |
| Admin key | `ADMIN_API_KEY` | `ADMIN_API_KEY` (gateway returns **500** on admin routes when unset) |
| LLM | `DASHSCOPE_API_KEY`, `LLM_BACKEND`, `VERTEX_*`, `GOOGLE_APPLICATION_CREDENTIALS` | — (Python only) |

`GOOGLE_APPLICATION_CREDENTIALS` in `.env` points at the container path `/ftsm/.gcp/...`;
in host mode it must point at the repo's `.gcp/` copy instead — `stack_up.sh` rewrites
it automatically when the configured path does not exist.

Degradation is intentional: if RabbitMQ or the knowledge service is unreachable, the rag
service reconnects with backoff, falls back to local training, and writes the resulting
index state back over HTTP (see *Authority boundary* above).

## API (through the gateway)

| Method | Path | Routed to | Notes |
| --- | --- | --- | --- |
| POST | `/api/auth/register` `/api/auth/login` `/api/auth/logout` | user | `GET /api/auth/me` requires session |
| GET/POST | `/api/conversations` | conversation | requires session; legacy response shapes preserved |
| GET/DELETE | `/api/conversations/{id}` | conversation | requires session |
| POST | `/api/upload` | rag | requires session; registers docs to knowledge |
| GET | `/api/training/status` | **rag** | the rag service owns `DATA_DIR` and the index |
| GET | `/api/documents` | **rag** | on-disk document list |
| GET | `/api/knowledge/stats` `/api/retrieval/quality` | knowledge | DB (registry + query log) authority |
| GET | `/api/kb/stats` | rag | manifest-backed index size + `rerank.active` |
| POST | `/api/training/start` | rag | **session only** (student re-index of their own uploads) |
| POST | `/api/knowledge/update` | rag | requires `X-Admin-Api-Key` |
| POST | `/api/chat` | rag | requires session; SSE character streaming |
| GET | `/api/cache/stats` `/api/scheduler/status` `/api/health` | rag | |

## Development Notes

- **Frontend**: the tracked UI (`web/guide.html` + `web/static/guide.js` for the English
  student portal, `web/legacy.html` + `web/static/legacy.js` for the legacy single-app
  view) calls the API with relative paths, so it works unchanged behind the gateway.
- **Database schema**: `docs/sql/schema.sql` (auto-applied by the MySQL container on first start). Epoch-second timestamps keep parity with the legacy Python contracts.
- **Build verification**: `mvn compile` (Java 17) passes for all five modules; Python sources pass `py_compile`. Runtime smoke tests require the infrastructure containers.
- **Desktop packaging** (PyInstaller/Tauri) is frozen with the legacy delivery; run the services with `docker compose` + `mvn`/`uvicorn` instead.

## RAG Evaluation

```bash
python scripts/evaluate_rag.py                                  # retrieval-only
python scripts/evaluate_rag.py --report-dir results/rag_eval    # with JSON/MD/CSV reports
python scripts/evaluate_rag.py --with-answer --report-dir results/rag_eval_answer
python scripts/evaluate_cache.py --report-dir results/cache_eval
```

Metrics: Source Hit Rate, first-hit rank, MRR, Precision@5, Recall@5, Answer Hit Rate, latency P50/P90.

## Honest Limitations

- Delivered as a graduation project: no production traffic, disaster recovery or compliance hardening.
- MQ retry counters are in-process (a crash mid-retry resets the count); the dead-letter queue is the safety net.
- The dense-side rejection gate computes direct cosine similarity (`_max_dense_cosine`) against the retrieved candidates; the bundled Qdrant container is currently unused (the vector store is ChromaDB).
- Evaluation datasets are small, self-built and model-assisted; metrics are not generalization claims.
