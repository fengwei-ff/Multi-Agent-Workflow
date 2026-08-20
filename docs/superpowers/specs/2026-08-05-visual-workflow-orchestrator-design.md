# Visual Workflow Orchestrator Design

**Date:** 2026-08-05  
**Status:** Approved for implementation planning  
**Scope:** Template-first visual orchestration + semi-dynamic LangGraph execution (branch / loop / parallel)

## Goals

1. Users design agent task flows on a node canvas before creating runs.
2. Product IA is **orchestration-first**: templates are primary; tasks are instances under a template.
3. Migrate the existing fixed「需求设计」graph into the first **built-in** template.
4. Support template composition **and** control-flow: condition, loop, parallel fork/join.
5. Creating a run **snapshots** the current DSL so later template edits do not affect in-flight or historical runs.
6. Built-in templates are **read-only** in the editor; users must **duplicate** before editing.

## Non-Goals (v1)

- Template version history / version picker UI
- Sub-workflows, tool/HTTP/sandbox nodes
- Multi-user collaboration / realtime co-edit
- YAML dual-mode editing
- Always-bind-to-latest-template execution

## Current Baseline

- Backend: FastAPI + single compiled LangGraph in `apps/api/app/graph/workflow.py` (`intent → discuss → HITL → tech_design → HITL → codegen`).
- Threads meta: `apps/api/.data/threads.json`; checkpoints in SQLite.
- Frontend: single task list + chat/artifacts UI (`apps/web/src/App.tsx`).
- Shared types already allow optional `workflow_id` on create-thread requests.

## Approach

**DSL + dynamic LangGraph compilation** (chosen over “UI-only mapping to fixed graphs”).

- Canvas persists a JSON workflow definition.
- Runtime compiles a snapshot into a LangGraph graph (conditional edges, loops, parallel).
- Built-in「需求设计」is the same DSL shape as user templates; seeded on startup if missing.

## Information Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Multi-Agent Workflow                                       │
├──────────────┬──────────────────────────────────────────────┤
│ Templates    │  Selected template                            │
│ • 需求设计 ★ │  Tabs: [编排] [任务实例]                        │
│ • (user)…   │                                               │
│ [+ 新建]     │  编排: node library | canvas | config panel   │
│              │  任务: run list + [新建任务] → run detail      │
└──────────────┴──────────────────────────────────────────────┘
```

- Left sidebar: **workflow templates** (not threads).
- Main area for selected template:
  - **编排**: React Flow canvas.
  - **任务实例**: runs filtered by `workflow_id`; open run → existing chat / stepper / artifacts.
- **新建任务** only from the current template context.
- Built-in template: canvas is view-only; actions = **复制** / **基于此新建任务**. Direct save/delete disabled.

## Data Model

### Workflow definition

```ts
type WorkflowDef = {
  id: string;
  name: string;
  description?: string;
  builtin: boolean;
  created_at: string;
  updated_at: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  viewport?: { x: number; y: number; zoom: number };
};

type NodeType =
  | 'start' | 'end'
  | 'intent' | 'discuss' | 'tech_design' | 'codegen' | 'llm'
  | 'hitl'
  | 'condition' | 'loop'
  | 'parallel_fork' | 'parallel_join';

type WorkflowNode = {
  id: string;
  type: NodeType;
  position: { x: number; y: number };
  data: Record<string, unknown>;
};

type WorkflowEdge = {
  id: string;
  source: string;
  target: string;
  /** condition: "true" | "false"; parallel branch id; optional otherwise */
  sourceHandle?: string;
  label?: string;
};
```

### Persistence

| Entity | Storage |
|--------|---------|
| Templates | `apps/api/.data/workflows.json` |
| Built-in seed | Code module; on API startup, upsert by id if absent (never overwrite user-copied edits; never mutate builtin body from API writes) |
| Runs / threads | Extend thread meta: `workflow_id`, `workflow_name`, `workflow_snapshot` (full `WorkflowDef` copy at create time) |
| Checkpoints | Existing SQLite checkpointer, keyed by `thread_id` |

### Builtin edit policy

- `PUT /workflows/{id}` and `DELETE /workflows/{id}` return **403** when `builtin === true`.
- UI hides save/delete; shows **复制为可编辑模板**.
- `POST /workflows/{id}/duplicate` creates `builtin: false` copy with new id and name like `{name} (副本)`.

### Run snapshot policy

- On `POST /workflows/{id}/runs` (or create-thread with `workflow_id`): deep-copy current template into `workflow_snapshot`.
- Stream / resume / retry / compile **only** use `workflow_snapshot`, never live template.
- Template deletes: existing runs remain (snapshot retained); list may show stale `workflow_name` from snapshot.

## Node Semantics (v1)

| Type | Runtime behavior | Key `data` fields |
|------|------------------|-------------------|
| `start` / `end` | Graph entry / exit | — |
| `intent` | Existing intent LLM node | optional prompt overrides |
| `discuss` | Existing discuss node | `max_rounds` (default from settings) |
| `tech_design` | Existing tech design node | optional prompt overrides |
| `codegen` | Existing codegen (streaming) | optional prompt overrides |
| `llm` | Generic LLM text/JSON | `system`, `user_template`, `output_mode`, `output_key` |
| `hitl` | `interrupt()` | `kind`, `title`, `options[]`, summary fields |
| `condition` | Conditional edges | `expression` over state (v1: allowlist paths / simple equality, e.g. `alignment_status == "aligned"`) |
| `loop` | Back-edge until stop or cap | `max_iterations`, `continue_when` expression |
| `parallel_fork` | Fan-out | — |
| `parallel_join` | Fan-in / barrier | — |

### Built-in「需求设计」topology

Logical flow (exact node ids chosen at seed time):

```
start
  → intent
  → discuss
  → hitl(alignment) ──continue_discuss──→ discuss (loop / back-edge)
       │ approve
       ▼
  tech_design
  → hitl(design_approval) ──revise──→ tech_design
       │ approve
       ▼
  codegen → end
