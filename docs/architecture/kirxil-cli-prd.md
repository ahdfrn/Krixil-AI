# Kirxil AI CLI — Product Requirements Document v1.0

> Supplied by the user as a PDF (`KIRXIL_AI_CLI_PRD_v1.0.pdf`) and reproduced here as the durable,
> version-controlled reference — the PDF itself isn't in this repo. This is the **full product
> vision**, not a description of what's built. See
> [`coding-agent.md`](coding-agent.md)'s "Kirxil AI CLI (Node.js/TypeScript rewrite)" section and
> [`cli/README.md`](../../cli/README.md) for what's actually implemented against it, and
> [`roadmap.md`](roadmap.md) for the phased plan going forward. Status: Product Definition.
> Platform: Windows / macOS / Linux.

## 1. Executive Summary

Kirxil AI CLI adalah AI-powered software engineering agent yang berjalan langsung di terminal dan
dirancang untuk membantu developer dalam seluruh siklus pengembangan software.

Kirxil tidak hanya berfungsi sebagai AI coding assistant. Kirxil dirancang sebagai Autonomous
Software Engineering Platform yang mampu memahami codebase, merencanakan pekerjaan, menulis kode,
menjalankan tools, menguji hasil, melakukan debugging, melakukan security review, hingga membantu
deployment dan monitoring.

```
UNDERSTAND → PLAN → BUILD → TEST → DEBUG → REVIEW → SECURE → DEPLOY → MONITOR → SELF-HEAL
```

## 2. Problem Statement

Developer harus berpindah-pindah antara IDE, Git, terminal, repository hosting, database, Docker,
cloud, monitoring, dokumentasi, browser, dan AI assistant. Banyak AI coding tools sangat kuat
untuk generate dan edit kode, tetapi pengembangan software sebenarnya mencakup architecture,
dependency analysis, testing, debugging, security, deployment, dan monitoring.

Kirxil bertujuan mengurangi fragmentasi tersebut dengan menyediakan satu AI engineering workflow
melalui terminal.

## 3. Product Vision

Make every developer capable of operating with an autonomous AI engineering team.

```
KIRXIL AI
  │
  AI Engineering Team
  │
  ┌──────────────┼──────────────┐
  │              │              │
Architect      Engineer       DevOps
  │              │              │
Security        Tester        Monitor
```

## 4. Product Mission

Kirxil harus mampu mengubah instruksi natural language menjadi pekerjaan engineering yang
understandable, executable, verifiable, recoverable, dan auditable.

> User: "Add Google authentication to this application."
>
> Analyze → Architecture → Plan → Implement → Test → Security Review → Documentation

## 5. Target Users

- **Professional Developers** — Web, mobile backend, SaaS, API, microservices, enterprise systems.
- **Indie Hackers** — membangun produk dengan tim kecil.
- **Startup** — mempercepat MVP, feature development, dan debugging.
- **Students** — memahami architecture, coding, debugging, dan software engineering.
- **Enterprise Engineering Teams** — menggunakan Kirxil sebagai AI Engineering Workforce.

## 6. Product Goals

- **G1 — Codebase Intelligence**: memahami files, symbols, functions, classes, dependencies,
  database, APIs, architecture, Git history, dan documentation.
- **G2 — Autonomous Engineering**: menjalankan task secara end-to-end.
- **G3 — Self-Healing**: test → detect failure → diagnose → fix → retest.
- **G4 — Safe AI Execution**: permission → policy → sandbox → execution.
- **G5 — Multi-Agent**: menjalankan specialized agents secara terkoordinasi.

## 7. Non-Goals untuk MVP

- Menggantikan IDE sepenuhnya.
- Menjalankan command berbahaya tanpa permission.
- Melakukan deployment production tanpa approval.
- Mengakses secret tanpa authorization.
- Menghapus database secara otomatis.
- Melakukan autonomous financial transactions.

## 8. Core Product Architecture

