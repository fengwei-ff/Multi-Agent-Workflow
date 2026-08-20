# Visual Workflow Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship template-first visual orchestration (React Flow) with DSL snapshots compiled to LangGraph, including the built-in read-only「需求设计」template plus condition/loop/parallel control flow.

**Architecture:** Templates live in `workflows.json` (seeded builtin). Creating a run deep-copies the template into `ThreadMeta.workflow_snapshot`. A compiler maps nodes/edges → LangGraph. Domain node functions are reused from today’s graph but routing comes from the DSL (HITL/`condition`/`loop`/`parallel_*`), not hard-coded `Command(goto=...)`. Frontend is orchestration-first: template list → 编排/任务实例 tabs → run detail.

**Tech Stack:** FastAPI, LangGraph, Pydantic, pytest; React 19, Vite, `@xyflow/react`; shared types in `@workflow-agent/shared`.

**Spec:** `docs/superpowers/specs/2026-08-05-visual-workflow-orchestrator-design.md`

**Note:** This workspace may not have a git repo. Commit steps: run only if `.git` exists; otherwise mark the step done after verifying files.

---

## File structure (target)

| Path | Responsibility |
|------|----------------|
| `packages/shared/src/index.ts` | Shared TS types for WorkflowDef / nodes / edges / APIs |
| `apps/api/app/workflows/__init__.py` | Package export |
| `apps/api/app/workflows/schema.py` | Pydantic WorkflowDef models |
| `apps/api/app/workflows/store.py` | Load/save `workflows.json`, CRUD, duplicate, seed hook |
| `apps/api/app/workflows/seed.py` | Builtin「需求设计」DSL constant |
| `apps/api/app/workflows/validate.py` | Structural validation → list of errors |
| `apps/api/app/workflows/expr.py` | Safe allowlisted expression eval for condition/loop |
| `apps/api/app/graph/nodes.py` | Pure node handlers (intent/discuss/design/codegen/llm/hitl) extracted from `workflow.py` |
| `apps/api/app/graph/compiler.py` | `compile_workflow(def) → StateGraph` / compiled runnable |
| `apps/api/app/graph/runtime.py` | Checkpointer lifecycle + `get_graph_for_snapshot(snapshot)` cache |
| `apps/api/app/graph/workflow.py` | Thin re-exports / legacy shim during migration |
| `apps/api/app/models.py` | Extend ThreadMeta + WorkflowState |
| `apps/api/app/service.py` | Snapshot on create; resolve graph via snapshot; list runs by workflow |
| `apps/api/app/main.py` | Workflow CRUD + runs endpoints; seed on lifespan |
| `apps/api/tests/...` | Unit/API tests |
| `apps/web/src/api.ts` | Workflow + runs client |
| `apps/web/src/App.tsx` | Shell: template-first routing |
| `apps/web/src/views/TemplateWorkspace.tsx` | Tabs 编排 / 任务实例 |
| `apps/web/src/views/RunDetail.tsx` | Existing chat/artifacts extracted |
| `apps/web/src/editor/*` | React Flow canvas, palette, config panel |
| `apps/web/src/styles.css` | Editor + shell styles |

---

### Task 1: Shared workflow types

**Files:**
- Modify: `packages/shared/src/index.ts`
- Test: manual `pnpm --filter @workflow-agent/shared exec tsc -p packages/shared --noEmit` (or workspace lint)

- [ ] **Step 1: Append workflow DSL types** to `packages/shared/src/index.ts` (keep existing phase/thread types):

