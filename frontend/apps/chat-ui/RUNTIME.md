# Agent Chat runtime (assistant-ui ↔ LangGraph)

`apps/chat-ui` is a React + Vite application that owns the full conversational Agent UX. It talks to the backend LangGraph dev server (`backend/langgraph.json` → `agent` graph on `:2025`) through the official `@assistant-ui/react-langgraph` runtime.

## Frozen architecture (post-P0)

```text
React 19 + Vite 6
       │
       ▼
@assistant-ui/react                ← Thread / Composer / message primitives
       │
       ▼
@assistant-ui/react-langgraph      ← useLangGraphRuntime + stream helper
       │
       ▼
@langchain/langgraph-sdk           ← Client (threads / runs / state)
       │
       ▼
LangGraph dev server `:2025`        ← `agent` graph
       │
       ▼
backend/app/workflows/agent_chat   ← graph.py
```

This stack is **frozen** at P0 acceptance. Do not introduce `react-langchain` or any other runtime — both runtimes overlap in capability, and switching creates a migration tax without a product reason.

## TL;DR

| Layer | What | Where |
| --- | --- | --- |
| LangGraph server | `agent` graph with `messages: Annotated[list[AnyMessage], add_messages]` state | `backend/app/workflows/agent_chat/graph.py`, served by `backend/scripts/run_agent_langgraph.ps1` on `:2025` |
| Wire protocol | LangGraph SDK REST/SSE | `@langchain/langgraph-sdk` `Client` |
| UI runtime | `useLangGraphRuntime` | `src/App.tsx` |
| Stream helper | `unstable_createLangGraphStream({ client, assistantId })` | `src/App.tsx` |
| Thread list adapter | `RemoteThreadListAdapter` → `client.threads.*` | `src/runtime/langgraph.ts` |
| Cancellation | `unstable_allowCancellation: true` (Stop button aborts the LangGraph run) | `src/App.tsx` |
| Workbench handoff | URL query params (`cc_source`, `cc_resource`, `cc_prompt`) | `src/lib/launch-context.ts` |

## Seams (do not blur)

The chat-ui app is intentionally thin. Each seam has exactly one owner:

```text
RemoteThreadListAdapter (UI-initiated thread list actions)
└── list / initialize / fetch / rename / delete / generateTitle
       │
       ▼
client.threads.*        (LangGraph thread metadata)


useLangGraphRuntime.load  (per-thread messages + interrupts)
└── load(externalId) → { messages, interrupts }
       │
       ▼
client.threads.getState(externalId)


unstable_createLangGraphStream
└── stream(messages, { initialize, config, signal })
       │
       ▼
client.runs.stream (handled by the helper, opaque to us)
```

`create` and `delete` are **not** wired on the runtime; the thread list adapter's `initialize` covers new-thread creation, and the runtime accepts cancellation through the `unstable_allowCancellation` path. See https://www.assistant-ui.com/docs/runtimes/langgraph/threads.

## URL contract (locked)

| Surface | URL |
| --- | --- |
| Dev — Workbench | `http://127.0.0.1:3000/` |
| Dev — Chat | `http://127.0.0.1:3001/chat/` |
| Dev — FastAPI | `http://127.0.0.1:8000/` |
| Dev — LangGraph | `http://127.0.0.1:2025/` |
| Prod | one origin; `/` → workbench, `/chat/**` → this build, `/api/**` → FastAPI |

The Vite `base: '/chat/'` setting is the single source of truth. The Workbench `VITE_CHAT_UI_URL` defaults to `http://127.0.0.1:3001/chat/` (trailing slash required). Reverse proxies / CDNs MUST serve this build with a SPA fallback so that deep links and refreshes inside `/chat/**` resolve.

## Environment variables

Vite exposes everything matching `VITE_*` to the browser. The chat-ui app uses **two** Vite env vars and **nothing else**:

| Variable | Public? | Purpose |
| --- | --- | --- |
| `VITE_LANGGRAPH_API_URL` | yes (URL only) | LangGraph server URL. Baked into the bundle. |
| `VITE_LANGGRAPH_ASSISTANT_ID` | yes (id only) | Graph id, usually `agent`. |

Long-lived secrets — LangSmith / LangGraph API keys, OpenAI keys, internal tokens — **MUST NOT** be prefixed `VITE_`. They must travel server-to-server:

```text
Browser (Vite-baked URL only)
    ↓
Workbench / chat-ui (no secrets)
    ↓
FastAPI / BFF (carries the key in the Authorization header, never in HTML/JS)
    ↓
LangGraph / OpenAI / ...
```

If a LangGraph auth scheme is added in the future, the chat-ui runtime will accept a `LANGSMITH_API_KEY` passed in the `Authorization` header from a BFF route, not via `import.meta.env`.

## Launch context from the Workbench

The Workbench opens `http://127.0.0.1:3001/chat/?cc_source=<src>&cc_resource=<id>&cc_prompt=<text>`. `src/lib/launch-context.ts` parses and validates the params:

- `cc_source`: `'knowledge' | 'metrics' | 'reports' | 'research'`
- `cc_resource`: opaque business id (doc id, company id, draft id, …)
- `cc_prompt`: short pre-filled user prompt

Invalid / missing context silently degrades to a free-form chat. Document text, secrets, or trace ids must NEVER travel in this URL.

## First-round scope

- Thread list (new / switch / rename / delete) backed by `client.threads.*`.
- Thread view with message rendering and streaming text.
- Composer with text input + attachment placeholder (UI only).
- Launch context banner.
- Markdown rendering for assistant messages.
- `unstable_allowCancellation: true` wired; server-side abort behaviour is unverified until Acceptance #15 passes.

## Chat-ui acceptance suite (15 items)

`pnpm install && pnpm dev:chat` from `frontend/` boots the dev server at `http://127.0.0.1:3001/chat/`. The following fifteen items MUST pass before any Tool UI / Generative UI work begins. Items 13–15 were added after the architecture freeze.

| # | Item | How |
| --- | --- | --- |
| 1 | `pnpm build` succeeds | `pnpm build` from `frontend/` |
| 2 | TypeScript clean | `pnpm typecheck` from `frontend/` |
| 3 | `/chat/` loads in browser | open `http://127.0.0.1:3001/chat/` |
| 4 | Workbench handoff keeps `cc_*` params | click Agent Chat from `http://127.0.0.1:3000/knowledge`, verify URL has params |
| 5 | New thread is created | click "新对话", confirm thread id in `client.threads.search` |
| 6 | Thread list loads | left panel shows LangGraph threads from `:2025` |
| 7 | Thread switch persists messages | create A, send 3 messages, switch to B, switch back — messages intact |
| 8 | Refresh persists messages | F5 on /chat/ keeps both thread A and thread B messages |
| 9 | Streaming tokens flow | send a question, observe incremental deltas |
| 10 | Cancel aborts the request | stop a run mid-stream, verify no more deltas |
| 11 | LangGraph error surfaces UI error | kill `:2025`, send a question — runtime shows a finite error, not infinite spinner |
| 12 | LangGraph unavailable does not block thread load | with `:2025` down, list + open existing thread still works from local state |
| 13 | **Thread isolation** | A → B → A: messages / interrupts / loading / tool state do NOT leak across threads |
| 14 | **Hard refresh with launch context** | open `/chat/?cc_source=research&cc_resource=<doc_id>&cc_prompt=…`, F5 — thread + banner come back, prompt is not re-fired |
| 15 | **End-to-end cancellation** | click Stop mid-stream — UI stops, LangGraph run is genuinely cancelled (`client.runs` shows no continued events), and the next message still streams normally |

## P0 acceptance run log