```
KIRXIL CLI
  │
  ▼
SESSION MANAGER
  │
  ▼
AGENT ORCHESTRATOR
  │
  ┌─────────────┼─────────────┐
  ▼             ▼             ▼
BRAIN         TOOLS         MODELS
  │             │             │
  ▼             ▼             ▼
Context       Terminal      LLM
Memory        Filesystem    Router
Graph         Git           Vision
AST           Browser       Local
```

## 9. Interactive CLI

Command utama: `kirxil`

```
╭──────────────────────────────────────────╮
│                 KIRXIL AI                 │
│         Autonomous Software Engineer      │
╰──────────────────────────────────────────╯

Project: my-project
Branch: main
Health: 94%

kirxil >
```

## 10. Natural Language Interface

- `kirxil > explain this project`
- `kirxil > find authentication bugs`
- `kirxil > refactor the payment service`
- `kirxil > make the dashboard faster`
- `kirxil > add dark mode`
- `kirxil > make this production ready`

Natural language diterjemahkan menjadi Intent → Task → Plan → Agent execution.

## 11. Agent Orchestrator

Agent Orchestrator adalah core system yang memahami intent, memecah task, memilih agent, memilih
tools, memilih model, mengatur dependencies, mengontrol execution, dan memvalidasi hasil.

```
Task: Build payment system

           ORCHESTRATOR
                │
   ┌───────────┼───────────┐
   ▼            ▼            ▼
Architecture  Database    Security
   │            │
   └──────┬─────┘
          ▼
        Backend
          │
          ▼
        Frontend
          │
          ▼
        Tester
```

## 12. Specialized Agents

- **Architect Agent** — architecture, design patterns, dependency analysis.
- **Coding Agent** — create, modify, refactor code.
- **Debug Agent** — error analysis, logs, root cause analysis, fixing.
- **Testing Agent** — unit, integration, E2E, regression testing.
- **Security Agent** — vulnerability detection, dependency audit, secret detection, authorization
  review.
- **Database Agent** — schema, migrations, indexes, query optimization.
- **DevOps Agent** — Docker, CI/CD, deployment, infrastructure.
- **Documentation Agent** — README, API docs, changelog, architecture docs.

## 13. Project Brain

Project Brain adalah intelligence layer yang mempertahankan pemahaman struktural terhadap
project.

```
Project Brain
│
├── AST Index
├── Symbol Index
├── Dependency Graph
├── Vector Index
├── File Map
├── API Map
├── Database Map
├── Git History
└── Project Memory
```

## 14. Hybrid Context Engine

Kirxil menggunakan Semantic Search + AST + Graph + Git + Memory + Runtime Context. Dengan
pendekatan ini Kirxil dapat menggabungkan pencarian semantik dengan hubungan struktural dan
runtime.

```
User Request → Intent → Context Retrieval → Relevant Files → Dependency Graph
             → Runtime Information → LLM
```

## 15. Memory System

**Short-term Memory**
- Conversation
- Tasks
- Tool results
- Current changes

**Long-term Project Memory**
- Architecture decisions
- Coding conventions
- Known bugs
- Developer preferences
- Previous changes

> **Status**: short-term memory (per-conversation, Redis-backed) and long-term memory (durable
> per-user facts, `app/memory/`, auto-extracted from completed chat/agent turns) are both real
> and predate this CLI track entirely — Phase 1/coding-agent work already built and tested them.
> Not per-*project* the way the PRD's "Architecture decisions"/"Coding conventions" framing
> implies — it's per-user facts, not a structured project knowledge base. What this pass added:
> `kirxil memory list/add/forget/status/on/off`, a real CLI client of that already-complete
> backend (`GET`/`POST`/`DELETE /memory`, `GET`/`PATCH /memory/settings`) — no new backend
> surface, just the first way to reach it from the terminal instead of only the web app.

## 16. Tool System