```ts
export type WorkflowNodeType =
  | 'start'
  | 'end'
  | 'intent'
  | 'discuss'
  | 'tech_design'
  | 'codegen'
  | 'llm'
  | 'hitl'
  | 'condition'
  | 'loop'
  | 'parallel_fork'
  | 'parallel_join';

export interface WorkflowNodePosition {
  x: number;
  y: number;
}

export interface WorkflowNode {
  id: string;
  type: WorkflowNodeType;
  position: WorkflowNodePosition;
  data: Record<string, unknown>;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  label?: string;
}

export interface WorkflowViewport {
  x: number;
  y: number;
  zoom: number;
}

export interface WorkflowDef {
  id: string;
  name: string;
  description?: string;
  builtin: boolean;
  created_at: string;
  updated_at: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  viewport?: WorkflowViewport;
}

export interface WorkflowSummary {
  id: string;
  name: string;
  description?: string;
  builtin: boolean;
  updated_at: string;
}

export interface CreateWorkflowRequest {
  name: string;
  description?: string;
  nodes?: WorkflowNode[];
  edges?: WorkflowEdge[];
}

export interface UpdateWorkflowRequest {
  name?: string;
  description?: string;
  nodes?: WorkflowNode[];
  edges?: WorkflowEdge[];
  viewport?: WorkflowViewport;
}

export interface CreateRunRequest {
  user_request: string;
}

export interface CreateRunResponse {
  thread_id: string;
}
```

- [ ] **Step 2: Extend `ThreadSummary` and `ThreadStateView`**

```ts
export interface ThreadSummary {
  thread_id: string;
  title: string;
  phase?: WorkflowPhase;
  workflow_id?: string;
  workflow_name?: string;
  created_at: string;
  updated_at: string;
}

// On ThreadStateView add:
// workflow_id?: string;
// workflow_name?: string;
```

- [ ] **Step 3: Verify TypeScript builds**

Run: `pnpm --filter @workflow-agent/web lint`  
Expected: PASS (or only pre-existing errors unrelated to shared types)

- [ ] **Step 4: Commit (if git available)**

```bash
git add packages/shared/src/index.ts
git commit -m "feat(shared): add workflow DSL and summary types"
```

---

### Task 2: Pydantic schema + expression evaluator

**Files:**
- Create: `apps/api/app/workflows/__init__.py`
- Create: `apps/api/app/workflows/schema.py`
- Create: `apps/api/app/workflows/expr.py`
- Create: `apps/api/tests/test_expr.py`

- [ ] **Step 1: Create package init**

`apps/api/app/workflows/__init__.py`:

```python
from app.workflows.schema import WorkflowDef, WorkflowEdge, WorkflowNode

__all__ = ['WorkflowDef', 'WorkflowNode', 'WorkflowEdge']
```

- [ ] **Step 2: Write `schema.py`** mirroring shared types with Pydantic `BaseModel`, `NodeType` Literal, default `data: dict = {}`.

- [ ] **Step 3: Write failing expr tests**

```python
# apps/api/tests/test_expr.py
from app.workflows.expr import eval_expression

def test_equality_true():
    assert eval_expression('alignment_status == "aligned"', {'alignment_status': 'aligned'}) is True

def test_equality_false():
    assert eval_expression('alignment_status == "aligned"', {'alignment_status': 'pending'}) is False

def test_numeric_compare():
    assert eval_expression('discussion_rounds >= 3', {'discussion_rounds': 3}) is True

def test_rejects_unknown_name():
    try:
        eval_expression('__import__("os")', {})
        assert False, 'should raise'
    except ValueError:
        pass
```

- [ ] **Step 4: Run tests — expect fail**

Run: `cd apps/api && PYTHONPATH=. python -m pytest tests/test_expr.py -v`  
Expected: FAIL (module missing)  
(If pytest missing: `pip install pytest` in conda env `vEffect`.)

- [ ] **Step 5: Implement `expr.py`**

Allow only: identifiers from an allowlist matching WorkflowState keys + comparisons (`==`, `!=`, `>=`, `<=`, `>`, `<`) and string/number literals. Parse with `ast.parse` in eval mode; walk AST and reject anything else (`Call`, `Attribute`, etc.). Return `bool`.

- [ ] **Step 6: Run tests — expect pass**

Run: `cd apps/api && PYTHONPATH=. python -m pytest tests/test_expr.py -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/workflows apps/api/tests/test_expr.py
git commit -m "feat(api): workflow schema and safe expression evaluator"
```

---

### Task 3: Workflow store + builtin seed