```

Discussion/revision limits map to loop/`max_iterations` and existing guard messages where applicable.

## Runtime Architecture

```
Create run → load template → snapshot → compile_workflow(snapshot)
                                         → LangGraph CompiledGraph
Stream/resume/retry → get_graph_for_thread(thread) using snapshot only
```

### Compiler responsibilities

1. Validate: exactly one `start` and one `end`; all nodes reachable from start (warn or error); `condition` has both `true`/`false` handles; loops only via `loop` or explicit back-edges attached to loop/HITL revise paths; no illegal cycles.
2. Map each node type to a runnable function (reuse existing handlers for domain nodes).
3. Map edges to LangGraph edges; conditions → `add_conditional_edges`; parallel fork → multiple outgoing; join → convergence.
4. Fail closed: invalid snapshot → API 400 with structured errors (node/edge ids) for canvas highlighting.

### State

- Keep existing `WorkflowState` fields used by artifacts UI (`requirements_doc`, `tech_design`, `generated_code`, messages, interrupt metadata, etc.).
- Add `node_outputs: dict[str, Any]` for generic `llm` / future nodes.
- Add `workflow_id` / optional `active_node_id` for UI highlighting if useful.
- Stepper on run detail is **derived from snapshot nodes** (ordered main path or phase mapping), not hard-coded `req/tech/code` only — but for the builtin template, UI can still show the familiar three stages via node-type → stage mapping.

## API

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/workflows` | List templates |
| `POST` | `/workflows` | Create empty or from body |
| `GET` | `/workflows/{id}` | Detail |
| `PUT` | `/workflows/{id}` | Update; **403 if builtin** |
| `DELETE` | `/workflows/{id}` | Delete; **403 if builtin** |
| `POST` | `/workflows/{id}/duplicate` | Copy → editable |
| `GET` | `/workflows/{id}/runs` | Threads for template |
| `POST` | `/workflows/{id}/runs` | Create run: body `{ user_request }`; snapshot + start graph |
| existing | `/threads/{id}/...` | stream, resume, retry, preview remain; resolve graph via snapshot |

Backward compatibility: if a legacy thread has no snapshot, fall back to compiling the builtin「需求设计」template (or keep temporary hard-coded graph until migrated). Prefer one-time migration note: old threads without `workflow_id` attach to builtin id in list UI as “未绑定 / 历史”.

## Frontend

### Stack

- `@xyflow/react` for canvas.
- Left: node palette grouped (Agent / HITL / Control).
- Center: canvas with connectable handles.
- Right: selected-node config form (type-specific).
- Toolbar: Save (disabled for builtin), Duplicate, Validate.

### Task instance tab

- Table/list of runs for this `workflow_id`.
- Create run modal: `user_request` only (template implied).
- Click run → navigate to run detail (reuse current chat + artifacts; adjust shell so user can return to template).

### Routing / shell

Refactor `App.tsx` into clearer views without big visual redesign:

- Template list + canvas + runs.
- Run detail (existing experience).

Keep current dark theme tokens/styles.

## Error Handling

- Template validation errors: field-level + canvas node error badges.
- Compile errors at run create: do not create thread; return errors.
- Mid-run node failure: existing interrupt / `can_retry` patterns.
- Builtin write attempts: 403 with clear message.

## Testing (v1)

- Unit: DSL validation; compile builtin template equals expected node sequence; condition/loop/parallel small fixtures.
- API: CRUD + builtin 403 + duplicate + create run stores snapshot; editing template does not change existing run snapshot.
- Manual: open builtin view-only → duplicate → edit → save → create run → chat/HITL/codegen still work.

## Implementation Phases (for planning)

1. Shared types + workflows JSON store + seed builtin DSL.
2. Compiler + wire create-run/stream to snapshot; retire sole hard-coded graph entrypoint.
3. Workflow CRUD APIs + runs listing.
4. Frontend shell: template-first navigation + React Flow editor (builtin read-only).
5. Runs tab + create run + run detail integration; dynamic stepper mapping.
6. Control-flow polish: condition/loop/parallel UI + compiler tests.

## Decisions Log

| Decision | Choice |
|----------|--------|
| Editor | Node canvas (React Flow) |
| IA | Orchestration-first; tasks under template |
| Node set | Domain agents + HITL + condition/loop/parallel + start/end |
| Execution | DSL → dynamic LangGraph |
| Mutability of runs | Snapshot at create |
| Builtin templates | Read-only; duplicate to edit |
| Template versioning | Deferred |

## Success Criteria

- User can open「需求设计」, view canvas, cannot save over it, can duplicate and edit the copy.
- User can create a run from a template and complete the existing HITL → codegen path.
- User can add a condition or loop on a duplicated template and have the compiled graph respect it.
- Editing a template after a run starts does not change that run’s behavior.