```
FILE          TERMINAL      GIT           CODE              TEST          WEB
├── read      ├── execute   ├── status    ├── AST           ├── unit      ├── search
├── write     ├── process   ├── diff      ├── symbols       ├── integr.   └── documentation
├── edit      └── logs      ├── branch    └── dependency        ation
├── delete                  ├── commit        graph         └── e2e
└── search                  └── history
```

> **Status**: FILE — read/write/edit/search/delete all real (`host.*`/`code.*`, `app/tools/
> host_tools.py`/`code_tools.py`) — `delete` was a real gap for one pass (existed at the
> `host-runner` HTTP layer but wasn't a registered agent tool) and is now `host.delete_file`/
> `code.delete_file`, HIGH risk (a strictly bigger, less-reversible blast radius than write/edit
> — see that tool's own comment) and approval-gated the same way `host.run_command` is. TERMINAL
> — `execute` is real (`host.run_command`/`code.run_command`); `process`/`logs` as separate
> concepts don't exist (nothing here manages long-running/background processes). GIT —
> `status`/`diff`/`branch`/`history`/`blame` are all real as CLI passthrough commands
> (`kirxil git ...`, §28) and the agent itself can run any git subcommand via
> `host.run_command`/`code.run_command` (including `commit` — no dedicated tool for it,
> `run_command` already covers it). CODE (AST/symbols/dependency graph) —
> not built; this is Project Brain territory (§13), a real, separately-scoped future phase, not a
> gap in this pass. TEST — no dedicated tool, but the agent runs tests via `run_command` and the
> system prompt explicitly tells it to read failures and iterate (see "Stronger coding skills" in
> `coding-agent.md`). WEB — `search` is real (`web.search`, needs `TAVILY_API_KEY`);
> `documentation` (fetching/reading docs specifically) isn't a separate tool.

## 17. Permission Engine

Setiap tool memiliki risk level dan policy.

| Level | Examples | Policy |
|---|---|---|
| LOW | Read file, Search code | AUTO |
| MEDIUM | Edit file, Install package | ASK |
| HIGH | Git commit, Network, DB | ASK |
| CRITICAL | Production deploy, DB delete | BLOCK / APPROVAL |

> **Status**: real, not a mock. `host.run_command` is HIGH risk (`app/tools/host_tools.py`) — an
> agent run genuinely pauses (`status: "waiting_approval"`) until a human approves or rejects the
> exact command via `POST /tools/executions/{id}/approve|reject` (`app/tools/service.py`), the
> same endpoints the web app's Agents/Tools pages already used for other tools (e.g.
> `document.delete`, CRITICAL). `kirxil` (the CLI) now prompts for this with a real `y`/`n` in
> both `kirxil run` and the interactive REPL — see `cli/README.md`'s "Permission Engine" section.
> Approving resumes the run (the model sees the result and keeps working, via
> `run_agent(resume=True)` rebuilding the conversation from persisted steps) rather than just
> handing back one tool result and quitting. What's *not* built: nothing today reaches CRITICAL
> for `host.*`/`code.*` (so BLOCK-by-default is untested there), and there's no per-tool policy
> config — the LOW/MEDIUM/HIGH/CRITICAL → AUTO/ASK/BLOCK mapping is fixed in code, not
> user-configurable yet.

## 18. Sandbox

Agent execution harus isolated dengan pembatasan filesystem, process, network, environment,
terminal, resource limits, timeout, dan command policy.

## 19. Plan Mode

`kirxil plan`

```
PLAN
1. Analyze existing billing
2. Design subscription model
3. Update database
4. Implement billing service
5. Add webhook
6. Update frontend
7. Add tests
8. Security review

Estimated: 23 files, ~2,800 LOC
```

Tidak ada perubahan sebelum approval.

> **Status**: real, as a goal template (`kirxil plan <goal>`, `cli/src/verbs.ts`) on the same
> pipeline every other verb uses — not a distinct orchestration mode with its own state machine.
> Explicitly instructs the model to investigate, format the answer as "PLAN" + numbered steps +
> a rough file/LOC estimate if it can reasonably make one, and *not* to implement any step (the
> same read-only framing `ask`/`explain`/`analyze`/`review` already use). What's different from
> the PRD's implied version: there's no separate "approve this plan, then execute it" handoff —
> `kirxil plan` stops after producing the plan; running it for real is a separate `kirxil run`
> call with that plan (or a piece of it) as the goal.

## 20. Build Mode

`kirxil build` menjalankan workflow PLAN → IMPLEMENT → TEST → REVIEW.

> **Status**: real, as a goal template (`kirxil build <goal>`, `cli/src/verbs.ts`) — the same
> pipeline every verb uses, instructed to work through and name all four phases explicitly
> (Plan/Implement/Test/Review) in one run, including fixing and re-running a genuinely failing
> test rather than just reporting it, and reviewing its own real diff before declaring done. Not
> read-only, unlike `plan`/`ask`/`explain`/`analyze`/`review` — this one is meant to actually
> build the thing.

## 21. Auto Mode

`kirxil --auto` memungkinkan autonomous workflow, tetapi high-risk actions tetap membutuhkan
approval dan dangerous actions tetap diblokir.

> **Status**: no separate flag exists, because the PRD's own description of what Auto Mode does
> — proceed autonomously, but HIGH-risk actions still need approval and nothing reaches BLOCK —
> is already exactly the CLI's actual default behavior today (the real Permission Engine, §17:
> LOW/MEDIUM tools run immediately with no pause at all, HIGH pauses for a real `y`/`n`). There's
> no separate "ask about everything" mode a `--auto` flag would need to opt out of, so adding one
> would toggle nothing real — the honest call here was to name this explicitly rather than ship a
> flag that's cosmetic.