**Files:**
- Create: `apps/api/app/workflows/seed.py`
- Create: `apps/api/app/workflows/store.py`
- Create: `apps/api/app/workflows/validate.py`
- Create: `apps/api/tests/test_workflow_store.py`
- Create: `apps/api/tests/test_validate.py`

- [ ] **Step 1: Define builtin id constant**

```python
# seed.py
BUILTIN_REQUIREMENT_DESIGN_ID = 'requirement_design'
```

Build `REQUIREMENT_DESIGN_WORKFLOW: WorkflowDef` with nodes/edges matching:

```
start → intent → discuss → hitl_alignment
hitl_alignment [continue_discuss] → discuss
hitl_alignment [approve] → tech_design → hitl_design
hitl_design [revise] → tech_design
hitl_design [approve] → codegen → end
hitl_* [terminate] → end
```

HITL `data` examples:

```python
{
  'kind': 'alignment',
  'title': '需求对齐确认',
  'options': ['approve', 'continue_discuss', 'terminate'],
}
```

Positions: vertical spacing ~120px for readable canvas.

- [ ] **Step 2: Implement `validate.py`**

`validate_workflow(def) -> list[dict]` each `{code, message, node_id?, edge_id?}`.

Rules:
- exactly one `start`, one `end`
- unique node ids, unique edge ids
- edges reference existing nodes
- every `condition` has outgoing edges with `sourceHandle` `true` and `false`
- every `hitl` has at least one outgoing edge
- `parallel_fork` has ≥2 outgoing; each parallel branch eventually reaches a `parallel_join` (simple: all fork outs reachable to same join id stored in fork `data.join_id` OR structural BFS — pick `data.join_id` on fork for v1)
- no unknown node types

- [ ] **Step 3: Implement `store.py`**

Path: `apps/api/.data/workflows.json` (same parent as threads).

Functions:
- `ensure_seeded() -> None` — if builtin id missing, insert seed (do **not** overwrite if present)
- `list_workflows() -> list[WorkflowDef]`
- `get_workflow(id) -> WorkflowDef | None`
- `create_workflow(...) -> WorkflowDef`
- `update_workflow(id, ...) -> WorkflowDef` — raise `PermissionError` if builtin; raise `KeyError` if missing
- `delete_workflow(id)` — same builtin guard
- `duplicate_workflow(id) -> WorkflowDef` — new uuid, `builtin=False`, name `f'{name} (副本)'`

- [ ] **Step 4: Tests**

```python
def test_seed_idempotent(tmp_path, monkeypatch):
    # monkeypatch store path to tmp_path / 'workflows.json'
    ensure_seeded()
    ensure_seeded()
    items = list_workflows()
    assert sum(1 for w in items if w.id == 'requirement_design') == 1
    assert items[0].builtin is True

def test_cannot_update_builtin():
    ensure_seeded()
    try:
        update_workflow('requirement_design', name='x')
        assert False
    except PermissionError:
        pass

def test_duplicate_is_editable():
    ensure_seeded()
    copy = duplicate_workflow('requirement_design')
    assert copy.builtin is False
    updated = update_workflow(copy.id, name='可编辑')
    assert updated.name == '可编辑'
```

Validate test: builtin seed has `validate_workflow(seed) == []`.

- [ ] **Step 5: Run pytest**

Run: `cd apps/api && PYTHONPATH=. python -m pytest tests/test_workflow_store.py tests/test_validate.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/workflows apps/api/tests
git commit -m "feat(api): workflow JSON store, validation, and builtin seed"
```

---

### Task 4: Extract node handlers (no hard-coded goto)

**Files:**
- Create: `apps/api/app/graph/nodes.py`
- Modify: `apps/api/app/models.py` (add `node_outputs`, `workflow_id`, loop counters)
- Modify: `apps/api/app/graph/workflow.py` (import handlers; keep old builder temporarily)

- [ ] **Step 1: Move** `understand_intent`, `discuss`, `design_tech`, `generate_code` into `nodes.py` unchanged in behavior (still return state dicts).

- [ ] **Step 2: Add generic handlers in `nodes.py`**

