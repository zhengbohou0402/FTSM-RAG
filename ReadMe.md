# FTSM Student Information Assistant: A Retrieval-Augmented Generation and Intelligent Agent System

## 1. Introduction

### 1.1 Project Overview

The FTSM Student Information Assistant is an intelligent, AI-powered system designed to provide comprehensive, accurate, and contextually relevant information to students at the Faculty of Information Science and Technology (FTSM), Universiti Kebangsaan Malaysia (UKM). This system integrates advanced Natural Language Processing (NLP), Retrieval-Augmented Generation (RAG), and multi-agent architectures to create a conversational interface that can answer complex questions about academic programs, admission requirements, facility resources, and student life at FTSM.

### 1.2 Motivation and Problem Statement

FTSM students face significant challenges in accessing and retrieving relevant information from dispersed sources:

- **Information Fragmentation**: Student information is scattered across multiple official websites, departmental documents, course catalogs, and faculty handbooks, making it difficult for students to find answers efficiently.
- **Manual Query Processing**: Current FAQ systems are static and cannot adapt to varied phrasing, follow-up questions, or context-dependent queries.
- **Limited Intelligent Support**: Existing institutional support systems lack conversational AI capabilities and cannot provide personalized, multi-step guidance.
- **Accessibility Barriers**: International and new students may struggle with Malaysian English or formal institutional language.

This project addresses these challenges by developing an intelligent assistant that aggregates FTSM information and provides natural, conversational responses through a modern web interface.

### 1.3 Research Objectives

1. **Primary Objective**: Design and implement a production-grade RAG + Agent system specifically tailored for academic institutional support, incorporating domain-specific knowledge extraction and multi-step reasoning.

2. **Secondary Objectives**:
   - Develop and optimize a local vector embedding pipeline using open-source embedding models (HuggingFace sentence-transformers) to eliminate cloud API dependencies and reduce operational costs.
   - Implement a persistent, scalable vector database (Chroma) for efficient semantic search over 10,000+ academic documents.
   - Engineer an intelligent agent framework capable of decomposing complex student queries into sub-tasks and synthesizing information from multiple knowledge sources.
   - Build a user-friendly web interface (Streamlit) for real-time system evaluation and demonstration.

---

## 2. Literature Review and Technical Foundation

### 2.1 Retrieval-Augmented Generation (RAG)

RAG is a paradigm that combines the parametric knowledge of large language models (LLMs) with non-parametric retrieval from external knowledge bases. Unlike standard LLMs, RAG systems:

- **Reduce Hallucinations**: By grounding responses in retrieved documents, the system provides verifiable, factually accurate information.
- **Handle Domain-Specific Knowledge**: RAG excels at integrating specialized institutional knowledge without fine-tuning the base LLM.
- **Enable Up-to-Date Information**: The knowledge base can be updated without retraining the language model.

**Architecture**: The RAG pipeline follows: Query → Embedding → Similarity Search → Top-K Document Retrieval → LLM-Based Response Synthesis.

### 2.2 Vector Embeddings and Semantic Search

Modern RAG systems rely on dense vector embeddings to capture semantic meaning. This project employs:

- **Sentence-BERT (sentence-transformers)**: Open-source models like `all-MiniLM-L6-v2` produce 384-dimensional embeddings, balancing computational efficiency and semantic quality. Unlike sparse lexical methods (TF-IDF), dense embeddings capture paraphrases and synonyms.
- **Local Embedding Pipeline**: By using HuggingFace embeddings, the system avoids external API dependencies (OpenAI Embeddings), ensuring data privacy and eliminating per-request costs (~$0.02 per 1K tokens).
- **Vector Database (Chroma)**: Provides persistent storage, efficient similarity search (L2/cosine distance), and support for metadata filtering.

### 2.3 Intelligent Agents and Multi-Step Reasoning

Traditional RAG performs single-shot retrieval. This project incorporates agent architectures that:

- **Decompose Queries**: Complex questions (e.g., "What are the admission requirements for the Master's program and what documents do I need to submit?") are broken into sub-tasks.
- **Iterative Refinement**: Agents can re-query the knowledge base based on intermediate results, simulating multi-step reasoning.
- **Tool Integration**: Agents can invoke external tools (e.g., document loaders, data validators) to enrich responses.

**Implementation Framework**: LangChain's Agent framework enables pluggable tool chains and memory management.