## 22. Self-Healing Engine

```
PLAN → IMPLEMENT → TEST
                     ├── PASS → REVIEW
                     └── FAIL → DEBUG → FIX → TEST
```

Maximum retry dapat dikonfigurasi, misalnya `max_retries: 5`.

## 23. Visual Engineering

Kirxil dapat menggunakan screenshot, design, Figma, dan browser untuk melakukan visual QA:
Screenshot → Vision Agent → Component Detection → Code Mapping → Implementation → Browser
Screenshot → Visual Diff → Fix.

## 24. Browser Agent

Browser Agent berjalan di browser sandbox dan dapat menguji alur seperti login, add product,
checkout, payment, dan verification. Jika gagal, screenshot, console logs, network logs, dan
source code dapat dikirim ke Debug Agent.

## 25. DevOps

```
Code → Build → Test → Security → Docker → Deploy → Health Check → Monitor
```

## 26. Production Monitoring

Kirxil dapat menganalisis logs, metrics, errors, latency, database, dan infrastructure untuk
mendeteksi anomaly serta memberikan rekomendasi perbaikan.

## 27. Swarm Mode

`kirxil swarm` memungkinkan task besar dipecah ke beberapa specialized agents yang dapat bekerja
paralel ketika dependency memungkinkan.

```
           ORCHESTRATOR
                │
   ┌────┼────┐
   ▼    ▼    ▼
Backend Frontend Database
   └────┼────┘
        ▼
     Testing
        ▼
     Security
```

## 28. Git Intelligence

- Branches
- Commits
- Diff
- Blame
- History

Command `review` dapat melakukan code review berbasis perubahan dan menemukan isu dengan severity
HIGH, MEDIUM, atau LOW.

> **Status**: Branches/Commits/Diff/Blame/History are all real (`kirxil git
> branch|log|diff|status|blame`, real local `git`, `cli/src/index.ts`). `kirxil review` is real too, but as a
> goal template (`cli/src/verbs.ts`) that tells the model to read `git diff` and tag findings
> HIGH/MEDIUM/LOW itself — not a separate static-analysis engine, so its quality depends on the
> model, the same as any other goal.