```python
async def node_llm(state, *, node_id: str, data: dict) -> dict: ...
async def node_hitl(state, *, data: dict) -> dict:
    # interrupt(payload); write last decision into state['pending_hitl_action']
    ...

async def node_condition_passthrough(state) -> dict:
    return {}  # routing done by conditional_edges

async def node_loop_gate(state, *, node_id: str, data: dict) -> dict:
    # increment loop_counts[node_id]; used by router
    ...

async def node_parallel_fork(state) -> dict:
    return {}

async def node_parallel_join(state) -> dict:
    return {}

async def node_start(state) -> dict:
    return {'phase': state.get('phase') or 'intent'}

async def node_end(state) -> dict:
    return {'phase': 'done'}
```

HITL must **not** use `Command(goto=...)`. It only `interrupt`s and returns updates including `pending_hitl_action` from the decision dict’s `action`.

- [ ] **Step 3: Extend `WorkflowState`**

```python
node_outputs: dict[str, Any]
workflow_id: str
pending_hitl_action: str
loop_counts: dict[str, int]
```

- [ ] **Step 4: Keep `create_workflow_builder()` working** by importing from `nodes.py` until Task 5 replaces entrypoint — smoke import:

Run: `cd apps/api && PYTHONPATH=. python -c "from app.graph import nodes; from app.graph.workflow import create_workflow_builder; print('ok')"`  
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/graph/nodes.py apps/api/app/models.py apps/api/app/graph/workflow.py
git commit -m "refactor(api): extract graph node handlers without Command goto for HITL"
```

---

### Task 5: DSL compiler + runtime graph cache

**Files:**
- Create: `apps/api/app/graph/compiler.py`
- Create: `apps/api/app/graph/runtime.py`
- Create: `apps/api/tests/test_compiler.py`
- Modify: `apps/api/app/graph/workflow.py` — delegate `get_compiled_graph` / shutdown to runtime; remove sole hard-coded path as the create-run entry (keep helper for tests if needed)

- [ ] **Step 1: Write compiler tests first**

```python
from app.workflows.seed import REQUIREMENT_DESIGN_WORKFLOW
from app.workflows.validate import validate_workflow
from app.graph.compiler import compile_workflow_builder

def test_builtin_valid():
    assert validate_workflow(REQUIREMENT_DESIGN_WORKFLOW) == []

def test_compile_builtin_has_nodes():
    builder = compile_workflow_builder(REQUIREMENT_DESIGN_WORKFLOW)
    # LangGraph StateGraph exposes nodes via builder.nodes
    assert 'intent' in builder.nodes or any('intent' in n for n in builder.nodes)
```

Add a tiny condition fixture workflow (start → condition → end/end) and assert compile succeeds.

- [ ] **Step 2: Implement `compile_workflow_builder(workflow: WorkflowDef) -> StateGraph`**

Algorithm:
1. `errors = validate_workflow(...)`; if errors: raise `ValueError` with JSON-serializable list.
2. Skip adding LangGraph nodes for type `start` (use `START` edge to its sole target). Treat `end` as edge to `END` (end node can be a no-op or omitted).
3. For each other node, `builder.add_node(node.id, partial(handler, data=node.data, node_id=node.id))`.
4. Wire edges:
   - From logical start’s outgoing → `builder.add_edge(START, target)`
   - Normal: `add_edge(source, target)`
   - Into end: `add_edge(source, END)`
   - `condition` / `loop` / `hitl`: `add_conditional_edges(source, router_fn, path_map)`
5. Routers:
   - **hitl**: read `state['pending_hitl_action']`; map to edge whose `sourceHandle == action` (or `label`); default first edge / raise
   - **condition**: `eval_expression(data['expression'], state)` → `'true'|'false'` handle
   - **loop**: if `eval_expression(continue_when)` and `loop_counts[id] < max_iterations` → handle `continue` else `exit`
   - **parallel_fork**: LangGraph allows multiple static edges from fork to branch starts; join node waits naturally when all parents complete (document: branches must be independent subgraphs ending at same join)

- [ ] **Step 3: Implement `runtime.py`**

- Shared checkpointer init (move from `workflow.py`)
- `async def get_graph_for_snapshot(snapshot: WorkflowDef)`:
  - cache key = `snapshot.id + ':' + hash(canonical_json(snapshot))`
  - compile + `builder.compile(checkpointer=...)`
- `async def shutdown_runtime()`
- Legacy threads without snapshot: load builtin from store and compile that

- [ ] **Step 4: Update `workflow.py`**

```python
async def get_compiled_graph():
    # deprecated for multi-workflow; used only if something still calls it
    from app.workflows.store import get_workflow, ensure_seeded
    ensure_seeded()
    wf = get_workflow('requirement_design')
    from app.graph.runtime import get_graph_for_snapshot
    return await get_graph_for_snapshot(wf)
