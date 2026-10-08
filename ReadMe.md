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
                        hybrid retrieval (ChromaDB vector + BM25 → RRF → gte-rerank-v2),
                        semantic cache, ReAct agent, chat SSE, indexing consumer
                                       ▼
                                    ChromaDB vector store
```

**Authority boundary**: `ftsm-knowledge` owns document state (`INDEXING → READY | FAILED`) and the query log; `ftsm-rag` never writes business state. Indexing and deletion happen exclusively through RabbitMQ events with **atomic, idempotent state migration** on the consumer side (`UPDATE ... WHERE status = 'INDEXING'`), so duplicated deliveries are harmless. Reads (`ready-ids`) use synchronous HTTP.

## Key Features

- **Three-stage retrieval** — multi-query vector search (ChromaDB) + BM25 keyword search, fused with RRF, re-ranked by DashScope `gte-rerank-v2`.
- **Dual-threshold rejection** — a query is answered only if the dense semantic signal or BM25 coverage (≥ 0.30) admits it; otherwise a fixed no-answer refusal is returned instead of a hallucination.
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

# 2) Java services
cd ftsm-java
mvn spring-boot:run -pl ftsm-user ftsm-conversation ftsm-knowledge ftsm-gateway

# 3) Python AI service (from the repo root)
pip install -r requirements.txt
uvicorn web_app:app --host 127.0.0.1 --port 8104

# 4) Open the gateway
open http://127.0.0.1:8080/
```

Required environment (see `.env.example`): `DASHSCOPE_API_KEY`, `FTSM_SESSION_SECRET` (shared by gateway and user service), `ADMIN_API_KEY` (for `/api/training/start` and `/api/knowledge/update`), optional `FTSM_RABBITMQ_URL` and `FTSM_KNOWLEDGE_URL`.

Degradation is intentional: if RabbitMQ or the knowledge service is unreachable, the rag service falls back to local training threads so the legacy single-app mode keeps working.

## API (through the gateway)

| Method | Path | Service | Notes |
| --- | --- | --- | --- |
| POST | `/api/auth/register` `/api/auth/login` `/api/auth/logout` | user | `GET /api/auth/me` requires session |
| GET/POST | `/api/conversations` | conversation | requires session; legacy response shapes preserved |
| GET/DELETE | `/api/conversations/{id}` | conversation | requires session |
| POST | `/api/upload` | rag | requires session; registers docs to knowledge |
| GET | `/api/documents` `/api/knowledge/stats` `/api/training/status` `/api/retrieval/quality` | knowledge | document list now comes from the DB authority |
| POST | `/api/training/start` `/api/knowledge/update` | rag | requires `X-Admin-Api-Key` |
| POST | `/api/chat` | rag | requires session; SSE character streaming |
| GET | `/api/cache/stats` `/api/scheduler/status` `/api/health` | rag | |

## Development Notes

- **Frontend**: the tracked UI (`web/legacy.html`, `web/static/legacy.js`) is English-only and calls the API with relative paths, so it works unchanged behind the gateway.
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
- The dense-side rejection gate uses a query-term semantic signal; it will switch to direct cosine thresholds when the vector store migrates to Qdrant's cosine space.
- Evaluation datasets are small, self-built and model-assisted; metrics are not generalization claims.