## 29. Checkpoint & Rollback

Setiap autonomous task memiliki checkpoint. User dapat melakukan rollback ke checkpoint
sebelumnya atau menggunakan `kirxil undo`.

> **Status**: real, git-based. `kirxil run`/the interactive REPL auto-commit whatever's changed
> in the current directory right before a goal starts (`cli/src/checkpoint.ts`'s
> `autoCheckpoint` — silent no-op outside a git repo or on an already-clean tree), and
> `kirxil undo` (`/undo` in the REPL too) resets back to right before the most recent one, after
> showing the real `git diff --stat` of what it's about to discard and waiting for a `y`/`n`.
> `kirxil checkpoint [message]` is the same snapshot, triggered manually. What's *not* built:
> this is directory/git-level, not the PRD's implied per-file/per-task fine-grained undo stack,
> and it does nothing outside a git repo — there's no separate Krixil-native journal.

## 30. Model Router

Kirxil bersifat model-agnostic. Model dipilih berdasarkan task complexity, latency, cost, context
size, capability, dan privacy.

```
Task complexity → Reasoning
Code generation → Coding
Simple question → Fast
Screenshot → Vision
Private project → Local
```

> **Status**: model-agnostic selection is real (`/model` in the REPL, `--model` on any command,
> `model.default` in `.kirxil.yml` — see §34), but automatic routing *by task type* is
> deliberately not built. This deployment has exactly two real local models
> (`llama3.1:8b`, `qwen2.5:7b`, no vision-capable model) with no benchmark data distinguishing
> which is actually better at which task — inventing a Reasoning/Coding/Fast/Vision/Local mapping
> with no real basis to justify it would be exactly the kind of fabricated capability this
> project avoids everywhere else (see `app/ai/catalog.py`'s own "no fabricated catalog entries"
> rule). The user's own preference, set once via `model.default`, is the honest version of this
> for now.

## 31. Local AI

Mode `kirxil --local` memungkinkan project sensitif menggunakan local model, local embeddings,
local vector database, dan local project brain.

## 32. Plugin Ecosystem

```
Plugin
├── tools
├── commands
├── agents
├── context providers
└── permissions
```

Target integrasi: GitHub, GitLab, Docker, Kubernetes, PostgreSQL, MySQL, Redis, AWS, Azure, GCP,
Vercel, Supabase, Firebase, Figma, Jira, Slack, Notion.

## 33. CLI Command Structure

```
kirxil
│
├── chat
├── ask
├── plan
├── build
├── agent
├── swarm
├── analyze
├── explain
├── search
├── generate
├── refactor
├── debug
├── test
├── review
├── git
├── deploy
├── monitor
├── memory
├── project
├── config
├── plugin
└── doctor
```

> **Status**: `ask`, `analyze`, `explain`, `search`, `generate`, `refactor`, `debug`, `test`,
> `review`, `plan`, `build`, `git`, `memory`, `config`, `doctor` are real (`cli/src/index.ts`,
> `cli/src/verbs.ts`) — 15 of 22, each a genuine command hitting the real backend or a real local
> tool, not a stub. `chat` isn't separate from the default interactive command (`kirxil` alone
> already is a chat-like loop); `auto` isn't a separate flag because the CLI's real default
> behavior already *is* what §21 describes (see that section's own status note). `agent`,
> `swarm`, `deploy`, `monitor`, `project`, `plugin` are not built — each needs real
> infrastructure this deployment doesn't have (a deploy target, a monitoring stack, a plugin
> sandbox, or — for `agent`/`swarm` — the multi-agent orchestrator §11/§12 describe) rather than
> being a small follow-up.

## 34. CLI Configuration

```yaml
project:
  name: my-project

model:
  default: kirxil-pro
  coding: kirxil-code
  reasoning: kirxil-reasoning

agent:
  max_iterations: 20
  max_retries: 5

permissions:
  read: allow
  write: ask
  execute: ask
  network: ask
  git: ask

sandbox:
  enabled: true

memory:
  enabled: true
```

