from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable, Protocol

from app.agents.tools import TOOL_USAGE_DOC, Workspace, execute_tool
from app.config import get_settings
from app.llm import get_llm
from app.roles.schema import RoleDef

logger = logging.getLogger('workflow_agent.agents.loop')

Emit = Callable[[dict[str, Any]], Awaitable[None]]


class AgentLoopError(Exception):
    pass


class AgentBackend(Protocol):
    async def reply(self, messages: list[dict[str, str]]) -> str:
        ...


class ChatAgentBackend:
    """Real LLM backend: JSON-action tool protocol over plain chat completions."""

    async def reply(self, messages: list[dict[str, str]]) -> str:
        return await get_llm().achat(messages)


# ---------------------------------------------------------------------------
# Mock backend: canned action scripts per role. Tool calls are executed for
# real by the loop, so Mock-LLM e2e runs produce real workspace files.
# ---------------------------------------------------------------------------

MOCK_SCRIPTS: dict[str, list[dict[str, Any]]] = {
    'product_manager': [
        {
            'type': 'tool_call',
            'tool': 'write_file',
            'args': {
                'path': 'docs/prd.md',
                'content': (
                    '# PRD\n\n## 背景\n用户需求见任务描述。\n\n'
                    '## 功能点\n1. 待办事项的增删改查\n2. 前端展示与交互\n\n'
                    '## 验收标准\n- API 可增删改查\n- 页面可正常打开并调用 API\n'
                ),
            },
        },
        {
            'type': 'finish',
            'result': {
                'doc_path': 'docs/prd.md',
                'acceptance_items': ['API 可增删改查', '页面可正常打开并调用 API'],
                'summary': 'PRD 已写入 docs/prd.md（mock）',
            },
        },
    ],
    'backend_dev': [
        {
            'type': 'tool_call',
            'tool': 'write_file',
            'args': {
                'path': 'docs/api.md',
                'content': (
                    '# API 契约\n\n'
                    '- GET /todos → [{id, title, done}]\n'
                    '- POST /todos {title} → {id, title, done}\n'
                    '- DELETE /todos/{id} → 204\n'
                ),
            },
        },
        {
            'type': 'tool_call',
            'tool': 'write_file',
            'args': {
                'path': 'src/server.py',
                'content': (
                    'from http.server import BaseHTTPRequestHandler, HTTPServer\n'
                    'import json\n\n'
                    'TODOS = []\n\n'
                    'class Handler(BaseHTTPRequestHandler):\n'
                    '    def do_GET(self):\n'
                    '        body = json.dumps(TODOS).encode()\n'
                    '        self.send_response(200)\n'
                    '        self.send_header("Content-Type", "application/json")\n'
                    '        self.end_headers()\n'
                    '        self.wfile.write(body)\n\n'
                    'if __name__ == "__main__":\n'
                    '    HTTPServer(("127.0.0.1", 8901), Handler).serve_forever()\n'
                ),
            },
        },
        {
            'type': 'tool_call',
            'tool': 'run_command',
            'args': {'command': 'python -m py_compile src/server.py'},
        },
        {
            'type': 'finish',
            'result': {
                'files_changed': ['docs/api.md', 'src/server.py'],
                'api_doc_path': 'docs/api.md',
                'endpoints': ['GET /todos', 'POST /todos', 'DELETE /todos/{id}'],
                'summary': '后端 API 已实现并通过语法检查（mock）',
            },
        },
    ],
    'frontend_dev': [
        {
            'type': 'tool_call',
            'tool': 'read_file',
            'args': {'path': 'docs/api.md'},
        },
        {
            'type': 'tool_call',
            'tool': 'write_file',
            'args': {
                'path': 'src/index.html',
                'content': (
                    '<!doctype html>\n<html lang="zh-CN">\n<head>\n'
                    '<meta charset="UTF-8" />\n<title>待办</title>\n</head>\n'
                    '<body>\n<h1>待办事项</h1>\n<ul id="todos"></ul>\n'
                    "<script>fetch('http://127.0.0.1:8901/todos').then(r=>r.json())"
                    '.then(list=>{document.getElementById("todos").innerHTML='
                    'list.map(t=>`<li>${t.title}</li>`).join("")})</script>\n'
                    '</body>\n</html>\n'
                ),
            },
        },
        {
            'type': 'finish',
            'result': {
                'files_changed': ['src/index.html'],
                'build_status': 'static-ok',
                'summary': '前端页面已实现，接口与 docs/api.md 对齐（mock）',
            },
        },
    ],
    'code_reviewer': [
        {
            'type': 'tool_call',
            'tool': 'list_files',
            'args': {'dir': 'src'},
        },
        {
            'type': 'tool_call',
            'tool': 'read_file',
            'args': {'path': 'src/server.py'},
        },
        {
            'type': 'finish',
            'result': {
                'verdict': 'pass',
                'issues': [],
                'summary': '代码符合 PRD 与接口契约，无 blocker 问题（mock）',
            },
        },
    ],
    'qa_tester': [
        {
            'type': 'tool_call',
            'tool': 'write_file',
            'args': {
                'path': 'docs/checklist.md',
                'content': (
                    '# 测试 Checklist\n\n'
                    '- [x] 后端代码语法检查通过\n'
                    '- [x] 前端页面文件存在\n'
                ),
            },
        },
        {
            'type': 'tool_call',
            'tool': 'run_command',
            'args': {'command': 'python -m py_compile src/server.py && ls src'},
        },
        {
            'type': 'finish',
            'result': {
                'verdict': 'pass',
                'checklist': [
                    {'item': '后端代码语法检查通过', 'status': 'pass', 'evidence': 'py_compile exit 0'},
                    {'item': '前端页面文件存在', 'status': 'pass', 'evidence': 'src/index.html 存在'},
                ],
                'bugs': [],
                'summary': '全部检查项通过（mock）',
            },
        },
    ],
}