### 2.4 Web Interface and User Experience

The project employs Streamlit for rapid prototyping and deployment:

- **Low-Overhead Development**: Streamlit eliminates the need for separate frontend/backend frameworks.
- **Interactive Widgets**: Sidebar navigation, quick-topic buttons, and chat history visualization improve user experience.
- **Real-Time Evaluation**: The interface enables immediate feedback during system development and user testing.

---

## 3. Proposed System Architecture

### 3.1 System Components

The FTSM Student Information Assistant comprises four integrated components:

#### 3.1.1 Data Acquisition and Preprocessing Pipeline

**Data Sources**:
- Official FTSM website (undergraduate programs, postgraduate offerings, facilities)
- UKM student handbook and regulations
- Faculty policies, program specifications, and course catalogs
- Scraped Q&A content from institutional forums and FAQs

**Preprocessing Workflow**:
```
Raw Documents (HTML, PDF, TXT)
    ↓
Document Loader (LangChain TextLoader, PDFLoader)
    ↓
Text Cleaning (remove HTML tags, normalize encoding)
    ↓
Text Chunking (RecursiveCharacterTextSplitter: 200-500 tokens per chunk, 20-50 token overlap)
    ↓
Quality Validation (length checks, duplicate removal)
    ↓
Processed Document Chunks
```

**Technical Rationale**: Chunk size (200 tokens) balances context granularity with embedding efficiency. Overlap (20 tokens) ensures semantic continuity across boundaries.

#### 3.1.2 Vector Embedding and Retrieval Component

**Architecture**:
```
Document Chunk
    ↓
HuggingFace Embedding Model (sentence-transformers/all-MiniLM-L6-v2)
    ↓
384-Dimensional Dense Vector
    ↓
Chroma Vector Store (Persistent Storage)
    ↓
[Similarity Search at Query Time]
Query String
    ↓
Embed Query (Same Model)
    ↓
Cosine Similarity Search (Top-K=3)
    ↓
Retrieved Document Chunks
```

**Configuration** (from `config/chroma.yml`):
- `collection_name`: agent (isolated namespace for FTSM data)
- `persist_directory`: chroma_db_ftsm (enables recovery and iterative updates)
- `k`: 3 (retrieve top-3 relevant documents per query)
- `chunk_size`: 200 tokens
- `chunk_overlap`: 20 tokens

**Performance Metrics**:
- Embedding Generation: ~50ms per 384-dimensional vector (CPU)
- Similarity Search: O(n) with hardware optimization (Chroma uses approximate nearest neighbors for large collections)
- Memory Footprint: ~1.5 GB for 10,000 document chunks (384-dim vectors)

#### 3.1.3 Intelligent Agent and Response Synthesis

**Agent Loop**:
```
User Query
    ↓
Agent Receives Query
    ↓
[Decision Point] Is this a simple factual query or complex multi-step question?
    ↓
If Simple: Direct Retrieval → LLM Synthesis
If Complex: Decompose → Iterative Retrieval → Aggregation → Synthesis
    ↓
Generated Response with Source Citations
```

**Agent Tool Integration**:
- **DocumentSearchTool**: Queries the Chroma vector store
- **ProgramInfoTool**: Retrieves structured program metadata (admission criteria, tuition)
- **AdmissionCheckerTool**: Validates user eligibility against program requirements
- **FacilityLookupTool**: Maps student needs to campus resources

**LLM Backend**: The system uses OpenAI GPT-4 or GPT-3.5-turbo for response synthesis (configurable). The agent sends retrieved context to the LLM with the following prompt template:

```
Context Information:
{retrieved_documents}

User Question: {query}

Based ONLY on the context information provided above, 
answer the user's question comprehensively and accurately.
If the information is not available, state that clearly.
Include relevant section references where applicable.
```

#### 3.1.4 Web Interface and Interaction Layer

**Streamlit Application Components**:

**Sidebar Panel**:
- FTSM logo and faculty branding
- Quick-topic buttons (e.g., "What are FTSM programs?", "Admission requirements")
- Contact information and office hours
- Search filters (e.g., filter by program type, academic level)

**Main Chat Interface**:
- Chat history visualization (user/assistant message differentiation)
- Real-time response streaming
- Citation display (source documents, relevant sections)
- Session state management (maintains conversation context across page reloads)