> **Status**: real, but a deliberately small slice — `.kirxil.yml` (`cli/src/projectConfig.ts`),
> discovered by walking up from the current directory the way `git` finds `.git`, so it applies
> anywhere inside a project. Implemented: `project.name` (shown in the interactive banner instead
> of the folder name), `model.default` (used unless `--model`/`/model` overrides it), and
> `agent.max_iterations` (forwarded as `AgentRunRequest.max_steps` — only ever *tightens* the
> deployment's own `agent_max_steps` ceiling, never raises it, so a project's config can't become
> a way to bypass the operator's own resource limit; see `app/agents/service.py`'s
> `create_agent_run`). Deliberately **not** implemented: `model.coding`/`model.reasoning` (see
> §30's status note), `agent.max_retries` (no real "retry" concept distinct from a step exists to
> map it onto), `permissions:` (a client-supplied file changing what the Permission Engine
> auto-approves or blocks is a real security-policy decision that deserves its own explicit
> conversation, not a side effect of "add a config file"), `sandbox:` (`host.*` is unsandboxed by
> design already — see "Real host-folder access" in `coding-agent.md`), `memory:` (already a real
> per-*user* server-side setting, not a per-project one). `kirxil config` (a real §33 command,
> added alongside this note) shows what's actually resolved — the file it found (or that none
> was), and each of the three fields above with a plain-language fallback shown when unset,
> rather than silently defaulting with no way to check.

## 35. UX Principles

- **Transparent** — user tahu apa yang dilakukan AI.
- **Controllable** — user dapat menghentikan agent.
- **Reversible** — perubahan dapat di-rollback.
- **Explainable** — agent menjelaskan alasan perubahan.
- **Fast** — streaming output.
- **Minimal** — tidak membanjiri terminal.

## 36. End-to-End Example

```
User:
kirxil > make this project production ready

Kirxil:
Architecture     ✓
Dependencies     ✓
Database         ✓
Authentication   ✓
Security         ✓
Tests            ✓
Deployment       ✓

Found:
HIGH  3
MED   8
LOW   14

User:
fix high priority issues

Kirxil:
Planning fixes...
1. Fix authentication vulnerability
2. Add authorization middleware
3. Secure environment configuration

After approval:
✓ Authentication
✓ Authorization
✓ Environment security
✓ 238 tests passed
✓ No high severity issues
✓ Build successful

Production readiness:
███████████████████░ 97%
```

## 37. MVP Scope

- CLI
- Interactive chat
- File read
- File write
- File edit
- Code search
- Terminal execution
- Git diff
- Basic agent
- Permission system

Target MVP: Kirxil sudah dapat digunakan sebagai AI coding agent yang aman dan usable.

