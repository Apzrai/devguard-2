# DEVGUARD 2.0 — Phase 1 Architecture Plan (Revised)

## Top-Level Overview

DEVGUARD 2.0 is a behavioral safety and verification layer around IBM Bob.
It ingests an existing application, reconstructs its behavioral contract from actual
source code and tests, routes a maintenance request through IBM Bob for execution,
and then verifies — using deterministic code and test runs first, watsonx.ai for
explanation — that Bob's output did not violate the contract. A cryptographically-linked
Proof of Done closes the loop.

**Key constraints locked before implementation:**
- DEVGUARD reads LegacyShop. IBM Bob modifies LegacyShop. These roles must never swap.
- No `ibm-bob` PyPI package is assumed to exist. Bob is behind a swappable executor
  interface; the concrete implementation is chosen at runtime via `.env`.
- Behavioral verification is deterministic first (run the existing test suite against
  Bob's output). watsonx.ai assists with explanation and analysis — it is not the
  sole or primary verification gate.
- The required controlled failure is specific and real: a maintenance request to raise
  the **Enterprise discount from 10% → 15%** that also accidentally changes the
  **Loyalty discount from 10% → 15%**. This must be caught from actual test failures
  and/or code diff analysis, not a hardcoded result.
- Additional failure scenarios (optional, not MVP): out-of-stock bypass, negative cart
  quantities. These are scaffolded but not required for the demo.

This plan covers **architecture only**. No code is written until the plan is approved.
The workspace is a **clean slate** — zero files committed.

---

## Recommended Stack

| Layer | Choice | Rationale |
|---|---|---|
| Runtime | **Python 3.11+** | Fast iteration, no build step, AST stdlib included |
| Web framework | **FastAPI + uvicorn** | Async, auto OpenAPI docs, minimal boilerplate |
| Frontend | **Single HTML + vanilla JS + Tailwind CDN** | Zero build toolchain risk |
| LLM / analysis | **ibm-watsonx-ai SDK** | Confirmed PyPI package; used for behavior map, contract, impact, drift, explanation |
| Bob integration | **Swappable BobExecutor interface** | See Bob Integration section below |
| Verification | **Python subprocess (run pytest)** | Deterministic; test results are ground truth |
| Storage | **JSON files on disk** | No DB setup; human-readable artifacts |
| Provenance | **Python hashlib SHA-256** | Zero extra deps; deterministic proof chain |
| Env config | **python-dotenv** | Standard; no secrets in source |

**No Docker, no database, no message queue.** Everything runs with `uvicorn`.

---

## Bob Integration Strategy

Bob's programmatic API is not confirmed at plan time. The architecture accounts for this
with a three-tier fallback, selected by `BOB_BACKEND` in `.env`:

| Tier | Backend value | When to use |
|---|---|---|
| 1 | `watsonx_agent` | watsonx.ai Agents API is available and Bob can be invoked as an agent |
| 2 | `watsonx_llm` | Only plain LLM access is available; Bob is simulated via a system prompt that describes Bob's persona and constraints |
| 3 | `mock` | No API access; returns a pre-written response from `fixtures/bob_mock_response.json` for demo/offline use |

All three implement the same `BobExecutor` abstract interface:
```
execute(request: str, contract: dict) -> BobResponse
```
where `BobResponse` contains: `intent_summary`, `proposed_diff`, `files_modified`, `raw`.

This means the rest of the pipeline is **completely decoupled from Bob's actual API**.
The executor is the only file that changes when the real Bob API is confirmed.

---

## LegacyShop — The Controlled Failure Scenario

LegacyShop's `discount.py` contains two distinct discount types with similar logic:

```
ENTERPRISE_DISCOUNT = 0.10   # 10% off for enterprise accounts
LOYALTY_DISCOUNT    = 0.10   # 10% off for loyalty program members
```

The maintenance request for the required controlled failure is:
> *"Update the Enterprise discount rate from 10% to 15% to match the new pricing policy."*

Bob (or the mock executor) produces a diff that correctly changes `ENTERPRISE_DISCOUNT`
but also accidentally changes `LOYALTY_DISCOUNT` from `0.10` to `0.15`.

LegacyShop ships with a **pre-written test suite** (`sample_app/tests/`) that includes:
- `test_enterprise_discount` — asserts `apply_discount("enterprise", 100) == 85.0` (after fix: 85.0)
- `test_loyalty_discount` — asserts `apply_discount("loyalty", 100) == 90.0` (this will FAIL after Bob's bad diff)
- `test_discount_independence` — asserts the two rates are independent

When DEVGUARD runs verification, it applies Bob's diff to a **working copy** of
LegacyShop, runs pytest against that copy, and the test failure is the primary
evidence that Bob's change violated the behavioral contract. watsonx.ai then
explains *why* the failure is a contract violation and which clause was breached.

DEVGUARD never modifies the canonical `sample_app/` directory. It operates on a
temporary copy in `artifacts/working_copy/`.

---

## Project Structure

```
devguard/
├── .env.example                        # API keys + BOB_BACKEND selector
├── README.md                           # Quick-start guide
├── requirements.txt                    # Python deps (no ibm-bob)
│
├── sample_app/                         # LegacyShop — read-only subject application
│   ├── __init__.py
│   ├── catalog.py                      # Product listing, search, filter
│   ├── cart.py                         # Add/remove/total logic
│   ├── checkout.py                     # Order placement, stock validation
│   ├── discount.py                     # ENTERPRISE_DISCOUNT + LOYALTY_DISCOUNT logic
│   └── tests/
│       ├── test_catalog.py
│       ├── test_cart.py
│       ├── test_checkout.py
│       └── test_discount.py            # Includes the loyalty/enterprise independence test
│
├── fixtures/
│   └── bob_mock_response.json          # Pre-written mock Bob response (the bad diff)
│
├── devguard/
│   ├── __init__.py
│   ├── understand.py                   # Step 1 — AST-based project understanding
│   ├── behavior_map.py                 # Step 2 — watsonx.ai behavior extraction
│   ├── evidence.py                     # Step 3 — SHA-256 provenance of source + tests
│   ├── contract.py                     # Step 4 — watsonx.ai behavioral contract
│   ├── impact.py                       # Step 5 — watsonx.ai impact analysis
│   ├── bob_executor.py                 # Step 6 — BobExecutor interface + 3 implementations
│   ├── drift_detector.py               # Step 7 — watsonx.ai intent drift scoring
│   ├── verifier.py                     # Step 8 — pytest runner + watsonx.ai explanation
│   └── proof.py                        # Step 9 — SHA-256 hash chain → Proof of Done
│
├── api/
│   ├── __init__.py
│   └── main.py                         # FastAPI — one endpoint per step
│
├── artifacts/                          # Runtime outputs (git-ignored)
│   ├── .gitkeep
│   └── working_copy/                   # Temp copy of sample_app for Bob to modify
│
└── ui/
    └── index.html                      # Single-file dashboard
```

---

## Core Workflow — Data Flow

```
sample_app/ (read-only)
        │
        ▼
[ UNDERSTAND ]       understand.py
        │            Python AST → module list, function names, entry points
        │            Output: artifacts/understanding.json
        ▼
[ BEHAVIOR MAP ]     behavior_map.py
        │            watsonx.ai → named behaviors with descriptions
        │            Output: artifacts/behavior_map.json
        ▼
[ EVIDENCE ]         evidence.py
        │            SHA-256 of every source file + test file → provenance baseline
        │            Output: artifacts/evidence.json
        ▼
[ CONTRACT ]         contract.py
        │            watsonx.ai → invariants + clauses per behavior
        │            Output: artifacts/contract.json
        ▼
[ IMPACT ]           impact.py
        │            Maintenance request + contract → watsonx.ai risk assessment
        │            Output: artifacts/impact.json
        ▼
[ BOB EXECUTION ]    bob_executor.py
        │            BobExecutor.execute(request, contract) → proposed diff
        │            Bob writes the diff to artifacts/working_copy/
        │            Output: artifacts/bob_response.json
        ▼
[ INTENT DRIFT ]     drift_detector.py
        │            Original request vs Bob intent summary → watsonx.ai drift score
        │            Output: artifacts/drift.json
        ▼
[ VERIFY ]           verifier.py
        │            1. Apply diff to artifacts/working_copy/
        │            2. Run pytest on working_copy → PASS / FAIL (deterministic)
        │            3. watsonx.ai explains which clause was violated and why
        │            Output: artifacts/verification.json
        ▼
[ PROOF OF DONE ]    proof.py
                     Hash chain: evidence → contract → bob_response → drift → verification
                     Output: artifacts/proof_of_done.json
                             artifacts/proof_of_done.md
```

**DEVGUARD never touches `sample_app/` after the initial read.**
All mutation happens in `artifacts/working_copy/` only.

---

## Behavioral Verification — Detail

Verification is **deterministic first, LLM second**:

| Stage | Method | Outputs |
|---|---|---|
| 1. Apply diff | `patch` stdlib or line-by-line apply | Modified files in `working_copy/` |
| 2. Run tests | `subprocess` → `pytest working_copy/tests/ --json-report` | Test results JSON |
| 3. Parse failures | Pure Python — read pytest JSON output | List of failing test IDs + error messages |
| 4. Clause mapping | Match failing tests to contract clause IDs (by behavior_ref) | Violated clauses list |
| 5. LLM explanation | watsonx.ai: "Given this test failure and this contract clause, explain the violation" | Human-readable explanation per violation |

The overall verdict (`PASS` / `FAIL`) comes from step 3, not the LLM.
watsonx.ai only provides the explanation in step 5. This means verification works
even if the LLM is unavailable — it just won't have the natural-language explanation.

---

## Sub-Tasks

### Task 1 — Repository Scaffold
**Intent:** Establish the project skeleton so every subsequent task has a home.
**Expected Outcomes:** All directories exist, `requirements.txt` is present with confirmed deps, `.env.example` covers all required keys including `BOB_BACKEND`, `README.md` explains setup.
**Todo List:**
- [ ] Create directories: `sample_app/tests/`, `devguard/`, `api/`, `artifacts/working_copy/`, `fixtures/`, `ui/`
- [ ] Create `requirements.txt` (no `ibm-bob` — see dependencies section)
- [ ] Create `.env.example`
- [ ] Create `README.md`
- [ ] Create `__init__.py` stubs
**Status:** [ ] pending

---

### Task 2 — LegacyShop Sample Application
**Intent:** Build the subject application with enough behavioral depth to make the contract meaningful. The discount module must have two similar-but-independent discount rates so the controlled failure is realistic.
**Expected Outcomes:** `sample_app/` runs standalone. `discount.py` has `ENTERPRISE_DISCOUNT = 0.10` and `LOYALTY_DISCOUNT = 0.10` as separate constants. Tests in `tests/test_discount.py` assert their independence.
**Todo List:**
- [ ] Implement `catalog.py` — product list, search, filter by category
- [ ] Implement `cart.py` — add item, remove item, calculate total
- [ ] Implement `checkout.py` — place order, validate stock, generate order ID
- [ ] Implement `discount.py` — `ENTERPRISE_DISCOUNT`, `LOYALTY_DISCOUNT`, `apply_discount(type, amount)`
- [ ] Write `tests/test_catalog.py`, `test_cart.py`, `test_checkout.py`
- [ ] Write `tests/test_discount.py` — must include `test_loyalty_discount`, `test_enterprise_discount`, `test_discount_independence`
- [ ] Confirm all tests pass on the clean codebase
- [ ] Add `__main__.py` for standalone demo
**Relevant Context:** DEVGUARD reads this directory. IBM Bob writes to `artifacts/working_copy/` (a copy). The canonical `sample_app/` is never modified.
**Status:** [ ] pending

---

### Task 3 — Bob Mock Fixture
**Intent:** Create the pre-written mock Bob response that contains the intentional bug — Enterprise discount correctly raised to 15%, Loyalty discount accidentally also raised to 15%. This is the fixture used when `BOB_BACKEND=mock`.
**Expected Outcomes:** `fixtures/bob_mock_response.json` contains a valid `BobResponse`-shaped payload with a diff that modifies both `ENTERPRISE_DISCOUNT` and `LOYALTY_DISCOUNT` to `0.15`.
**Todo List:**
- [ ] Write the bad unified diff that changes both discount constants
- [ ] Wrap it in the `BobResponse` JSON schema: `intent_summary`, `proposed_diff`, `files_modified`, `raw`
**Relevant Context:** This fixture is what makes the demo reliable and repeatable without a live Bob API. The drift detector should see the intent as aligned (Bob did what was asked superficially) while the verifier catches the test failure.
**Status:** [ ] pending

---

### Task 4 — Project Understanding Module
**Intent:** Implement the UNDERSTAND step using Python AST — no LLM required.
**Expected Outcomes:** `understand.py` produces `artifacts/understanding.json` with module names, file paths, line counts, and top-level function/class names for every file in `sample_app/`.
**Todo List:**
- [ ] Walk `sample_app/` (excluding `tests/`), collect file metadata
- [ ] Use `ast.parse` to extract function and class names per file
- [ ] Walk `sample_app/tests/` separately and record test function names
- [ ] Write `artifacts/understanding.json`
**Status:** [ ] pending

---

### Task 5 — Behavior Map
**Intent:** Use watsonx.ai to convert the source code and understanding artifact into a structured list of named behaviors.
**Expected Outcomes:** `artifacts/behavior_map.json` — list of behavior objects with `id`, `name`, `module`, `description`, `inputs`, `outputs`. Discount behaviors must be listed as separate entries for enterprise and loyalty.
**Todo List:**
- [ ] Build prompt from source file contents + understanding artifact
- [ ] Call watsonx.ai; instruct it to respond in strict JSON
- [ ] Add retry + JSON repair loop for malformed responses
- [ ] Validate response against Pydantic schema
- [ ] Write `artifacts/behavior_map.json`
**Status:** [ ] pending

---

### Task 6 — Evidence and Provenance
**Intent:** Hash the canonical source files and tests before any Bob execution, establishing an immutable baseline.
**Expected Outcomes:** `artifacts/evidence.json` with SHA-256 hash per file, aggregate hash, and ISO timestamp.
**Todo List:**
- [ ] Hash each file in `sample_app/` (source + tests)
- [ ] Compute aggregate hash of all individual hashes
- [ ] Record timestamp
- [ ] Write `artifacts/evidence.json`
**Status:** [ ] pending

---

### Task 7 — Behavioral Contract
**Intent:** Use watsonx.ai to derive formal invariants from the behavior map — the rules that must hold regardless of future changes.
**Expected Outcomes:** `artifacts/contract.json` — list of clauses with `id`, `behavior_ref`, `invariant`, `must_not`, `severity` (critical/high/low). Must include a clause like: *"Enterprise and Loyalty discount rates are independent; changing one must not affect the other."*
**Todo List:**
- [ ] Build prompt from behavior map
- [ ] Instruct watsonx.ai to produce contract clauses in strict JSON
- [ ] Add retry + JSON repair loop
- [ ] Validate against Pydantic schema
- [ ] Write `artifacts/contract.json`
**Relevant Context:** The contract clause about discount independence is what the verifier will reference when the test fails. The clause should map to the `test_discount_independence` test.
**Status:** [ ] pending

---

### Task 8 — Impact Analysis
**Intent:** Before Bob runs, predict which behaviors and contract clauses are at risk from the maintenance request.
**Expected Outcomes:** `artifacts/impact.json` — ranked list of at-risk behaviors and clauses, with reasoning. For the Enterprise discount request, the Loyalty discount clause should appear as a risk (low/medium), demonstrating DEVGUARD predicted the danger before Bob ran.
**Todo List:**
- [ ] Accept maintenance request as input
- [ ] Build prompt from request + contract + behavior map
- [ ] Call watsonx.ai to rank risk
- [ ] Write `artifacts/impact.json`
**Status:** [ ] pending

---

### Task 9 — Bob Executor
**Intent:** Implement the `BobExecutor` abstract interface and all three concrete backends. The interface is the permanent contract; backends are swappable.
**Expected Outcomes:** `bob_executor.py` exports `BobExecutor` (ABC), `WatsonxAgentExecutor`, `WatsonxLLMExecutor`, `MockBobExecutor`. Factory function `get_executor()` reads `BOB_BACKEND` from env and returns the correct instance. `artifacts/bob_response.json` is written after execution. `artifacts/working_copy/` is populated with the modified files.
**Todo List:**
- [ ] Define `BobResponse` Pydantic model: `intent_summary`, `proposed_diff`, `files_modified`, `raw`
- [ ] Define `BobExecutor` ABC with `execute(request, contract) -> BobResponse`
- [ ] Implement `MockBobExecutor` — reads `fixtures/bob_mock_response.json`, applies diff to `working_copy/`
- [ ] Implement `WatsonxLLMExecutor` — uses watsonx.ai with a Bob-persona system prompt; parses response into `BobResponse`
- [ ] Implement `WatsonxAgentExecutor` — stub only, marked `NotImplemented` until Bob Agents API is confirmed
- [ ] Implement `get_executor()` factory
- [ ] Write `artifacts/bob_response.json`
- [ ] Copy `sample_app/` to `artifacts/working_copy/`, apply `proposed_diff`
**Relevant Context:** `MockBobExecutor` is the reliable path for the hackathon demo. `WatsonxLLMExecutor` is the live path if credentials are available. `WatsonxAgentExecutor` is future-ready.
**Status:** [ ] pending

---

### Task 10 — Intent Drift Detection
**Intent:** Detect if Bob's stated intent drifted from the original maintenance request. For the controlled failure scenario, Bob's intent will appear aligned (it says it updated Enterprise pricing) — drift detection should score LOW drift, which is intentionally correct. This demonstrates that drift alone is not sufficient — verification is also needed.
**Expected Outcomes:** `artifacts/drift.json` — `drift_score` (0.0–1.0), `verdict` (ALIGNED/DRIFTED), `reasoning`.
**Todo List:**
- [ ] Extract `intent_summary` from `bob_response.json`
- [ ] Build prompt: original request vs Bob's intent summary
- [ ] Call watsonx.ai to score semantic alignment
- [ ] Write `artifacts/drift.json`
**Relevant Context:** For the controlled failure, drift will show ALIGNED. The verifier will catch the real problem. This is a deliberate design point — it shows why verification must be independent of intent.
**Status:** [ ] pending

---

### Task 11 — Behavioral Verification
**Intent:** Run the LegacyShop test suite against Bob's modified working copy. Parse failures. Map failures to contract clauses. Use watsonx.ai only for explanation, not verdict.
**Expected Outcomes:** `artifacts/verification.json` — `verdict` (PASS/FAIL), `test_results` (from pytest), `violated_clauses` (list of contract clause IDs), `explanation` (watsonx.ai narrative per violation).
**Todo List:**
- [ ] Confirm `artifacts/working_copy/` has the patched files from Bob executor
- [ ] Run `pytest sample_app/tests/` against the working copy via `subprocess` with `--json-report`
- [ ] Parse pytest JSON output: collect failing test IDs and error messages
- [ ] Map each failing test to its `behavior_ref` in the contract → find violated clause IDs
- [ ] If any failures: verdict = FAIL; call watsonx.ai to explain each violated clause in plain language
- [ ] If no failures: verdict = PASS; skip LLM call
- [ ] Write `artifacts/verification.json`
**Relevant Context:** For the controlled failure, `test_loyalty_discount` and `test_discount_independence` will fail. These map to the discount independence clause in the contract. Verdict = FAIL without any LLM involvement.
**Status:** [ ] pending

---

### Task 12 — Proof of Done
**Intent:** Chain all artifact hashes into a single tamper-evident Proof of Done.
**Expected Outcomes:** `artifacts/proof_of_done.json` — hash chain, final verdict, step-by-step summary. `artifacts/proof_of_done.md` — human-readable report for judges.
**Todo List:**
- [ ] Load all prior artifacts in pipeline order
- [ ] Compute hash chain: each step hashes `(previous_chain_hash + current_artifact_content)`
- [ ] Extract final verdict from `verification.json`
- [ ] Write `artifacts/proof_of_done.json`
- [ ] Write `artifacts/proof_of_done.md` with a readable summary of each step and outcome
**Status:** [ ] pending

---

### Task 13 — FastAPI Endpoints
**Intent:** Expose every pipeline step as an HTTP endpoint so the frontend and judges can trigger and inspect each step independently.
**Expected Outcomes:** `uvicorn api.main:app` serves all endpoints. Steps run in order; each writes its artifact; artifacts are readable via GET.
**Todo List:**
- [ ] `POST /run/understand`
- [ ] `POST /run/behavior-map`
- [ ] `POST /run/evidence`
- [ ] `POST /run/contract`
- [ ] `POST /run/impact` — body: `{ "request": "..." }`
- [ ] `POST /run/bob` — body: `{ "request": "...", "scenario": "happy|failure_a" }`
- [ ] `POST /run/drift`
- [ ] `POST /run/verify`
- [ ] `POST /run/proof`
- [ ] `GET /artifacts/{name}` — return any artifact by filename
- [ ] `POST /run/full` — runs entire pipeline end-to-end with a single request body
- [ ] `GET /health` — returns Bob backend in use + watsonx.ai connectivity status
**Status:** [ ] pending

---

### Task 14 — Frontend Dashboard
**Intent:** Single HTML file. Shows the full pipeline as a visual flow. Lets a judge run the demo end-to-end without a terminal.
**Expected Outcomes:** `ui/index.html` — pipeline step indicators (pending / running / pass / fail), maintenance request input, scenario toggle (Happy Path vs Controlled Failure), per-step artifact display, Proof of Done panel.
**Todo List:**
- [ ] Pipeline status strip: 9 steps with color-coded status badges
- [ ] Maintenance request input field (pre-filled with Enterprise 10%→15% request)
- [ ] Scenario toggle: Happy Path / Controlled Failure (pre-fills different request text and sets mock mode)
- [ ] "Run Full Pipeline" button — calls `POST /run/full`, polls for completion
- [ ] Per-step collapsible panel showing raw artifact JSON
- [ ] Proof of Done panel: hash chain display + final PASS/FAIL banner
- [ ] No JS framework — vanilla fetch + DOM manipulation only
**Status:** [ ] pending

---

## Implementation Order

```
1  → Task 1   (scaffold — foundation for everything)
2  → Task 2   (LegacyShop + tests — required input; tests define ground truth)
3  → Task 3   (mock Bob fixture — enables offline development immediately)
4  → Task 4   (understand — no LLM, validates AST approach)
5  → Task 6   (evidence — hash baseline before any LLM work)
6  → Task 5   (behavior map — first LLM step)
7  → Task 7   (contract — depends on behavior map)
8  → Task 8   (impact — depends on contract)
9  → Task 9   (Bob executor — mock path first, then LLM path)
10 → Task 10  (drift — depends on Bob response)
11 → Task 11  (verification — depends on Bob working copy + contract)
12 → Task 12  (proof of done — depends on all prior artifacts)
13 → Task 13  (FastAPI — wraps all modules)
14 → Task 14  (frontend — wraps the API)
```

---

## Dependencies Required

```
# requirements.txt
fastapi
uvicorn[standard]
python-dotenv
ibm-watsonx-ai          # Confirmed PyPI package — analysis steps
pydantic                # Schema validation
pytest                  # Test runner for behavioral verification
pytest-json-report      # Machine-readable pytest output
httpx                   # Async HTTP
```

**Not included and not assumed:**
- `ibm-bob` — no such package is installed until the real SDK name is confirmed
- Any diff/patch library — Python stdlib `difflib` and `pathlib` are sufficient

**External accounts required:**
- IBM Cloud account with watsonx.ai access (project ID + API key)
- `BOB_BACKEND` set to `mock` works with zero external dependencies

---

## Risks That Could Waste Time

| Risk | Severity | Mitigation |
|---|---|---|
| Bob API/SDK does not exist as a Python package | 🔴 HIGH | Entire Bob path is behind `BobExecutor` interface; `MockBobExecutor` is always available; demo runs fully offline |
| watsonx.ai auth or rate limit failure during demo | 🔴 HIGH | All LLM outputs cached as JSON artifacts; re-run replays from cache unless `--force` flag used |
| LLM returns malformed JSON | 🔴 HIGH | JSON-mode prompting + retry loop + Pydantic validation with fallback repair |
| pytest JSON report format changes across versions | 🟡 MEDIUM | Pin `pytest` and `pytest-json-report` versions in requirements.txt |
| Diff apply fails on working copy | 🟡 MEDIUM | Use unified diff format consistently; validate that diff applies cleanly before running tests |
| Contract clause IDs don't map cleanly to test names | 🟡 MEDIUM | Explicit mapping table in contract: `behavior_ref` matches a test function name prefix |
| Pipeline too slow for live demo | 🟡 MEDIUM | Pre-run and cache all analysis steps (understand → contract); only Bob + verify run live |
| Frontend status polling adds complexity | 🟡 LOW | Use synchronous `POST /run/full` with a short timeout; show spinner while waiting |
