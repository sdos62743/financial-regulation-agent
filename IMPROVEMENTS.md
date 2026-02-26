# Financial Regulation Agent — Improvement Plan

One category at a time. Includes structural changes, logic improvements, and prompt/graph alignment.

---

## Category 1: Technical Debt & Cleanup

### 1.1 Builder Debug Code
- **File**: `graph/builder.py`
- **Issue**: Commented original flow, `iterations >= 1` debug mode (validation loop effectively disabled)
- **Logic**: Restore intended validation loop (`iterations >= 3`), remove commented blocks
- **Prompt/Node**: N/A

### 1.2 SeleniumMiddleware
- **Status**: ✅ Done — removed from settings (comment cleaned)

### 1.3 State Key Inconsistency
- **Issue**: `documents` vs `retrieved_docs` — validation node checks both; state defines `retrieved_docs`
- **Logic**: Standardize on `retrieved_docs` everywhere; remove `documents` fallback or document the dual-key design
- **Files**: `graph/nodes/validation.py`, `graph/state.py`

### 1.4 Duplicate Safe Message
- **Issue**: Same "I can't confirm..." message in `finalize_response` (builder) and `validation` node
- **Logic**: Extract to shared constant (e.g. `graph/constants.py` or `graph/prompts/`) and reuse

---

## Category 2: Validation Loop & Critic Logic

### 2.1 Structured Output for Validation
- **Current**: Regex parsing of `valid: true|false` from free text — brittle
- **Logic**: Use Pydantic structured output (e.g. `ValidationResult(valid: bool, reason: str)`) instead of regex
- **Prompt**: `validate.txt` — change OUTPUT FORMAT to instruct JSON/structured output matching schema
- **Node**: `validation.py` — replace `_parse_valid_flag` with structured parse

### 2.2 Validation Prompt: `is_retry` Passed But Not Used
- **Current**: `validate.txt` says "If this is a retry, be slightly more lenient" but has no `{is_retry}` placeholder. Node passes `is_retry` but it's ignored — LLM never knows if it's a retry.
- **Logic**: Add conditional line to prompt: when `is_retry=True`, inject "**Note: This is a RETRY.** Be slightly more lenient." into the prompt (or add `{retry_note}` placeholder that node sets to this text when is_retry else "")

### 2.3 Feedback Loop to Planner
- **Current**: On invalid, we return `safe_msg` and loop to `planner_node` — but planner gets no feedback about *why* it failed
- **Logic**: Pass `validation_feedback` (reason from critic) into state; planner prompt receives it and can adjust plan
- **Prompt**: `plan.txt` — add optional `{validation_feedback}` when present
- **Node**: `reasoning.py` — read `validation_feedback` from state; `validation.py` — return `reason` in state

### 2.4 Configurable Max Iterations
- **Logic**: `MAX_VALIDATION_ITERATIONS` env var (default 3) instead of hardcoded 1 or 3
- **File**: `graph/builder.py` — `decide_end`

---

## Category 3: Graph Flow & Routing Logic

### 3.1 Conditional Tools Routing
- **Current**: `retrieval_node` → always → `tools_node` → `synthesis_node`. Tools node runs even when plan has no `tool:` steps
- **Logic**: Add conditional edge: only go to `tools_node` when plan contains `tool:`; otherwise `retrieval_node` → `synthesis_node` directly
- **Implementation**: New `route_after_retrieval(state)` that returns `"tools"` or `"synthesis"`

### 3.2 Plan Format Alignment
- **Current**: Router/tools expect `tool: <name>` in plan steps. Plan prompt doesn't explicitly instruct this format
- **Prompt**: `plan.txt` — add: "When a tool is needed, use format: 'tool: <tool_name> <args if any>' (e.g. 'tool: treasury_rates')"
- **Node**: `call_tools` in builder — already parses `tool:`; ensure plan prompt produces it

### 3.3 Structured Node Has No Retrieval
- **Current**: `structured_node` reads `retrieved_docs` from state — but when routed to `structured`, we skip `retrieval_node`!
- **Logic**: Either (a) route structured through retrieval first, or (b) structured node fetches docs itself. Currently structured gets empty docs when routed directly.
- **Graph**: `structured` is alternate path from planner — it never gets retrieval. **Fix**: Route `structured` → `retrieval_node` → `structured_node` OR have structured node call hybrid_search when docs empty.

---

## Category 4: Retrieval & Schema Alignment

### 4.1 Doc Type Schema Mismatch
- **Ingestion**: Spiders use `type`: "enforcement", "speech", "press_release", "litigation_release", etc.
- **extract_filters prompt**: Uses "types" with values like "press_release", "publication", "rule", "guidance" — and "enforcement" maps to category, not type
- **hybrid_search**: Filters on `type` (artifact) and `category` (semantic)
- **Logic**: Align extract_filters output with what hybrid_search expects. Ensure `doc_types`/`types` in filters match Chroma `type` values.

