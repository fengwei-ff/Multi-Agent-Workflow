# Multi-Agent-Workflow

可视化编排、可暂停、可恢复的多智能体工作流运行时。

Multi-Agent-Workflow 使用 React Flow 编辑工作流，用 LangGraph 执行工作流，把多个具备不同角色、工具和产物契约的 Agent 连接成可追踪的任务流。它适合用于需求分析、代码生成、代码评审、测试验证等需要多角色协作的研发场景。

> 当前项目处于 MVP / early-stage 阶段，重点验证“可视化工作流 DSL + LangGraph 编译执行 + Agent Loop + 人工确认”的完整闭环。

## Features

- **可视化工作流编辑器**：基于 React Flow 编辑节点、边、条件和循环上限。
- **动态 LangGraph 编译**：将工作流 DSL 编译为可执行的 LangGraph，而不是把流程硬编码在业务代码中。
- **角色化 Agent**：角色拥有 system prompt、产物契约和最大执行步数，可创建自定义角色。
- **真实工具调用**：Agent 可以读写工作区文件、列出文件、执行检查命令，并输出结构化产物。
- **人工确认（HITL）**：通过 LangGraph `interrupt` 暂停流程，审批后继续或打回修订。
- **条件分支与循环**：支持基于状态字段的条件边，以及带最大迭代次数的回边。
- **流式运行记录**：通过 SSE 展示节点、工具调用、工具结果、产物和错误事件。
- **运行快照隔离**：每次运行保存 workflow snapshot，模板修改不会改变历史运行。
- **工作区与预览**：每个线程拥有独立工作区，可查看文件并构建静态预览。
- **Mock LLM 模式**：没有配置 API Key 时可使用内置 Mock Agent 运行端到端流程。

## Demo Flow

内置工作流“研发交付流”默认包含：

```text
产品经理
   ↓
需求确认（人工审批）
   ├── revise → 产品经理重新修订
   └── approve
          ↓
      后端开发 → 前端开发 → CR 代码评审 → 测试工程师 → 完成
                         ↑             │
                         └─ reject ────┘
```

每个 Agent 在自己的线程工作区内产生文件和结构化结果，后续节点通过状态路径读取前序节点的产物。

## Architecture

```text
React + React Flow
        │ REST + SSE
        ▼
FastAPI API
        │
        ├── Workflow / Role / Thread API
        ├── SSE run / resume / retry
        └── Workspace / Preview API
        │
        ▼
Application Service
        │
        ├── workflow snapshot
        ├── state projection
        └── stream event serialization
        │
        ▼
Workflow DSL → Compiler → LangGraph Runtime
                              │
                              ├── SQLite checkpointer
                              ├── Agent Loop
                              ├── Role system prompt
                              └── Workspace tools
```

### Repository layout

```text
apps/api/                 FastAPI + LangGraph 后端
  app/graph/              工作流编译器和运行时
  app/workflows/          Workflow DSL、校验、存储和内置模板
  app/roles/              角色 schema、seed 和存储
  app/agents/             Agent Loop 和工具系统
  app/persistence.py      SQLite 元数据存储与旧 JSON 迁移
  tests/                  API、编译器、条件、Agent 和存储测试
apps/web/                 React + Vite 前端
  src/editor/             React Flow 工作流编辑器
  src/views/              工作流、运行详情、角色管理页面
packages/shared/          前后端共享的 TypeScript 类型和辅助函数
docs/superpowers/         设计文档和实现计划
```

## Requirements

- Node.js 22+
- pnpm 10
- Python 3.12+
- Conda（推荐环境名：`vEffect`）
- 可选：OpenAI-compatible LLM API

## Quick Start

### 1. Install frontend dependencies

```bash
pnpm install
```

### 2. Prepare Python environment

```bash
conda create -n vEffect python=3.12 -y
conda activate vEffect
pip install -r apps/api/requirements.txt
```

### 3. Configure environment variables

在项目根目录创建 `.env`。不配置 `OPENAI_API_KEY` 时，项目会自动使用 Mock LLM：

```dotenv
# LLM
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
USE_MOCK_LLM=false

# API
CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173

# Runtime
CHECKPOINT_DB_PATH=./.data/checkpoints.db
CHECKPOINT_ALLOW_MEMORY_FALLBACK=false
GRAPH_CACHE_SIZE=128

# Agent limits
AGENT_MAX_STEPS=30
AGENT_COMMAND_TIMEOUT=120
AGENT_COMMAND_OUTPUT_LIMIT=200000
AGENT_SHELL_ENABLED=true
AGENT_HTTP_ENABLED=false
```

### 4. Start the API

```bash
conda activate vEffect
pnpm dev:api
```

API: http://127.0.0.1:8000  
OpenAPI: http://127.0.0.1:8000/docs

### 5. Start the web app

另开一个终端：

```bash
pnpm dev:web
```

Web: http://127.0.0.1:5173

也可以分别执行：