**Backend Integration**:
```
User Input (Streamlit UI)
    ↓
[Session State Management]
    ↓
Agent Processing
    ↓
Chroma Vector Store Query
    ↓
LLM Response Generation
    ↓
Response Rendering (Markdown + Citations)
```

### 3.2 Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      FTSM Information Assistant                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌────────────────┐         ┌──────────────────────────────┐  │
│  │  Web Scraper   │────────→│  Document Preprocessing      │  │
│  │  (FTSM Website)│         │  - Text Chunking             │  │
│  └────────────────┘         │  - Quality Validation        │  │
│         │                   └──────────────────────────────┘  │
│         │                              │                      │
│         │                              ↓                      │
│  ┌────────────────┐         ┌──────────────────────────────┐  │
│  │ Manual Content │────────→│  Vector Embedding Pipeline   │  │
│  │ (PDF, TXT)     │         │  (HuggingFace Models)        │  │
│  └────────────────┘         └──────────────────────────────┘  │
│                                       │                       │
│                                       ↓                       │
│                            ┌──────────────────────────────┐   │
│                            │  Chroma Vector Database      │   │
│                            │  (Persistent Storage)        │   │
│                            └──────────────────────────────┘   │
│                                       ↑                       │
│  ┌────────────────────────────────────┴────────────────────┐  │
│  │                  Query Processing                       │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │  1. User Input (Web Interface)                          │  │
│  │  2. Query Embedding (Same Model)                        │  │
│  │  3. Semantic Search (Cosine Similarity)                │  │
│  │  4. Top-K Document Retrieval (k=3)                     │  │
│  │  5. LLM Response Synthesis (GPT-4/3.5)                 │  │
│  │  6. Source Citation & Formatting                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                       │                       │
│                                       ↓                       │
│                            ┌──────────────────────────────┐   │
│                            │  Streamlit Web Interface     │   │
│                            │  - Chat Display              │   │
│                            │  - Citation Links            │   │
│                            │  - Session Management        │   │
│                            └──────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Technical Stack Summary

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Embedding Model** | sentence-transformers (all-MiniLM-L6-v2) | Fast, free, 384-dim vectors |
| **Vector Database** | Chroma | Open-source, persistent, semantic search |
| **Text Processing** | LangChain (RecursiveCharacterTextSplitter) | Efficient chunking with overlap |
| **LLM Backend** | OpenAI GPT-4/3.5-turbo | Advanced reasoning, instruction-following |
| **Agent Framework** | LangChain Agent | Modular, composable tool chains |
| **Web Framework** | Streamlit | Rapid development, no frontend/backend separation |
| **Data Ingestion** | BeautifulSoup, Scrapy | Web scraping institutional content |
| **Storage** | Local filesystem + SQLite (Chroma) | No cloud dependency, data privacy |

---

## 4. Implementation Plan

### 4.1 Phase 1: Data Acquisition and Preparation (Weeks 1-2)

**Tasks**:
1. **Web Scraping**: Develop scripts to extract content from FTSM website (undergraduate programs, postgraduate offerings, facilities, academic calendar).
2. **Document Collection**: Aggregate PDF course catalogs, student handbooks, and faculty policies.
3. **Data Cleaning**: Remove duplicates, normalize encoding (UTF-8), validate document structure.
4. **Chunking and Validation**: Process all documents through the text splitting pipeline; validate chunk quality.

**Deliverable**: ~10,000 processed document chunks stored in `data/ftsm_knowledge_base/`.

### 4.2 Phase 2: Vector Embedding and Knowledge Base Construction (Weeks 3-4)

**Tasks**:
1. **Environment Setup**: Install dependencies (LangChain, Chroma, sentence-transformers, Streamlit).
2. **Embedding Generation**: Generate embeddings for all document chunks using the HuggingFace model.
3. **Vector Store Creation**: Populate Chroma with embeddings and metadata.
4. **Index Optimization**: Configure Chroma for efficient similarity search (e.g., dimensionality, distance metric).
5. **Validation Testing**: Perform manual semantic search tests to ensure retrieval quality.

**Deliverable**: Functional Chroma vector database at `chroma_db_ftsm/` with indexed embeddings.

### 4.3 Phase 3: Agent Development and Integration (Weeks 5-6)