### 4.2 Extract Filters vs Hybrid Search Schema
- **extract_filters**: Returns `regulators`, `categories`, `types`, `year`, `jurisdiction`, `sort`
- **hybrid_search**: Expects `regulators`, `categories`, `types` (or `doc_types`), `year`, `jurisdiction`, `spiders`, `source_types`, `sort`
- **Logic**: extract_filters doesn't output `spiders` or `source_types` — OK if null. Ensure `types` from prompt maps to hybrid_search `doc_types`.

### 4.3 RRF_K and Pool Limits
- **Logic**: Move to config/env: `HYBRID_RRF_K`, `HYBRID_BM25_POOL`, etc.

---

## Category 5: Prompts ↔ Node Alignment

### 5.1 classify_intent
- **Prompt**: Expects `{query}`. Output: JSON `{category: "..."}`.
- **Node**: Uses `IntentSchema` Pydantic — aligned. Heuristic fallback exists.
- **Gap**: None significant.

### 5.2 extract_filters
- **Prompt**: Expects `{query}`. Output: JSON with regulators, categories, types, year, jurisdiction, sort.
- **Node**: Parses JSON, normalizes, merges with heuristics. Uses `types` and `doc_types` from raw.
- **Gap**: Prompt says "types" but hybrid_search may expect `doc_types` in some code paths — verify `_normalize_filters` maps correctly.

### 5.3 plan (reasoning)
- **Prompt**: Expects `{query}`, `{intent}`. Output: JSON `{steps: [...], rationale: "..."}`.
- **Node**: Uses `ExecutionPlan` Pydantic. Returns `plan` (steps) and `plan_rationale`.
- **Gap**: Plan doesn't instruct `tool: <name>` format for tool steps — add to prompt. Plan doesn't receive `validation_feedback` on retry — add when implementing feedback loop.

### 5.4 merge
- **Prompt**: Expects `{query}`, `{plan}`, `{docs}`, `{tools}`.
- **Node**: Passes `plan_str`, `docs_str`, `tools_str` — aligned.
- **Gap**: Merge prompt says "Final Response:" but node strips it — prompt could say "Do not prefix with 'Final Response:'" or keep stripping. Minor.

### 5.5 validate
- **Prompt**: Expects `{response}`, `{sources}`. Output: `valid: true|false` and `reason: <sentence>`.
- **Node**: Passes `response` (draft), `sources`, `query`, `is_retry`. **Check**: Does validate.txt have `{is_retry}` placeholder?
- **Gap**: Regex parsing is brittle — move to structured output. Reason is not passed back to planner.

### 5.6 direct_response
- **Prompt**: Expects `{query}`.
- **Node**: Passes `query` — aligned.

### 5.7 structured
- **Prompt**: Expects `{query}`, `{docs}`.
- **Node**: Passes `query`, `docs_str`. But structured receives `retrieved_docs` — when routed directly, retrieval is skipped, so docs are empty. **Critical gap.**

### 5.8 calculation
- **Prompt**: Expects `{query}`, `{data}`.
- **Node**: Passes `query`, `data` (from tool_outputs + retrieved_docs). Calculation also skips retrieval when routed directly — so it gets empty docs. **Same gap as structured.**

---

## Category 6: Calculation & Structured Path Fixes

### 6.1 Calculation and Structured Need Context
- **Current**: When router sends to `calculation` or `structured`, those nodes read `retrieved_docs` and `tool_outputs`. But retrieval was skipped!
- **Logic**: Either:
  - **Option A**: Always run retrieval before routing (intent → filters → retrieval → router → calculation/structured/merge). Bigger graph change.
  - **Option B**: Router sends calculation/structured to retrieval first, then to their node. So: planner → router → retrieval (for calc/struct) → calc/struct node.
  - **Option C**: Calculation/structured nodes call `hybrid_search` themselves when `retrieved_docs` is empty. Self-sufficient but duplicates retrieval logic.

---

## Category 7: Configuration Centralization

### 7.1 Timeouts
- LLM: 60 (llm_config), Controller: 240 (query_controller), Scrapy: 120 (settings)
- **Logic**: Single `config.py` or `.env` section: `LLM_TIMEOUT`, `QUERY_TIMEOUT`, `DOWNLOAD_TIMEOUT`

### 7.2 Retrieval Params
- `RRF_K`, pool limits, weights — centralize

---

## Category 8: API & Webapp

### 8.1 Streaming Consistency
- Main `/query` streams; webapp `query_controller` uses `ainvoke` with timeout. Different patterns.
- **Logic**: Document or align — e.g. webapp could use streaming for long queries.

### 8.2 Rate Limiting
- Add for production

---

## Recommended Order

1. **Category 1** — Quick wins, unblocks clarity
2. **Category 6** — Fixes broken calculation/structured paths (critical logic bug)
3. **Category 2** — Validation improvements, feedback loop
4. **Category 3** — Conditional tools, routing fixes
5. **Category 4** — Schema alignment
6. **Category 5** — Prompt tweaks (can do alongside 2–4)
7. **Category 7** — Config
8. **Category 8** — API polish

---

## Next Step

Start with **Category 1** when ready. I can implement each category in sequence.
