# Role-Based Multi-Agent-Workflow Design

**Date:** 2026-08-06
**Status:** Approved for implementation planning
**Scope:** 以「角色 agent 节点」为核心的多 agent 工作流重构；节点体系全部重新设计
**Supersedes:** `2026-08-05-visual-workflow-orchestrator-design.md` 中的节点语义部分（store / snapshot / canvas / stream 基础设施沿用）

## Background

上一版实现的节点是功能步骤（intent / discuss / tech_design / codegen）+ 通用控制节点（condition / loop / parallel_fork / parallel_join / llm），无法表达「产品 → 前后端开发 → CR → 测试」这种角色分工协作的研发流程。本次重构把节点体系改为：**节点 = agent 角色，路由 = 显式条件边**。

## Decisions Log

| Decision | Choice |
|----------|--------|
| 节点抽象 | agent 角色节点（预设 + 可自定义角色） |
| 协作/回退表达 | 全靠显式连线 + 条件边（无内置回退协议） |
| 产出形态 | 完整前后端项目（工作区文件） |
| agent 执行模型 | 带工具的 agent loop（自研，非 prebuilt） |
| 工具权限 | v1 全角色全工具开放，权限模型后续加 |
| 节点体系 | 全部重新设计：start / end / agent / hitl |
| 人工介入 | 保留 HITL 审批节点 |
| 旧数据 | 不迁移；旧模板归档，历史 run 只读 |

## Node System

画布节点只有 4 种；所有「智能」在 agent 节点内，所有「路由」在边上。

| Type | 语义 | `data` |
|------|------|--------|
| `start` | 流程入口，恰好一个 | — |
| `end` | 流程出口，可多个（交付 / 终止等不同结局） | — |
| `agent` | 角色节点，执行 agent loop | `role_id`, `task_template`, `max_steps?` |
| `hitl` | 人工审批，`interrupt()` | `title`, `options[]`, `summary_fields[]` |

被移除的节点类型：`intent / discuss / tech_design / codegen`（变成预设角色）、`condition / loop / parallel_fork / parallel_join`（条件边 + 回头边 + 多条出边天然覆盖）、`llm` 通用节点（被 agent 节点 + 自定义角色吸收）。

### 边

```ts
type EdgeCondition = {
  left: string;   // 状态字段点路径，如 'node_outputs.cr_1.verdict' | 'hitl.last_action'
  op: 'eq' | 'neq' | 'in' | 'contains' | 'gt' | 'lt' | 'exists';
  value?: unknown;
};

type WorkflowEdge = {
  id: string;
  source: string;
  target: string;
  condition?: EdgeCondition;   // 无条件边 = default 兜底
  max_iterations?: number;     // 回头边专用，默认 5
  label?: string;
};
```

- 同一节点多条出边：按画布配置顺序求值，第一条 condition 为真的生效；必须恰好一条 default 边。
- 表达式作用域白名单：`node_outputs.*`、`hitl.*`、`loop_counts.*` 及全局标量字段。**不做 eval / 任意代码执行**。
- 回退循环（CR 不通过回开发等）= 带条件的回头边；编译期给回头边自动挂计数，超 `max_iterations` 强制走 default，防死循环。

## Agent Loop Runtime

每个 agent 节点执行时启动自研 tool-calling 循环：

```
system prompt = role.system_prompt + 工作区说明 + 产物契约
user prompt   = task_template 渲染(state)   // {state 字段} 占位符

loop（最多 max_steps 轮，节点可配，默认 30）:
  LLM → tool_calls?
    ├─ 有 → 执行工具 → 结果回喂 → 继续
    └─ 无 → 最终回复即 final_result(JSON) → 结束
```

### 工具集（v1 全角色开放）

| 工具 | 说明 |
|------|------|
| `read_file(path)` | 读工作区文件 |
| `write_file(path, content)` | 写工作区文件 |
| `list_files(dir)` | 列目录 |
| `run_command(command, timeout?)` | 工作区内执行 shell（装依赖 / 起服务 / 跑测试），输出截断回喂 |
| `http_request(method, url, body?)` | 接口测试 |
| `finish(result_json)` | 显式结束循环并提交产物（亦可以「无 tool_call 的最终回复」代替） |