> **Status: all 10 items real.** CLI ✓, interactive chat ✓ (`kirxil`), file read ✓
> (`host.read_file`/`code.read_file`), file write ✓ (`host.write_file`/`code.write_file`),
> **file edit ✓** (`host.edit_file`/`code.edit_file` — added this pass: a precise, unique
> `old_string`→`new_string` replacement, distinct from `write_file`'s whole-file overwrite,
> matching how Claude Code itself separates Edit from Write), **code search ✓** (`host.
> search_files`/`code.search_files` — also added this pass: a real recursive regex search the
> *agent* can call directly, not just `kirxil search`'s local ripgrep passthrough the CLI has for
> itself — implemented as stdlib-only regex + `os.walk`, deliberately not a shell-out to `rg`,
> so it works the same regardless of what's installed on the machine or in the sandbox image),
> terminal execution ✓ (`host.run_command`, HIGH risk + approval), git diff ✓ (`kirxil git diff`,
> plus `status`/`log`/`branch`), basic agent ✓, permission system ✓ (real, see §17's status
> note). This was the last gap in the PRD's own defined MVP checklist — everything past this
> point (§38 V0.2 and later) is explicitly a later phase, not MVP.

## 38. V0.2 — Project Brain

- AST
- Symbol index
- Dependency graph
- Vector search
- Project memory
- Project rules
- Plan mode

## 39. V0.3 — Autonomous Agent

- Agent orchestrator
- Self-healing
- Test loop
- Multi-agent
- Checkpoints
- Rollback

## 40. V0.4 — Engineering Platform

- Browser agent
- Vision agent
- Security agent
- DevOps agent
- Deployment
- Monitoring

## 41. V1.0 — Kirxil Autonomous Engineering

Autonomous Engineering, Swarm, Cloud, Plugin ecosystem, Enterprise, Code, Architecture, Database,
Testing, Security, Browser, DevOps, Monitoring, Memory, Multi-agent, Local AI, Cloud AI.

## 42. Success Metrics

- Developer productivity target: time to implement feature turun 50%+.
- Debugging target: time to diagnose bug turun 60%+.
- Agent-generated changes passing tests target: >90%.
- Tasks completed without manual intervention target: >70%.

Angka-angka tersebut adalah target produk untuk validasi, bukan klaim performa yang sudah
terbukti.

## 43. North Star Metric

**Verified Engineering Tasks Completed by Kirxil.**

```
Task → Code → Test → Verification → SUCCESS
```

Fokus metrik adalah jumlah task engineering yang berhasil diselesaikan dan diverifikasi, bukan
jumlah token, chat, atau baris kode.

## 44. Competitive Positioning

| Capability | Basic AI | Coding Agent | Kirxil Target |
|---|---|---|---|
| Chat | ✓ | ✓ | ✓ |
| Code generation | ✓ | ✓ | ✓ |
| File editing | ✓ | ✓ | ✓ |
| Terminal | Limited | ✓ | ✓ |
| Project Brain | Limited | ✓ | Advanced |
| AST intelligence | — | Partial | ✓ |
| Dependency graph | — | Partial | ✓ |
| Multi-agent | — | Limited | ✓ |
| Self-healing | — | Partial | ✓ |
| Visual QA | — | Limited | ✓ |
| Browser agent | — | Partial | ✓ |
| Security agent | — | Partial | ✓ |
| DevOps | — | Limited | ✓ |
| Monitoring | — | — | ✓ |
| Local AI | Varies | ✓ | ✓ |
| Plugin ecosystem | Varies | ✓ | ✓ |
| Checkpoint/Rollback | — | ✓ | Advanced |
| Autonomous workflow | Limited | ✓ | ✓ |

## 45. Technical Architecture

```
KIRXIL CLI → Session Manager → Agent Runtime
                                    │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
              Orchestrator    Context Engine     Model Router
                    │           ┌──────┼──────┐          │
                    │           ▼      ▼      ▼          │
                    │          AST   Graph   RAG          │
                    ▼                                     ▼
              Tool Runtime                             Models
                    │
          ┌──────┼───────┐
          ▼       ▼       ▼
        Files  Terminal   Git
                  │
                  ▼
               Sandbox
                  │
                  ▼
              Project Env
```

## 46. Suggested Technology Stack

- **CLI**: TypeScript, Node.js, Ink, Commander, Zod, execa, Tree-sitter, ripgrep.
- **Backend**: TypeScript, Node.js, Fastify, PostgreSQL, Redis, BullMQ.
- **Intelligence**: Tree-sitter, Vector Database, Embeddings, Graph layer, LLM Router.
- **Infrastructure**: Docker, Kubernetes, Linux, Object Storage, Observability.

> **Deviation, deliberate**: Krixil's actual backend (`services/ai-service`) stays Python/FastAPI
> — it already exists, is fully built and tested (156 passing tests as of this writing), and
> rewriting it in Fastify/BullMQ would discard that for no functional gain. Only the **CLI**
> itself was rebuilt in the PRD's suggested Node.js/TypeScript/Ink/Commander/Zod/execa stack; the
> CLI is a client of the existing backend, same as the web app.

## 47. Repository Architecture

```
kirxil/
│
├── apps/
│   ├── cli/
│   ├── api/
│   └── web/
│
├── packages/
│   ├── agent-core/
│   ├── orchestrator/
│   ├── context-engine/
│   ├── project-brain/
│   ├── code-indexer/
│   ├── tool-runtime/
│   ├── permission-engine/
│   ├── sandbox/
│   ├── memory/
│   ├── model-router/
│   ├── git-engine/
│   ├── browser-agent/
│   ├── vision-agent/
│   ├── security-agent/
│   ├── devops-agent/
│   └── shared/
│
├── plugins/
├── tests/
├── docs/
└── infrastructure/
```

> **Deviation, deliberate**: Krixil's actual repo layout (`services/`, `apps/web/`, `cli/`,
> `training/`) wasn't restructured into this `apps/`+`packages/` monorepo shape — that's a
> separate, much larger, riskier decision than "update the CLI," not made unilaterally here.