```

- [ ] **Step 5: Run compiler tests**

Run: `cd apps/api && PYTHONPATH=. python -m pytest tests/test_compiler.py -v`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/graph apps/api/tests/test_compiler.py
git commit -m "feat(api): compile workflow DSL to LangGraph with control-flow routers"
```

---

### Task 6: Service + API wiring (CRUD, runs, snapshots)

**Files:**
- Modify: `apps/api/app/models.py` — `ThreadMeta.workflow_snapshot: dict | None`, `workflow_name`
- Modify: `apps/api/app/service.py`
- Modify: `apps/api/app/main.py`
- Create: `apps/api/tests/test_workflows_api.py` (optional httpx AsyncClient)

- [ ] **Step 1: Extend ThreadMeta**

```python
class ThreadMeta(BaseModel):
    thread_id: str
    title: str
    workflow_id: str = 'requirement_design'
    workflow_name: str = '需求设计'
    workflow_snapshot: dict[str, Any] | None = None
    created_at: str
    updated_at: str
```

- [ ] **Step 2: Change create path**

```python
def create_thread_meta(user_request: str, workflow_id: str) -> ThreadMeta:
    from copy import deepcopy
    from app.workflows.store import get_workflow, ensure_seeded
    from app.workflows.validate import validate_workflow
    ensure_seeded()
    wf = get_workflow(workflow_id)
    if wf is None:
        raise ValueError(f'Unknown workflow_id: {workflow_id}')
    errors = validate_workflow(wf)
    if errors:
        raise ValueError(f'Invalid workflow: {errors}')
    snapshot = deepcopy(wf.model_dump())
    ...
```

- [ ] **Step 3: `start_run` / `resume_run` / `retry_run`**

Replace `await get_compiled_graph()` with:

```python
meta = get_thread_meta(thread_id)
snapshot = WorkflowDef.model_validate(meta.workflow_snapshot) if meta.workflow_snapshot else get_workflow('requirement_design')
graph = await get_graph_for_snapshot(snapshot)
```

- [ ] **Step 4: Add helpers**

```python
def list_threads_for_workflow(workflow_id: str) -> list[ThreadMeta]:
    return [t for t in list_threads() if t.workflow_id == workflow_id]
```

- [ ] **Step 5: Replace stub `GET /workflows` in `main.py` with full CRUD**

```python
@app.on_event / lifespan: ensure_seeded()

GET    /workflows
POST   /workflows
GET    /workflows/{id}
PUT    /workflows/{id}      # PermissionError → 403
DELETE /workflows/{id}      # 403 builtin
POST   /workflows/{id}/duplicate
GET    /workflows/{id}/runs
POST   /workflows/{id}/runs  # body CreateThreadBody.user_request → create_thread_meta + return thread_id
```

Keep `POST /threads` as compatibility wrapper calling same create with `workflow_id`.

- [ ] **Step 6: Manual smoke**