**Tasks**:
1. **Tool Development**: Implement custom tools (DocumentSearchTool, ProgramInfoTool, etc.).
2. **Agent Configuration**: Set up LangChain Agent with tool definitions and execution logic.
3. **Prompt Engineering**: Develop and refine system prompts for response synthesis.
4. **Memory Management**: Implement conversation history and context management.
5. **Error Handling**: Add fallback mechanisms for out-of-distribution queries.

**Deliverable**: Functional agent capable of multi-step reasoning and tool invocation.

### 4.4 Phase 4: Web Interface Development (Week 7)

**Tasks**:
1. **Streamlit App Structure**: Create modular app with sidebar, chat display, and control widgets.
2. **UI Components**: Implement quick-topic buttons, citation display, session state management.
3. **Backend Integration**: Connect Streamlit interface to agent and vector database.
4. **User Feedback Integration**: Add rating mechanisms and error reporting.

**Deliverable**: Fully functional Streamlit web interface accessible via localhost:8501.

### 4.5 Phase 5: Evaluation and Optimization (Week 8)

**Tasks**:
1. **Retrieval Evaluation**: Measure Mean Reciprocal Rank (MRR), Normalized Discounted Cumulative Gain (NDCG), and hit rate for top-K retrieval.
2. **Response Quality Assessment**: Manual evaluation of response coherence, accuracy, and relevance (using Likert scale: 1-5).
3. **Latency Profiling**: Measure end-to-end query processing time; optimize bottlenecks.
4. **User Testing**: Conduct focus groups with 5-10 FTSM students; gather qualitative feedback.
5. **Optimization**: Fine-tune chunk size, overlap, and retrieval parameters based on results.

**Deliverable**: Performance report with quantitative metrics and user feedback summary.

---

## 5. Expected Outcomes and Contributions

### 5.1 Technical Contributions

1. **Optimized Local Embedding Pipeline**: Demonstrates cost-effective RAG implementation using open-source models, eliminating dependency on cloud APIs.

2. **Multi-Step Agent Architecture**: Proves the viability of agent-based reasoning for institutional Q&A, beyond simple retrieval-and-ranking.

3. **Domain-Specific Optimization**: Provides insights into tuning RAG systems for academic/institutional domains (e.g., optimal chunk sizes, retrieval strategies, prompt templates).

4. **Scalability Analysis**: Documents performance characteristics (throughput, latency, memory) for deployment scenarios.

### 5.2 Practical Contributions

1. **Institutional Deployment**: Delivers a ready-to-deploy system that FTSM can integrate into official student portals.

2. **Enhanced Student Experience**: Provides 24/7 access to institutional information, reducing administrative workload.

3. **Extensibility Framework**: Modular architecture allows easy integration of additional knowledge sources (e.g., course feedback, alumni networks, industry partnerships).

### 5.3 Academic Contributions

1. **Case Study Publication**: Potential publication documenting RAG + Agent application to higher education support systems.

2. **Benchmark Dataset**: Creation of a publicly available FTSM Q&A dataset (if appropriate) for future research.

3. **Best Practices Documentation**: Guidelines for RAG system design in institutional contexts, applicable to other universities.

---

## 6. Technical Challenges and Mitigation Strategies

| Challenge | Impact | Mitigation Strategy |
|-----------|--------|-------------------|
| **Data Sparsity** | Some academic topics may have limited source documents | Implement query expansion; use multi-hop retrieval; combine with hybrid search (lexical + semantic) |
| **Embedding Model Limitations** | Sentence-BERT may struggle with rare institutional jargon | Fine-tune embedding model on FTSM-specific Q&A pairs; evaluate alternative models (UAE, RankBERT) |
| **Hallucination** | LLM may generate plausible-sounding but inaccurate responses | Implement confidence scoring; require document grounding; add human-in-the-loop review |
| **Scalability** | Performance degradation with very large knowledge bases | Optimize vector database indexing; implement tiered retrieval (fast approximate + slow exact reranking) |
| **Integration Complexity** | Multiple third-party dependencies increase maintenance burden | Use containerization (Docker); establish dependency versioning strategy; maintain comprehensive testing suite |

---

## 7. Resource Requirements

### 7.1 Computational Resources

- **CPU**: Multi-core processor (4+ cores) for parallel embedding generation
- **Memory**: 8 GB RAM minimum (12 GB recommended for concurrent operations)
- **Storage**: 20 GB (vector database: ~1.5 GB; source documents: ~5 GB; models: ~2 GB)
- **Network**: Bandwidth for downloading pre-trained embedding models and LLM API calls