路径越界（`..`、绝对路径逃逸工作区）一律拒绝。

### 工作区

- 每个 run 独立目录：`.sandbox-runs/{thread_id}/workspace/`；同一 run 内所有 agent 共享读写。
- 代码不再走「markdown 解析落盘」老路，由 agent 用 `write_file` 自行写入。
- run 结束后工作区保留，前端可浏览文件树、触发预览。

### 产物契约

agent 结束时必须提交符合角色 `output_schema` 的 JSON，写入 `state.node_outputs[node_id]`，作为条件边表达式的数据源。示例：

```jsonc
// CR 角色
{ "verdict": "pass" | "reject", "issues": [{ "file": "...", "line": 0, "severity": "...", "comment": "..." }], "summary": "..." }
// 测试角色
{ "verdict": "pass" | "fail", "checklist": [{ "item": "...", "status": "pass|fail", "evidence": "..." }], "bugs": [], "summary": "..." }
// 产品角色
{ "doc_path": "docs/prd.md", "acceptance_items": ["..."], "summary": "..." }
```

### 流式事件

loop 内每个事件（LLM token、tool_call 开始/结束、命令输出摘要）推送到前端聊天区，可看到「CR 正在读 src/api.ts」「测试正在执行 curl ...」。

### 容错

单步 LLM / 工具失败可重试；达 `max_steps` 未 finish → 节点失败，run 进入可人工干预状态（沿用现有 retry / resume 机制）。

## Roles

Role 是一等公民，存 `apps/api/.data/roles.json` + 代码 seed（启动时 upsert；内置只读，复制后可改，策略同模板）。

```ts
type RoleDef = {
  id: string;
  name: string;
  builtin: boolean;
  system_prompt: string;    // 人设 + 工作规范 + 产物契约说明
  output_schema: object;    // finish 提交 JSON 的 schema
  max_steps?: number;
};
```

### 预设角色

| 角色 | 职责 | 产物 |
|------|------|------|
| 产品经理 | 澄清并结构化需求，写 `docs/prd.md`，拆可验收条目 | `{ doc_path, acceptance_items[], summary }` |
| 前端开发 | 读 PRD + 接口契约实现前端，自验构建通过 | `{ files_changed[], build_status, summary }` |
| 后端开发 | 读 PRD 设计并实现 API，写 `docs/api.md`，自验服务可起、接口冒烟通过 | `{ files_changed[], api_doc_path, endpoints[], summary }` |
| CR | 对照 PRD 与接口文档审代码（正确性 / 安全 / 规范），不改代码 | `{ verdict, issues[], summary }` |
| 测试 | 从 PRD 拆 checklist 写 `docs/checklist.md`，逐条执行验证（起服务、http_request 调接口、跑构建/测试命令），记录证据 | `{ verdict, checklist[], bugs[], summary }` |

契约衔接：后端先产出 `docs/api.md`，前端 task_template 引用它保证对齐；CR 与测试均以 PRD 为验收基准。模板内用占位符串联（如 `{node_outputs.backend_1.api_doc_path}`）。

自定义角色：前端角色管理页（列表 + 编辑器），内置角色只能复制后编辑；自定义角色在 agent 节点下拉里可选。

## HITL

- 执行即 `interrupt()`，payload = `title / summary_fields[] / options[]`；`summary_fields` 引用状态字段，前端渲染审批卡片。
- 用户选择写入 `state.hitl = { node_id, action, message }`；出边用条件表达式（如 `hitl.last_action == 'approve'`）判断走向。
- HITL 不再内置 alignment / design_approval 等业务 kind，无节点内部分发硬编码；options 完全由模板配置。

## Compiler & Validation

创建 run 时 fail-closed 校验：

1. 恰好一个 start，至少一个 end；所有节点从 start 可达。
2. 每个节点的出边：条件边之外恰好一条 default。
3. 表达式 `left` 路径在白名单内、引用的 node_id 存在。
4. 回头边必须有 `max_iterations` 兜底路径。

校验失败返回结构化错误（node/edge id），前端画布高亮。

## Data Model