```bash
# API running
curl -s localhost:8000/workflows | head
curl -s -X POST localhost:8000/workflows/requirement_design/duplicate
curl -s -X PUT localhost:8000/workflows/requirement_design -H 'Content-Type: application/json' -d '{"name":"x"}'
# expect 403
```

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/models.py apps/api/app/service.py apps/api/app/main.py apps/api/tests
git commit -m "feat(api): workflow CRUD, run snapshot, and compile-per-snapshot execution"
```

---

### Task 7: Frontend API client + shell IA

**Files:**
- Modify: `apps/web/src/api.ts`
- Create: `apps/web/src/views/RunDetail.tsx` (extract from `App.tsx`)
- Modify: `apps/web/src/App.tsx` — template list + view mode
- Modify: `apps/web/src/styles.css`

- [ ] **Step 1: Add API functions**

```ts
export async function listWorkflows(): Promise<WorkflowSummary[]> { ... }
export async function getWorkflow(id: string): Promise<WorkflowDef> { ... }
export async function createWorkflow(body: CreateWorkflowRequest): Promise<WorkflowDef> { ... }
export async function updateWorkflow(id: string, body: UpdateWorkflowRequest): Promise<WorkflowDef> { ... }
export async function deleteWorkflow(id: string): Promise<void> { ... }
export async function duplicateWorkflow(id: string): Promise<WorkflowDef> { ... }
export async function listWorkflowRuns(workflowId: string): Promise<ThreadSummary[]> { ... }
export async function createWorkflowRun(workflowId: string, userRequest: string): Promise<string> { ... }
```

- [ ] **Step 2: Extract `RunDetail`**

Move current chat / stepper / artifacts / preview modal into `RunDetail.tsx` with props:

```ts
type Props = {
  threadId: string;
  onBack: () => void;
};
```

`onBack` returns to template workspace (任务实例 tab).

- [ ] **Step 3: Restructure `App` state**

```ts
type View =
  | { kind: 'workspace'; workflowId: string; tab: 'editor' | 'runs' }
  | { kind: 'run'; workflowId: string; threadId: string };

// Sidebar: workflows from listWorkflows()
// Main: TemplateWorkspace or RunDetail
```

- [ ] **Step 4: TemplateWorkspace skeleton (no React Flow yet)**

Tabs 编排 | 任务实例. 编排 tab: placeholder “画布加载中…” + Duplicate / New run buttons. 任务实例: list runs + create modal (`user_request`). Builtin: disable Save/Delete.

- [ ] **Step 5: Manual UI check**

Run web: open app → see「需求设计」in sidebar → tabs work → create run still executes old path if compiler wired.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src
git commit -m "feat(web): orchestration-first shell with workflow API client"
```

---

### Task 8: React Flow editor (read-only builtin)