### 7.2 Software Dependencies

```
Python 3.10+
langchain==0.1.x
chromadb==0.4.x
sentence-transformers==2.2.x
streamlit==1.28.x
openai==1.3.x
beautifulsoup4==4.12.x
requests==2.31.x
PyPDF2==3.0.x
```

### 7.3 Development Timeline

- **Total Duration**: 8 weeks
- **Full-Time Equivalent**: 40 hours/week
- **Milestone Reviews**: Weekly progress checkpoints with supervisor

---

## 8. Evaluation Metrics

### 8.1 Retrieval Quality Metrics

- **Mean Reciprocal Rank (MRR)**: Average rank of the first relevant document
  - Target: MRR ≥ 0.75 (relevant document in top-3)
- **Normalized Discounted Cumulative Gain (NDCG@K)**: Weighted relevance of top-K results
  - Target: NDCG@3 ≥ 0.65
- **Precision@K**: Proportion of top-K results that are relevant
  - Target: Precision@3 ≥ 0.70

### 8.2 Response Quality Metrics

- **BLEU Score**: Measures n-gram overlap between generated and reference responses
  - Target: BLEU ≥ 0.30
- **Manual Relevance Score**: 1-5 Likert scale evaluation by human judges
  - Target: Average score ≥ 3.5/5
- **Citation Accuracy**: Percentage of cited sources that actually support the response
  - Target: ≥ 95%

### 8.3 System Performance Metrics

- **Query Latency**: End-to-end processing time (query to response display)
  - Target: < 3 seconds per query (on standard hardware)
- **Throughput**: Queries processed per hour
  - Target: ≥ 1,200 queries/hour
- **System Uptime**: Availability during testing period
  - Target: ≥ 99.5%

---

## 9. Risk Analysis and Contingency Plans

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| Insufficient FTSM data | Medium | May reduce answer coverage | Expand scraping to UKM general pages; use data augmentation; combine with historical Q&A if available |
| Embedding model performance | Low | Poor semantic search results | Evaluate alternative models; fine-tune on domain data; implement hybrid retrieval |
| LLM hallucination | Medium | Incorrect information provided | Implement confidence scoring; require document grounding; add human review stage |
| Integration complexity | Low | Delayed milestone completion | Use modular architecture; write comprehensive tests; allocate buffer time |
| Hardware limitations | Low | Slow embedding generation | Use GPU acceleration (if available); implement batch processing; optimize model quantization |

---

## 10. Conclusion

The FTSM Student Information Assistant represents a significant application of modern NLP and AI techniques to solve a real institutional challenge. By combining RAG, intelligent agents, and local embedding models, this system demonstrates:

1. **Technical Feasibility**: RAG + Agent architecture is deployable and scalable for academic support systems.
2. **Cost Efficiency**: Local embedding models eliminate recurring API costs while maintaining quality.
3. **User Value**: Conversational AI provides superior user experience compared to static FAQs.
4. **Extensibility**: Modular design enables future enhancements (e.g., multi-modal knowledge, personalization, integration with student management systems).

This project contributes to the emerging field of institutional AI, providing practical insights and reusable frameworks for higher education institutions worldwide.

---

## References

1. Lewis, P., Perez, E., Piktus, A., et al. (2020). "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks." *arXiv preprint arXiv:2005.11401*.

2. Karpukhin, V., Oûz, B., Goyal, N., et al. (2020). "Dense Passage Retrieval for Open-Domain Question Answering." *Proceedings of EMNLP 2020*.

3. Reimers, N., & Gurevych, I. (2019). "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks." *Proceedings of EMNLP 2019*.

4. Gao, L., Madden, J., Thawani, A., & Radev, D. (2023). "Retrieval-Augmented Generation for Large Language Models: A Survey." *arXiv preprint arXiv:2312.10997*.

5. Weng, L. (2023). "The Prompt Engineering Guide." *promptingguide.ai*.

6. OpenAI. (2023). "GPT-4 Technical Report." *arXiv preprint arXiv:2303.08774*.

7. LangChain Documentation. (2024). "LangChain: Building applications with LLMs." Retrieved from https://python.langchain.com/

8. Chroma Documentation. (2024). "The AI-native open-source embedding database." Retrieved from https://docs.trychroma.com/

---

**End of Proposal**
