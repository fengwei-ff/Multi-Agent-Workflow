# Contributing to Multi-Agent Workflow

感谢你对 Multi-Agent Workflow 的兴趣。项目目前处于 MVP 阶段，欢迎围绕工作流 DSL、LangGraph 编译执行、Agent 工具治理、HITL 和可观测性提交贡献。

## Before You Start

- 先阅读 `README.md`，了解架构、启动方式和安全边界。
- 大功能或架构调整请先创建 Issue，说明问题、方案和兼容性影响。
- 不要在 Issue、Pull Request 或测试数据中提交 API Key、个人信息或真实业务代码。

## Development Setup

```bash
pnpm install

conda create -n vEffect python=3.12 -y
conda activate vEffect
pip install -r apps/api/requirements.txt
cp .env.example .env
```

默认可以使用 Mock LLM 开发，不需要配置外部模型服务。

## Workflow

1. Fork 项目并创建 feature branch。
2. 保持修改范围聚焦，避免顺带重构无关代码。
3. 为行为变化补充或更新测试。
4. 在本地执行完整检查。
5. 提交 Pull Request，描述背景、实现方式、测试结果和已知限制。

## Validation

提交前运行：

```bash
conda activate vEffect
PYTHONPATH=apps/api pytest -q apps/api/tests
pnpm lint
pnpm build
```

如果修改了 Agent、工作流编译器、状态持久化或 SSE 事件，请优先补充对应的 API / runtime 测试。

## Code Guidelines

- 优先修复根因，不使用只针对单个截图或单个模型输出的临时判断。
- 保持 Workflow DSL、Pydantic schema 和 TypeScript 类型之间的一致性。
- 新增 Agent 工具时明确路径、权限、超时、输出限制和失败行为。
- 不要把宿主机密钥、绝对路径或个人环境配置写入代码。
- 生产安全相关改动必须同时更新 `README.md` 的 Security Notes。
- 提交信息建议使用简洁的动词开头，例如 `Fix checkpoint recovery` 或 `Add workflow validation`。

## Pull Requests

Pull Request 建议包含：

- 变更背景和目标；
- 主要设计取舍；
- 影响的 API、配置或数据格式；
- 测试命令和结果；
- 截图或录屏（如果涉及前端交互）；
- 数据迁移、回滚或兼容性说明。

Maintainers may request changes to keep the public API, workflow schema and runtime behavior stable.