### Run 1 — 2026-09-16, Windows dev box (Node v24.19.0, pnpm 10.18.3, Chromium headless 147)

Static gates and everything that does **not** require the LangGraph server were executed. Items needing `:2025` could not run here — see "Environment blocker".

| # | Result | Evidence |
| --- | --- | --- |
| 1 | PASS | `pnpm --filter @claude-copilot/chat-ui build` → `built in 16.58s`; workbench build green. |
| 2 | PASS | `tsc -b --noEmit` clean for `contracts`, `workbench`, `chat-ui`. |
| 3 | PASS | `GET /chat/` → 200 with base-prefixed assets; app mounts (rail `AGENT CHAT / Claude Copilot`, `新对话`, composer, empty state); `pageerror` count **0**. |
| 4 | **FAIL** | Clicking "Agent Chat" from `/knowledge` lands on `http://127.0.0.1:3001/chat/` but carries **no** `cc_source` / `cc_resource` / `cc_prompt`. |
| 5–10 | BLOCKED | Require `:2025`. |
| 11 | **FAIL** (cold start) | With `:2025` never up, sending a message never terminates and surfaces no error. The mid-session variant is untested. Detail below. |
| 12 | BLOCKED | Needs a populated `:2025` list to open an existing thread. |
| 13 | BLOCKED | Requires `:2025`. |
| 14 | PARTIAL | `cc_*` params survive F5 and the banner re-renders; nothing is auto-sent (observed only `POST /threads/search`, never `runs/stream`). The "thread comes back" half needs `:2025`. |
| 15 | BLOCKED | Requires `:2025`. |

Lint: `eslint .` → 0 errors, 1 warning (`react-refresh/only-export-components` in `LaunchContextBanner.tsx`, benign).

#### Failure detail — #11: non-terminal run, zero user feedback

Two variants of "#11 with `:2025` down" exist, and they are **not** equivalent:

- **Cold start** — `:2025` was never up, so the page has no initialised thread. Send then fails at *thread creation* (`POST /threads`). **This is the variant that was actually run, and it fails** (detail below).
- **Mid-session** — `:2025` was up, a thread exists, then it dies. Send fails inside `runs.stream` instead. **Untested** (needs a working `:2025`); the failure flows through a different code path that does call `setRunning(false)` on rejection (`serialRunQueue.js`), so it may well behave correctly.

Observed behaviour, cold start, sending one message:

- the run **never resolves**: the Stop button is still present at t=35 s (sampled every 5 s), i.e. `thread.isRunning` stays `true` indefinitely;
- **no error is surfaced**: no sonner toast (`[data-sonner-toaster]` empty), no inline error, the only `aria-live` region is empty;
- the user's message **stays with no assistant reply**, and the optimistic `未命名会话` row is **silently rolled back** from the rail (gone by t=40 s) once `POST /threads` fails;
- `pageerror` count is 0 — nothing throws, so nothing reaches an error boundary either.

Failed requests observed: `POST /threads/search`, `POST /threads`.

Root cause: the rejection from `RemoteThreadListAdapter.initialize()` (our `langGraphThreadListAdapter.create` → `client.threads.create`) is not routed through the run queue's rejection path, so `isRunning` is never cleared and no `AssistantError` reaches any UI channel. The error model itself exists — `@assistant-ui/core` exports `AssistantError` / `toAssistantError` / `ErrorDisplay` (`"inline" | "toast" | "silent" | "dev-only"`) — but nothing in this app subscribes to it, and `ChatToaster` (`sonner`) is mounted while never being called. `useLangGraphRuntime` exposes **no** `onError` option, so there is no supported seam to intercept this today.

This is precisely the "infinite spinner instead of a finite error" that #11 forbids. Because #11 is a hard gate, it blocks Tool UI / Generative UI work until resolved.