```ts
type NodeType = 'start' | 'end' | 'agent' | 'hitl';

type AgentNodeData = { role_id: string; task_template: string; max_steps?: number };
type HitlNodeData  = { title: string; options: string[]; summary_fields: string[] };

WorkflowState = {
  user_request: string;
  node_outputs: Record<string, unknown>;  // agent 产物 + 条件表达式数据源
  hitl?: { node_id: string; action: string; message: string };
  loop_counts: Record<string, number>;
  workspace_dir: string;                  // .sandbox-runs/{thread_id}/workspace
  messages: ...; phase: ...;              // 沿用现有
};
```

持久化：模板 / 快照 / checkpoint 机制沿用现有实现；新增 `roles.json`。

## API

| Method | Path | Notes |
|--------|------|-------|
| `GET/POST/PUT/DELETE` | `/roles` | 角色 CRUD；内置 403 |
| `POST` | `/roles/{id}/duplicate` | 复制为可编辑角色 |
| `GET` | `/threads/{id}/workspace/files` | 工作区文件树 |
| `GET` | `/threads/{id}/workspace/file?path=` | 读单个文件 |
| existing | `/workflows/**`, `/threads/**` | 全部沿用，编译器换成新 DSL |

## Frontend

- 画布节点库收窄为 4 种；agent 节点配置 = 选角色 + task_template；边配置面板 = 条件表单（left / op / value + 排序 + default 标记 + max_iterations）。
- 新增角色管理页（列表 + 编辑器：名称 / system prompt / output schema）。
- run 详情：聊天区流式展示工具事件；新增工作区文件树面板；预览能力保留（对工作区内前端项目跑现有 `build_preview`）。

## Migration

- 旧 DSL 不兼容，不做迁移。启动时 seed 新内置模板「研发交付流」。
- 旧「需求设计」模板标记归档：列表隐藏，历史 run 只读可查看，不可 resume。
- 删除 `graph/workflow.py`、`graph/nodes.py`、`graph/compiler.py` 中领域节点相关代码；保留 store / snapshot / thread / stream 基础设施。

### 内置模板「研发交付流」拓扑（示意，以 seed 为准）

```
start → 产品经理 → hitl(需求确认) ──打回──→ 产品经理（回头边）
           │ 通过
           ▼
        后端开发 → 前端开发 → CR ──reject──→ 对应开发（回头边）
                              │ pass
                              ▼
                            测试 ──fail──→ 对应开发（回头边）
                              │ pass
                              ▼
                             end
```

## Error Handling

- 编译期校验错误：结构化返回，画布高亮。
- agent loop 失败 / 超步数：节点失败 + retry/resume。
- 工具执行失败：结果回喂给 LLM 自行纠错，连续失败计入重试上限。
- 内置角色 / 模板写操作：403。

## Testing

- 单元：条件表达式求值（白名单 / 各 op）；编译器校验规则；回头边计数熔断；agent loop 工具协议（Mock LLM 下 finish / tool_call 序列）；路径越界拒绝。
- API：roles CRUD + 内置 403 + duplicate；新 DSL 创建 run 快照；HITL 条件路由。
- 端到端（Mock LLM）：内置模板跑通 产品 → 后端 → 前端 → CR → 测试 全链路，工作区落盘文件符合预期。

## Implementation Phases

1. RoleDef + roles.json + seed 5 角色；agent loop 执行器（工具协议 + 工作区 + 流式事件）。
2. 新 DSL 编译器（4 种节点 + 条件边 + 回头边计数）+ 校验；接入 run 创建 / 恢复。
3. 内置模板「研发交付流」seed + Mock LLM 端到端打通。
4. 前端：画布节点 / 边配置改版 + 角色管理页。
5. 前端：run 详情工具事件流 + 工作区文件树 + 预览接入。

## Success Criteria

- 用户可在画布上用 4 种节点编排角色流程，条件边控制 CR 打回 / 测试回退。
- 创建 run 后各 agent 在共享工作区协作产出完整前后端项目，前端可实时看到工具调用过程。
- 测试 agent 产出 checklist 并真实执行接口验证，结果决定流程走向。
- 用户可自定义新角色并在模板中使用。
