# Financial Regulation Agent — Architecture

## High-Level System Overview

<img src="architecture-overview.png" alt="High-Level System Overview" width="900" />

```mermaid
flowchart TB
    subgraph Clients["Clients"]
        WebUI["Web UI (HTML)"]
        API["REST API (streaming)"]
        CLI["CLI / Scripts"]
    end

    subgraph API Layer["API Layer"]
        FastAPI_Main["app/main.py\nPOST /query"]
        Webapp_Server["webapp/server.py\nPOST /ask"]
        Deps["app/dependencies.py\nAuth, Query extraction"]
    end

    subgraph Agent Core["Agent Core (LangGraph)"]
        Controller["RAGController\nquery_controller.py"]
        Graph["StateGraph\nbuilder.py"]
    end

    subgraph LLM["LLM & Embeddings"]
        LLM_Config["app/llm_config.py\nGemini / OpenAI"]
        Embeddings["Embeddings"]
    end

    subgraph Retrieval["Retrieval"]
        Hybrid["Hybrid Search\nBM25 + Vector + Cohere"]
        Chroma["ChromaDB\nVector Store"]
    end

    subgraph Tools["Tools (ToolRegistry)"]
        BankCapital["Bank Capital"]
        Treasury["Treasury / SOFR"]
        FedBS["Fed Balance Sheet"]
        MarketData["Market Data"]
    end

    subgraph Ingestion["Ingestion Pipeline"]
        Spiders["Scrapy Spiders\nSEC, FOMC, FDIC, CFTC,\nBasel, FCA, FinCEN"]
        Pipelines["Pipelines\nCleaner, SEC, VectorStore"]
        Chroma_Ingest["ChromaDB"]
    end

    subgraph Observability["Observability"]
        LangSmith["LangSmith"]
        Prometheus["Prometheus metrics"]
        Logger["Structured logging"]
    end

    WebUI --> Webapp_Server
    API --> FastAPI_Main
    CLI --> Graph

    FastAPI_Main --> Deps
    Webapp_Server --> Deps
    FastAPI_Main --> Graph
    Webapp_Server --> Controller
    Controller --> Graph

    Graph --> LLM_Config
    Graph --> Hybrid
    Graph --> Tools
    Hybrid --> Chroma
    Pipelines --> Chroma_Ingest
    Spiders --> Pipelines

    Graph -.-> LangSmith
    Graph -.-> Prometheus
```

---

## LangGraph Workflow (Agent Pipeline)

<img src="langgraph-workflow.png" alt="LangGraph Workflow" width="900" />

```mermaid
flowchart LR
    subgraph Entry["Entry"]
        START([START])
        Query["query"]
    end

    subgraph Classification["Classification & Planning"]
        EF["extract_filters\n(filters + route)"]
        Plan["planner_node\ngenerate_plan"]
        Router["router_node\nroute_query"]
    end

    subgraph RetrievalPath["Retrieval Path"]
        RAG["retrieval_node"]
        CRAG["crag_evaluator\ncorrect|ambiguous|incorrect"]
        Reject["crag_reject\n(clarify)"]
        Decompose["decompose_recompose\n(refine docs)"]
    end

    subgraph Execution["Execution Branches"]
        Tools_N["tools_node"]
        Struct["structured_node"]
        Calc["calculation_node"]
        Direct["direct_response\n(other route)"]
    end

    subgraph Synthesis["Synthesis & Validation"]
        Merge["synthesis_node\nmerge_outputs"]
        Critic["critic_node\nvalidate_response"]
        Final["finalize_node"]
    end

    START --> Query
    Query --> EF --> Plan --> Router

    Router -->|"rag|structured|calculation"| RAG
    Router -->|"other"| Direct

    RAG --> CRAG
    CRAG -->|incorrect| Reject
    CRAG -->|ambiguous| Decompose
    CRAG -->|correct| Tools_N
    CRAG -->|correct| Struct
    CRAG -->|correct| Calc
    CRAG -->|correct| Merge
    Decompose --> Tools_N
    Decompose --> Struct
    Decompose --> Calc
    Decompose --> Merge

    Tools_N --> Merge
    Struct --> Merge
    Calc --> Merge

    Merge --> Critic
    Critic -->|invalid| Plan
    Critic -->|valid| Final
    Direct --> Final
    Reject --> Final
    Final --> END([END])
```