```bash
cd apps/api && pnpm dev
cd apps/web && pnpm dev
```

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | empty | OpenAI-compatible API Key；为空时自动使用 Mock LLM |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | LLM 服务地址 |
| `OPENAI_MODEL` | `gpt-4o-mini` | 使用的模型名 |
| `USE_MOCK_LLM` | `false` | 强制使用 Mock LLM |
| `CORS_ORIGINS` | `http://localhost:5173` | 允许的前端来源，多个值用逗号分隔 |
| `CHECKPOINT_DB_PATH` | `./.data/checkpoints.db` | LangGraph checkpoint 数据库 |
| `CHECKPOINT_ALLOW_MEMORY_FALLBACK` | `false` | 是否允许 checkpoint 降级到内存；生产环境建议保持关闭 |
| `GRAPH_CACHE_SIZE` | `128` | 编译后工作流图缓存数量 |
| `AGENT_MAX_STEPS` | `30` | Agent 单节点最大循环步数 |
| `AGENT_COMMAND_TIMEOUT` | `120` | 工作区命令最大执行秒数 |
| `AGENT_COMMAND_OUTPUT_LIMIT` | `200000` | 命令输出最大字节数 |
| `AGENT_SHELL_ENABLED` | `true` | 是否允许 Agent 执行工作区命令 |
| `AGENT_HTTP_ENABLED` | `false` | 是否允许 Agent 发起 HTTP 请求 |

## Workflow DSL

工作流由节点和边组成。当前节点类型：

| Node | Purpose |
| --- | --- |
| `start` | 流程入口 |
| `agent` | 执行一个角色化 Agent |
| `hitl` | 暂停等待人工确认 |
| `end` | 流程结束 |

Agent 节点的核心配置示例：

```json
{
  "id": "backend",
  "type": "agent",
  "position": { "x": 640, "y": 120 },
  "data": {
    "role_id": "backend_dev",
    "task_template": "请根据 docs/prd.md 实现后端 API。",
    "max_steps": 30
  }
}
```

边可以配置条件和循环上限：

```json
{
  "id": "e_cr_reject",
  "source": "cr",
  "target": "backend",
  "condition": {
    "left": "node_outputs.cr.verdict",
    "op": "eq",
    "value": "reject"
  },
  "max_iterations": 3
}
```

支持的条件操作包括 `eq`、`neq`、`in`、`contains`、`gt`、`lt` 和 `exists`。

## Persistence

默认数据目录为 `apps/api/.data/`：

```text
apps/api/.data/metadata.db     工作流、角色、线程元数据
apps/api/.data/checkpoints.db  LangGraph checkpoint
```

旧版 `workflows.json`、`roles.json` 和 `threads.json` 会在首次读取时自动迁移到 SQLite。每个线程还会拥有独立工作区：

```text
.sandbox-runs/<thread_id>/workspace/
```

预览构建产物位于：

```text
.preview-runs/<preview_id>/
```

## API Overview

主要 API：

```text
GET    /health

GET    /workflows
POST   /workflows
GET    /workflows/{workflow_id}
PUT    /workflows/{workflow_id}
DELETE /workflows/{workflow_id}
POST   /workflows/{workflow_id}/duplicate
POST   /workflows/{workflow_id}/runs

GET    /roles
POST   /roles
PUT    /roles/{role_id}
DELETE /roles/{role_id}

GET    /threads
POST   /threads
GET    /threads/{thread_id}
DELETE /threads/{thread_id}
POST   /threads/{thread_id}/runs
POST   /threads/{thread_id}/resume
POST   /threads/{thread_id}/retry
POST   /threads/{thread_id}/preview
```

完整请求和响应结构请查看启动后的 `/docs`。

## Development

运行 Python 测试：

```bash
conda activate vEffect
PYTHONPATH=apps/api pytest -q apps/api/tests
```

运行前端和共享包检查：

```bash
pnpm lint
pnpm build
```

当前测试覆盖工作流校验、条件路由、循环、编译器、HITL、Agent Loop、文件产物校验、线程快照隔离、SQLite 并发写入和 API CRUD。

## Security Notes

这个项目会让 Agent 在工作区内写文件并执行命令，因此不应直接暴露给不可信用户：

- 当前命令执行仍是宿主机子进程，不是容器或 microVM 级沙箱。
- `AGENT_HTTP_ENABLED` 默认关闭；开启前应配置网络隔离和访问控制。
- 当前项目没有用户认证、租户隔离、配额和权限系统。
- `AGENT_SHELL_ENABLED`、命令超时和输出上限只能降低风险，不能替代真正的隔离运行时。
- 生产部署建议使用独立 Worker、容器化执行环境、数据库备份和审计日志。

## Roadmap

- [x] Workflow DSL 与 React Flow 编辑器
- [x] LangGraph 动态编译和 SQLite checkpoint
- [x] Agent Loop、角色系统和结构化产物
- [x] HITL interrupt / resume
- [x] 条件分支、循环上限和运行快照
- [ ] OpenAPI 自动生成前端类型和 API Client
- [ ] Workflow version / migration 机制
- [ ] 独立 Worker 和任务队列
- [ ] 容器级代码执行沙箱
- [ ] 用户、租户、权限、配额和审计
- [ ] 插件化工具与 Agent 能力授权

## Contributing

欢迎提交 Issue、讨论工作流 DSL、Agent 工具治理、执行可靠性和可观测性方面的想法。

建议的贡献流程：

1. Fork 项目并创建 feature branch。
2. 为行为变更补充 API 或运行时测试。
3. 执行 `PYTHONPATH=apps/api pytest -q apps/api/tests`、`pnpm lint` 和 `pnpm build`。
4. 提交 Pull Request，说明设计取舍和兼容性影响。

## License

本项目采用 [MIT License](LICENSE) 开源。第三方依赖仍受其各自许可证约束；使用生成代码或接入外部模型服务时，请遵守对应服务和模型的使用条款。