> ⚠️ `e2e/p0-resilience.spec.ts` claims to cover #11/#12 but **cannot fail**: its assertion is `expect(bodyText.length).toBeGreaterThan(0)`, which holds even in the broken state above. Do not treat a green `p0-resilience.spec.ts` as evidence that #11 passes.

#### Failure detail — #4: launch context is never produced

`buildAgentChatUrl(baseUrl, context?)` supports `cc_*`, but its only caller passes no context:

```ts
// apps/workbench/src/layout/AppLayout.vue
function openAgentChat() {
  window.location.assign(buildAgentChatUrl(chatUiUrl))   // ← no second argument
}
```

So no `cc_*` param is ever emitted and the chat-ui banner never renders from a real handoff. Deciding *what* context each workbench view should hand off (which resource id, which prompt) is a product decision, not a runtime fix.

A second, environment-level factor: `VITE_CHAT_UI_URL` has **no fallback in `vite.config.ts`**; `AppLayout.vue` falls back to the relative `'/chat'`, which resolves against the workbench's own origin and navigates to `http://127.0.0.1:3000/chat` (dead — there is no `/chat` proxy, by design). Copying `apps/workbench/.env.example` → `.env` (gitignored) fixes the destination; verified: handoff then lands on `http://127.0.0.1:3001/chat/`. Note that chat-ui does bake its dev defaults into `vite.config.ts`, so the two apps are inconsistent here.

#### Environment blocker for `:2025`

`backend/scripts/run_agent_langgraph.ps1` requires `uv` to create `.venv-langgraph` and install the backend package plus `langgraph-cli[inmem]`, and `backend/langgraph.env` must supply real LLM credentials (`SILICON_KEY` / LLM settings). In this environment: `uv`, `uvx`, `docker` and the `langgraph` CLI are all **missing**, no Python deps are installed (`langgraph`, `fastapi`, `langchain_core`, `langchain_openai` all absent), and there is no `.venv-langgraph`. Items 5–10, 12, 13, 15 and the thread-restore half of #14 therefore remain **unexecuted**, not passed.

#### Defects fixed during Run 1

- **Design tokens were silently dropped.** `src/index.css` had `@import "@claude-copilot/design-tokens/tokens.css"` *after* the `@tailwind` at-rules, which is invalid CSS and emitted `@import must precede all other statements`; the tokens never reached the bundle (0 definitions of `--cc-brand-primary` / `--cc-bg-page` / `--cc-radius-md` in the built CSS). Moving the `@import` to the top of the file removed the warning and the tokens now appear (1 definition each). Note `postcss.config.mjs` has no `postcss-import`, so this ordering is load-bearing — the workbench sidesteps it by importing tokens from JS in `main.ts`. Also note `--cc-font-sans`, referenced in `index.css`, is defined **nowhere** in the repo, so that `font-family` always falls back.
- **Dependency baseline re-pinned.** See §Versioning.

## Versioning — compatibility set, NOT upstream latest

> **Architecture Frozen. No further framework/runtime changes before P0 acceptance.**

The `0.13.x` baseline stated in earlier revisions of this document **never existed on npm**: `@assistant-ui/react` and `@assistant-ui/react-markdown` have no `0.13.x` release at all (they jump `0.12.x → 0.14.0`), and `@assistant-ui/react-langgraph` is the only package of the three with a `0.13.x` line. That made "0.13.x" a **false baseline** — it could not be installed, so the first `pnpm install` failed on `ERR_PNPM_NO_MATCHING_VERSION`.

The real policy is **compatibility-set based, not minor-version based**. The three `@assistant-ui/*` packages do not share a minor version; what matters is that each is in the minor line the others declare as a peer range.

**Current baseline (pinned, post-migration):**