---

## Data Flow: Query to Answer

<img src="query-to-answer.png" alt="Data Flow: Query to Answer" width="900" />

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI / Webapp
    participant Dep as Dependencies
    participant Ctrl as RAGController
    participant G as LangGraph
    participant EF as extract_filters
    participant Plan as planner
    participant Rtr as router
    participant RAG as retrieval
    participant CRAG as CRAG evaluator
    participant Synth as synthesis
    participant Crt as critic
    participant VS as ChromaDB
    participant LLM as LLM (Gemini/OpenAI)

    U->>API: POST /query or /ask
    API->>Dep: Auth, extract query
    Dep-->>API: query string
    API->>Ctrl: controller.ask(query)
    Ctrl->>G: ainvoke(initial_state)

    G->>EF: state
    EF->>LLM: extract filters + route
    LLM-->>EF: JSON (filters, route)
    EF-->>G: filters, route, intent

    G->>Plan: state
    Plan->>LLM: generate plan
    LLM-->>Plan: plan steps
    Plan-->>G: plan

    G->>Rtr: state
    Rtr-->>G: route (rag|structured|calculation|other)

    alt route = rag|structured|calculation
        G->>RAG: state
        RAG->>VS: hybrid search (BM25 + vector)
        VS-->>RAG: docs
        RAG->>LLM: Cohere rerank
        RAG-->>G: retrieved_docs

        G->>CRAG: evaluate retrieval
        CRAG->>LLM: assess quality
        CRAG-->>G: confidence (correct|ambiguous|incorrect)

        alt correct / ambiguous (refined)
            G->>Synth: state + docs
            Synth->>LLM: merge plan + docs → answer
            LLM-->>Synth: synthesized_response
            Synth-->>G: synthesized_response
        end

        G->>Crt: state
        Crt->>LLM: validate against sources
        LLM-->>Crt: validation_result
        Crt-->>G: valid/invalid + feedback

        alt invalid
            G->>Plan: refine with feedback (loop)
        else valid
            G->>Ctrl: final_output
        end
    else route = other
        G->>G: direct_response (LLM only)
    end

    Ctrl-->>API: { answer, ... }
    API-->>U: JSON response
```

---

## Component Map

| Layer | Components | Purpose |
|-------|------------|---------|
| **Entry** | `app/main.py`, `webapp/server.py`, `scripts/run_agent.py` | HTTP / CLI entry points |
| **Dependencies** | `app/dependencies.py` | API key auth, query extraction, request context |
| **Controller** | `webapp/retrieval/query_controller.py` | Bridges HTTP → LangGraph, timeout, rate-limit handling |
| **Graph** | `graph/builder.py`, `graph/state.py` | LangGraph workflow definition |
| **Nodes** | `graph/nodes/*` | extract_filters, planner, router, RAG, CRAG, tools, structured, calculation, merge, critic |
| **Retrieval** | `retrieval/hybrid_search.py`, `retrieval/vector_store.py` | BM25 + vector + Cohere rerank → ChromaDB |
| **LLM** | `app/llm_config.py` | Gemini / OpenAI, embeddings |
| **Tools** | `tools/registry.py`, `tools/*.py` | Bank Capital, Treasury, Fed Balance Sheet, Market Data |
| **Ingestion** | `ingestion/regcrawler/` | Scrapy spiders, pipelines, Chroma upsert |
| **Observability** | `observability/`, LangSmith, Prometheus | Logging, tracing, metrics |