class MockAgentBackend:
    """Scripted backend for deterministic e2e tests; tools still execute for real."""

    def __init__(self, role_id: str) -> None:
        script = MOCK_SCRIPTS.get(role_id) or [
            {'type': 'finish', 'result': {'summary': 'mock 角色无脚本，直接结束'}}
        ]
        self._queue = list(script)

    async def reply(self, messages: list[dict[str, str]]) -> str:
        if not self._queue:
            return json.dumps(
                {'type': 'finish', 'result': {'summary': 'mock 脚本已耗尽，强制结束'}},
                ensure_ascii=False,
            )
        return json.dumps(self._queue.pop(0), ensure_ascii=False)


def default_backend(role_id: str) -> AgentBackend:
    if get_settings().should_use_mock:
        return MockAgentBackend(role_id)
    return ChatAgentBackend()


# ---------------------------------------------------------------------------
# Action parsing + loop
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict[str, Any] | None:
    content = text.strip()
    if content.startswith('```'):
        lines = content.split('\n')[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        content = '\n'.join(lines).strip()
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start = content.find('{')
        end = content.rfind('}')
        if start >= 0 and end > start:
            try:
                parsed = json.loads(content[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
        return None


def parse_action(text: str) -> dict[str, Any]:
    """Parse LLM output into {type: tool_call|finish|message}. Falls back to message."""
    parsed = _extract_json(text)
    if parsed is None:
        return {'type': 'message', 'content': text.strip()}
    action_type = parsed.get('type')
    if action_type == 'tool_call' and isinstance(parsed.get('tool'), str):
        args = parsed.get('args')
        return {
            'type': 'tool_call',
            'tool': parsed['tool'],
            'args': args if isinstance(args, dict) else {},
        }
    if action_type == 'finish':
        result = parsed.get('result')
        return {'type': 'finish', 'result': result if isinstance(result, dict) else {'value': result}}
    content = parsed.get('content')
    return {'type': 'message', 'content': str(content) if content is not None else text.strip()}


async def _noop_emit(_event: dict[str, Any]) -> None:
    return None


_PATH_LIKE = re.compile(
    r'^[\w][\w./-]*\.(md|markdown|py|ts|tsx|js|jsx|html|htm|css|json|txt|yaml|yml|sql|sh)$'
)
_PATH_TOKEN = re.compile(
    r'(?<![\w./-])(?:\./)?[\w][\w./-]*\.'
    r'(?:md|markdown|py|ts|tsx|js|jsx|html|htm|css|json|txt|yaml|yml|sql|sh)'
    r'(?![\w.-])'
)


def _iter_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _iter_strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _iter_strings(item)]
    return []


def find_missing_result_files(workspace: Workspace, result: dict[str, Any]) -> list[str]:
    """Declared artifact paths in a finish result that don't exist in the workspace.

    Review fields such as ``issues[].file`` and free-form summaries are excluded:
    they describe files being inspected, not files produced by the current node.
    """
    missing: list[str] = []
    declared_values: list[Any] = []
    for key, value in result.items():
        if key == 'files_changed' or key == 'path' or key.endswith('_path'):
            declared_values.append(value)

    for text in _iter_strings(declared_values):
        stripped = text.strip()
        candidates = [stripped] if _PATH_LIKE.fullmatch(stripped) else _PATH_TOKEN.findall(text)
        for candidate in candidates:
            normalized = candidate.removeprefix('./')
            try:
                target = workspace._resolve(normalized)
            except ValueError:
                continue
            if not target.is_file():
                aliases = []
                if normalized.startswith('src/'):
                    aliases.append(normalized.removeprefix('src/'))
                else:
                    aliases.append(f'src/{normalized}')
                existing_alias = next(
                    (alias for alias in aliases if workspace._resolve(alias).is_file()),
                    None,
                )
                if existing_alias:
                    missing.append(
                        f'{normalized}（实际文件为 {existing_alias}，请修正 finish 路径或移动文件）'
                    )
                else:
                    missing.append(normalized)
    return sorted(set(missing))


async def run_agent_loop(
    *,
    role: RoleDef,
    task_text: str,
    workspace: Workspace,
    backend: AgentBackend | None = None,
    max_steps: int | None = None,
    emit: Emit = _noop_emit,
) -> dict[str, Any]:
    """Run the tool-using agent loop for one role. Returns the finished result dict."""
    settings = get_settings()
    backend = backend or default_backend(role.id)
    limit = max_steps or role.max_steps or settings.agent_max_steps

    contract = json.dumps(role.output_schema, ensure_ascii=False) if role.output_schema else '{}'
    system_prompt = (
        f'{role.system_prompt}\n\n'
        f'---\n{TOOL_USAGE_DOC}\n\n'
        f'产物契约（finish 的 result 必须符合）:\n{contract}'
    )
    messages: list[dict[str, str]] = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': task_text},
    ]
    failed_command_result: str | None = None

    for step in range(1, limit + 1):
        text = await backend.reply(messages)
        action = parse_action(text)
        messages.append({'role': 'assistant', 'content': text})

        if action['type'] == 'finish':
            if failed_command_result is not None:
                await emit({
                    'kind': 'message',
                    'step': step,
                    'content': '最近一次代码检查失败，必须修复后重新执行检查。',
                })
                messages.append({
                    'role': 'user',
                    'content': (
                        '不能 finish：最近一次 run_command 检查失败。请根据错误修改代码，'
                        f'然后重新运行检查，确认 exit_code 为 0 后再 finish。\n错误结果：\n{failed_command_result}'
                    ),
                })
                continue
            missing = find_missing_result_files(workspace, action['result'])
            if missing:
                logger.warning('角色 %s finish 引用了不存在的文件: %s', role.id, missing)
                await emit({
                    'kind': 'message',
                    'step': step,
                    'content': f'产物校验未通过：以下文件不存在于工作区 {missing}',
                })
                messages.append({
                    'role': 'user',
                    'content': (
                        f'校验未通过：你在 finish 的 result 中提到了这些文件，但它们并不存在于工作区: '
                        f'{missing}\n请先用 write_file 真实写入这些文件，然后重新 finish。'
                    ),
                })
                continue
            await emit({'kind': 'finish', 'step': step, 'result': action['result']})
            return action['result']

        if action['type'] == 'tool_call':
            tool = action['tool']
            args = action['args']
            await emit({'kind': 'tool_call', 'step': step, 'tool': tool, 'args': args})
            result = await execute_tool(workspace, tool, args)
            if tool == 'run_command':
                failed_command_result = None if result.startswith('exit_code: 0') else result
            await emit({'kind': 'tool_result', 'step': step, 'tool': tool, 'result': result})
            messages.append({
                'role': 'user',
                'content': f'工具 {tool} 执行结果:\n{result}\n\n继续下一步，或完成后 finish。',
            })
            continue

        # message: surface to stream and nudge the model to continue
        await emit({'kind': 'message', 'step': step, 'content': action['content']})
        messages.append({
            'role': 'user',
            'content': '请继续。记住每步只输出一个 JSON 动作，完成工作后用 finish 提交产物。',
        })

    raise AgentLoopError(f'角色 {role.name} 达到最大步数 {limit} 仍未提交产物')
