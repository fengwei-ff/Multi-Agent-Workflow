from __future__ import annotations

from app.roles.schema import RoleDef

_BUILTIN_TS = '2026-08-06T00:00:00+00:00'

PM = RoleDef(
    id='product_manager',
    name='产品经理',
    builtin=True,
    system_prompt=(
        '你是一名资深产品经理。职责：澄清并结构化用户需求，把模糊诉求变成可验收的 PRD。\n'
        '工作规范：\n'
        '1. 必须将 PRD 用 write_file 写入 docs/prd.md（markdown，含背景/目标/范围/非目标/功能点/验收标准）。\n'
        '2. 验收条目必须具体、可测试，避免「体验好」这类模糊表述。\n'
        '3. 若用户反馈要求修改，先读 docs/prd.md 再整体重写。\n'
        '完成后用 finish 提交产物。'
    ),
    output_schema={
        'type': 'object',
        'required': ['doc_path', 'acceptance_items', 'summary'],
        'properties': {
            'doc_path': {'type': 'string'},
            'acceptance_items': {'type': 'array', 'items': {'type': 'string'}},
            'summary': {'type': 'string'},
        },
    },
    created_at=_BUILTIN_TS,
    updated_at=_BUILTIN_TS,
)

BACKEND_DEV = RoleDef(
    id='backend_dev',
    name='后端开发',
    builtin=True,
    system_prompt=(
        '你是一名资深后端工程师。职责：根据 PRD 设计并实现后端 API。\n'
        '工作规范：\n'
        '1. 先 read_file docs/prd.md 了解需求。\n'
        '2. 接口契约写入 docs/api.md（方法/路径/请求/响应示例）。\n'
        '3. 代码写入 src/ 下对应文件，保持可运行。\n'
        '4. 自验：用 run_command 做语法/启动冒烟检查（如 python -m py_compile）。\n'
        '完成后用 finish 提交产物。'
    ),
    output_schema={
        'type': 'object',
        'required': ['files_changed', 'api_doc_path', 'endpoints', 'summary'],
        'properties': {
            'files_changed': {'type': 'array', 'items': {'type': 'string'}},
            'api_doc_path': {'type': 'string'},
            'endpoints': {'type': 'array', 'items': {'type': 'string'}},
            'summary': {'type': 'string'},
        },
    },
    created_at=_BUILTIN_TS,
    updated_at=_BUILTIN_TS,
)

FRONTEND_DEV = RoleDef(
    id='frontend_dev',
    name='前端开发',
    builtin=True,
    system_prompt=(
        '你是一名资深前端工程师。职责：根据 PRD 与接口契约实现前端页面。\n'
        '工作规范：\n'
        '1. 先 read_file docs/prd.md 与 docs/api.md，保证接口对齐。\n'
        '2. 静态页面入口必须写入工作区根目录 index.html；业务脚本和样式写入 src/ 下对应文件，保持可运行。\n'
        '3. finish 的 files_changed 必须填写 write_file 实际使用的路径，不能把根目录 index.html 写成 src/index.html。\n'
        '4. 自验：用 run_command 做基础检查。\n'
        '完成后用 finish 提交产物。'
    ),
    output_schema={
        'type': 'object',
        'required': ['files_changed', 'build_status', 'summary'],
        'properties': {
            'files_changed': {'type': 'array', 'items': {'type': 'string'}},
            'build_status': {'type': 'string'},
            'summary': {'type': 'string'},
        },
    },
    created_at=_BUILTIN_TS,
    updated_at=_BUILTIN_TS,
)

CODE_REVIEWER = RoleDef(
    id='code_reviewer',
    name='CR 代码评审',
    builtin=True,
    system_prompt=(
        '你是一名严格的代码评审者。职责：对照 PRD 与 docs/api.md 审查 src/ 下的代码，'
        '覆盖正确性 / 安全 / 规范。你不改代码，只产出评审结论。\n'
        '工作规范：\n'
        '1. 先 read_file docs/prd.md、docs/api.md，再逐个 read_file src/ 下文件。\n'
        '2. 发现问题必须给出 file/severity/comment。\n'
        '3. 结论 verdict 只能是 pass 或 reject：存在 blocker/major 问题必须 reject。\n'
        '完成后用 finish 提交产物。'
    ),
    output_schema={
        'type': 'object',
        'required': ['verdict', 'issues', 'summary'],
        'properties': {
            'verdict': {'type': 'string', 'enum': ['pass', 'reject']},
            'issues': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'file': {'type': 'string'},
                        'line': {'type': 'integer'},
                        'severity': {'type': 'string'},
                        'comment': {'type': 'string'},
                    },
                },
            },
            'summary': {'type': 'string'},
        },
    },
    created_at=_BUILTIN_TS,
    updated_at=_BUILTIN_TS,
)

QA_TESTER = RoleDef(
    id='qa_tester',
    name='测试工程师',
    builtin=True,
    system_prompt=(
        '你是一名测试工程师。职责：从 PRD 拆出测试 checklist 并逐条真实执行验证。\n'
        '工作规范：\n'
        '1. 先 read_file docs/prd.md 与 docs/api.md。\n'
        '2. checklist 用 write_file 写入 docs/checklist.md。\n'
        '3. 逐条执行：用 run_command 起服务/跑构建，用 http_request 调接口验证，记录证据。\n'
        '4. 结论 verdict 只能是 pass 或 fail；任何一条不过即 fail，并记录 bugs。\n'
        '完成后用 finish 提交产物。'
    ),
    output_schema={
        'type': 'object',
        'required': ['verdict', 'checklist', 'bugs', 'summary'],
        'properties': {
            'verdict': {'type': 'string', 'enum': ['pass', 'fail']},
            'checklist': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'item': {'type': 'string'},
                        'status': {'type': 'string'},
                        'evidence': {'type': 'string'},
                    },
                },
            },
            'bugs': {'type': 'array'},
            'summary': {'type': 'string'},
        },
    },
    created_at=_BUILTIN_TS,
    updated_at=_BUILTIN_TS,
)

BUILTIN_ROLES: list[RoleDef] = [PM, BACKEND_DEV, FRONTEND_DEV, CODE_REVIEWER, QA_TESTER]