**Files:**
- Create: `apps/web/src/editor/WorkflowCanvas.tsx`
- Create: `apps/web/src/editor/NodePalette.tsx`
- Create: `apps/web/src/editor/NodeConfigPanel.tsx`
- Create: `apps/web/src/editor/nodeTypes.tsx`
- Modify: `apps/web/package.json` — add `@xyflow/react`
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/src/views/TemplateWorkspace.tsx`

- [ ] **Step 1: Install dependency**

```bash
pnpm --filter @workflow-agent/web add @xyflow/react
```

- [ ] **Step 2: Implement canvas**

- Map `WorkflowDef.nodes/edges` ↔ React Flow nodes/edges
- Custom nodes show type label + title from `data.title` or type
- Handles: `condition` left in / right `true`+`false`; `hitl` handles per `data.options`; `parallel_fork` multiple source handles
- `nodesDraggable={!builtin}`, `nodesConnectable={!builtin}`, `elementsSelectable={true}`
- onChange local state; Save calls `updateWorkflow` when `!builtin`
- Duplicate always available
- Validate button: client-side check mirroring critical rules OR POST save and show API errors

- [ ] **Step 3: Palette + config panel**

Palette groups: Agent (`intent`,`discuss`,`tech_design`,`codegen`,`llm`), HITL, Control (`condition`,`loop`,`parallel_fork`,`parallel_join`,`start`,`end`). Drag-to-add disabled when builtin.

Config fields by type:
- `hitl`: kind, title, options (comma-separated)
- `condition`: expression string
- `loop`: continue_when, max_iterations
- `llm`: system, user_template, output_key
- `discuss`: max_rounds

- [ ] **Step 4: Wire into TemplateWorkspace 编排 tab**

- [ ] **Step 5: Manual**

Open builtin → cannot save → Duplicate → edit name/node → Save → reload persists.

- [ ] **Step 6: Commit**

```bash
git add apps/web/package.json apps/web/src/editor apps/web/src/views apps/web/src/styles.css pnpm-lock.yaml
git commit -m "feat(web): React Flow workflow editor with read-only builtin"
```

---

### Task 9: Dynamic stepper + end-to-end verification

**Files:**
- Modify: `packages/shared/src/index.ts` — helper `stepperFromSnapshot(nodes)`
- Modify: `apps/web/src/views/RunDetail.tsx`
- Create: `apps/api/tests/test_snapshot_isolation.py`

- [ ] **Step 1: Stepper helper**

Map node types to stages:

```ts
export function stepperFromWorkflow(nodes: WorkflowNode[]): Array<{ id: string; label: string }> {
  const stages: Array<{ id: string; label: string }> = [];
  const push = (id: string, label: string) => {
    if (!stages.some((s) => s.id === id)) stages.push({ id, label });
  };
  for (const n of nodes) {
    if (n.type === 'intent' || n.type === 'discuss' || (n.type === 'hitl' && n.data?.kind === 'alignment')) {
      push('req', '需求对齐');
    } else if (n.type === 'tech_design' || (n.type === 'hitl' && n.data?.kind === 'design_approval')) {
      push('tech', '技术方案');
    } else if (n.type === 'codegen') {
      push('code', '产出代码');
    }
  }
  push('done', '完成');
  return stages;
}
```

RunDetail: if `state`/meta includes snapshot stages use them; else `STEPPER_STEPS`.

Expose snapshot summary on `GET /threads/{id}` optional fields `workflow_id`, `workflow_name` (already planned).

- [ ] **Step 2: Snapshot isolation test**

```python
def test_edit_template_does_not_change_snapshot(tmp_path, monkeypatch):
    # create run from workflow W
    # update W name/nodes
    # assert thread.workflow_snapshot['name'] unchanged / nodes unchanged
```

- [ ] **Step 3: Full manual path**

1. Builtin view-only canvas shows 需求设计 topology  
2. Duplicate → add a `condition` if desired → Save  
3. 任务实例 → 新建任务 → complete HITL → codegen  
4. Edit template again → old run behavior unchanged  

- [ ] **Step 4: Commit**

```bash
git add packages/shared apps/web apps/api
git commit -m "feat: dynamic stepper and snapshot isolation verification"
```

---

### Task 10: Control-flow polish (condition / loop / parallel)

**Files:**
- Modify: `apps/api/app/graph/compiler.py` (harden routers)
- Modify: `apps/web/src/editor/*` (handles UX)
- Create: `apps/api/tests/test_control_flow.py`

- [ ] **Step 1: Tests**

- Condition workflow: expression true takes true branch (compile path_map keys)
- Loop: `max_iterations` forces exit handle
- Parallel: fork with two llm no-op stubs to join compiles without error

- [ ] **Step 2: Fix gaps found by tests** (expression edge cases, missing handles)

- [ ] **Step 3: UI**: show handle labels; validation errors badge on nodes from last save/validate

- [ ] **Step 4: Commit**

```bash
git add apps/api apps/web
git commit -m "feat: condition, loop, and parallel control-flow polish"
```

---

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| Shared DSL types | 1 |
| workflows.json + seed builtin | 3 |
| Builtin read-only / duplicate | 3, 6, 8 |
| Run snapshot | 6, 9 |
| Dynamic LangGraph compile | 5 |
| Domain nodes reused | 4 |
| condition / loop / parallel | 5, 10 |
| CRUD + runs API | 6 |
| Orchestration-first IA | 7 |
| React Flow editor | 8 |
| Dynamic stepper | 9 |
| Legacy threads fallback | 5–6 |
| Non-goals respected | (no versioning/subflow/tools) |

## Self-review notes

- No TBD placeholders in tasks.
- HITL routing explicitly moved from `Command(goto=)` to edge handles — required for DSL.
- Parallel v1 uses `data.join_id` on fork to keep validation tractable.
- Commits skipped if no `.git`.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-05-visual-workflow-orchestrator.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with checkpoints  

Which approach?