## 48. Product Philosophy

- AI tidak boleh asal mengubah kode — **Understand first.**
- AI tidak dianggap selesai setelah menghasilkan kode — **Verify first.**
- AI tidak boleh memiliki kekuasaan tanpa batas — **Permission first.**
- Task kompleks harus dipecah — **Orchestrate first.**
- Kesalahan harus dapat dipulihkan — **Checkpoint first.**

## 49. Product Positioning

Kirxil AI bukan sekadar AI coding assistant. Kirxil diposisikan sebagai Autonomous AI Engineer dan
AI Engineering Platform.

> KIRXIL AI — Build. Debug. Test. Ship.
> Your AI Engineering Team, Inside Your Terminal.

## 50. Recommended Engineering Priority

```
01 CLI Runtime
02 Tool System
03 Permission Engine
04 Agent Runtime
05 Project Brain
06 Context Engine
07 Self-Healing Loop
08 Multi-Agent Orchestrator
09 Vision + Browser
10 DevOps + Cloud
```

Urutan ini memungkinkan Kirxil menjadi produk yang berguna sejak MVP, sementara kemampuan lanjutan
dibangun di atas fondasi agent, tools, security, dan project intelligence.

**Status against this list, as of the Node.js/TypeScript rewrite (see `coding-agent.md`)**: 01
(CLI Runtime) is done. 02 (Tool System) and 04 (Agent Runtime) are the same slice as before —
reusing `services/ai-service`'s tools and agent loop rather than rebuilding them client-side. 03
(Permission Engine) moved from "exists in the backend, unused by the CLI" to genuinely wired
end-to-end: `host.run_command` is HIGH risk, an agent run really pauses for it, `kirxil` prompts
for real approval, and approving resumes the run instead of ending it (see §17's status note
above). 05–10 are not built.

> **Visual design status (2026-09-01).** A separate, detailed terminal-UI mockup (boxed panels,
> a multi-agent orchestrator tree, a swarm graph, `brain`/`security`/`deploy` commands, "Always
> allow" permission memory, a self-healing attempt counter) was reviewed against what's actually
> real in this deployment. The real half — plan text, tool calls, diffs, risk-gated approvals, git
> state, run history — now has that visual treatment: a bordered `KIRXIL PLAN` panel with a real
> `kirxil build` handoff, a restyled permission panel with a real CRITICAL typed-confirm path,
> real diff rendering for edits, derived in-flight step labels, a real status bar, and two new real
> commands (`init`, `sessions`). The fabricated half (05 Project Brain, 08 Multi-Agent
> Orchestrator, "Always allow", any deploy/security/swarm surface) was deliberately left
> unbuilt — none of it exists in this platform yet, and rendering it would have been decorative UI
> with nothing real behind it, the one thing this whole build has consistently avoided. See
> `coding-agent.md`'s "Visual overhaul" section and `cli/README.md`.