| Package | Pinned | Note |
| --- | --- | --- |
| `@assistant-ui/react` | `0.15.20` | peer target of `react-markdown` (`^0.15.0`) |
| `@assistant-ui/react-langgraph` | `0.14.28` | requires `@langchain/langgraph-sdk ^1.9.20` |
| `@assistant-ui/react-markdown` | `0.14.15` | peer of `react` (`^0.15.0`) |
| `@langchain/langgraph-sdk` | `1.11.0` | bumped from `^0.0.50` for the `react-langgraph` peer range |
| `@langchain/core` | `1.2.11` | peer of `langgraph-sdk` (`^1.1.48`) |
| `assistant-stream` | `0.3.43` | used by `generateTitle` (`createAssistantStream`) |
| `assistant-cloud` | `0.2.1` | forced via root `pnpm.overrides`; see below |

These exact versions are **pinned in `package.json`** (no `^`), so a frozen-lockfile install is deterministic.

> The window in which this set was unfrozen is closed. Do NOT bump `@assistant-ui/*` / `@langchain/*` outside an explicit upgrade task; the 15-item acceptance suite below is the gate.

### Why this is not an architecture change

The frozen stack — React 19 + Vite + `@assistant-ui/react` + `@assistant-ui/react-langgraph` + `@langchain/langgraph-sdk` + LangGraph `:2025` — is unchanged. The migration only un-pinned the *minor lines* to the nearest installable compatibility set, then re-pinned. No Next.js, no `agent-chat-ui`, no hand-rolled SSE parser, no custom `ChatModelAdapter`, and no hand-written event translation were introduced. `react-langchain` appears in the tree **only as a transitive dependency of `react-langgraph` 0.14.28**; it is still not a runtime we select directly.

### `assistant-cloud` override

`@assistant-ui/react-langgraph` declares `assistant-cloud: "*"`, which resolved to `0.1.43`, while `@assistant-ui/core@0.3.19` imports the `assistant-cloud/ai-sdk` subpath that only exists in `0.2.1`+. Without the override the build fails with `Missing "./ai-sdk" specifier in "assistant-cloud" package`. The root `frontend/package.json` therefore pins `pnpm.overrides.assistant-cloud` to `0.2.1`. Remove the override only when every `@assistant-ui/*` package agrees on a range that includes the `ai-sdk` subpath.

### Lockfile policy

After the first successful install, the workflow is:

1. Replace every bootstrap `^` range in the compatibility set with the **exact** resolved version in `package.json`.
2. Commit `package.json` + `pnpm-lock.yaml` together as a single atomic change.
3. CI calls `pnpm install --frozen-lockfile` directly (not `pnpm run install:frozen`). The `install:frozen` script stays in `package.json` as a developer shortcut but CI / automation must use the raw command so it cannot be removed by an accidental `scripts:` edit.

Helper script:

```bash
pnpm install              # first install (bootstrap); resolves the caret ranges
pnpm install:frozen       # developer shortcut for `pnpm install --frozen-lockfile`
```

Any `@assistant-ui/*` bump requires a full 15-item re-run of the suite below.

## Cancellation disclaimer

`unstable_allowCancellation: true` enables the runtime path that propagates Stop clicks to the LangGraph SDK. **Whether the server-side run is actually aborted depends on the LangGraph deployment.** Until Acceptance #15 passes, treat the wiring as "enabled, not yet proven".

## Next rounds (gated by the 15-item suite)

| Priority | Item | Notes |
| --- | --- | --- |
| P1 | Financial Tool UI — `search_financial_report` | First Tool UI; covers "工具执行 → 找到财报 → 片段 → Citation → PDF 页码" end-to-end. Becomes the template for `extract_metrics`, `compare_financials`, etc. |
| P1 | Citation panel | Map LangGraph `metadata` events to inline `[C#]` references; link back to source PDF. |
| P2 | HITL | Surface LangGraph `interrupt` events as approval cards. |
| P2 | Generative UI | Inline financial tables / charts in message body. |
| P3 | Attachments | Wire `attachments` adapter to backend file uploads. |

The acceptance suite MUST pass before any of these start. Skipping it has produced regressions in earlier rounds.