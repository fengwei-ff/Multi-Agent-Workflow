# Changelog

本文件记录项目的重要变化。

## [Unreleased]

### Added

- 补充 GitHub 开源协作所需的许可证、环境变量模板和贡献指南。
- 持续完善可视化工作流、Agent Loop、HITL 和运行恢复能力。

## [0.1.0] - 2026-08-20

### Added

- 基于 React Flow 的可视化 Workflow DSL 编辑器。
- 基于 LangGraph 的动态工作流编译和运行时。
- 产品经理、后端开发、前端开发、CR 和测试工程师等内置角色。
- Agent 工具调用、工作区文件管理和结构化产物校验。
- HITL interrupt / resume、条件分支、循环上限和运行快照隔离。
- SQLite 元数据存储和 LangGraph SQLite checkpoint。
- SSE 流式事件、线程恢复、节点重试和静态预览。
- Mock LLM 模式和 API / 编译器 / Agent / 持久化测试。

### Known Limitations

- 当前没有用户认证、租户隔离、权限、配额和审计系统。
- Agent 命令执行仍运行在宿主机子进程中，不等同于容器级沙箱。
- API 和 Agent 执行尚未拆分为独立 Worker 与任务队列。
