from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.agents.loop import MockAgentBackend, parse_action, run_agent_loop
from app.agents.tools import Workspace, execute_tool
from app.roles.seed import PM


def test_parse_action_tool_call():
    text = '```json\n{"type":"tool_call","tool":"read_file","args":{"path":"docs/prd.md"}}\n```'
    action = parse_action(text)
    assert action == {'type': 'tool_call', 'tool': 'read_file', 'args': {'path': 'docs/prd.md'}}


def test_parse_action_finish():
    action = parse_action('{"type":"finish","result":{"verdict":"pass"}}')
    assert action['type'] == 'finish'
    assert action['result'] == {'verdict': 'pass'}


def test_parse_action_plain_text_falls_back_to_message():
    action = parse_action('我先看一下需求')
    assert action['type'] == 'message'
    assert '需求' in action['content']


def test_mock_backend_executes_real_tools(tmp_path: Path):
    workspace = Workspace(tmp_path)
    backend = MockAgentBackend('product_manager')

    result = asyncio.run(run_agent_loop(
        role=PM,
        task_text='做一个待办应用',
        workspace=workspace,
        backend=backend,
        max_steps=5,
    ))

    assert result['doc_path'] == 'docs/prd.md'
    prd = tmp_path / 'docs' / 'prd.md'
    assert prd.exists()
    assert 'PRD' in prd.read_text(encoding='utf-8')


def test_mock_backend_emits_tool_events(tmp_path: Path):
    workspace = Workspace(tmp_path)
    backend = MockAgentBackend('backend_dev')
    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    result = asyncio.run(run_agent_loop(
        role=PM.model_copy(update={'id': 'backend_dev'}),
        task_text='实现 API',
        workspace=workspace,
        backend=backend,
        max_steps=10,
        emit=emit,
    ))

    kinds = [e['kind'] for e in events]
    assert kinds.count('tool_call') == 3
    assert kinds.count('tool_result') == 3
    assert kinds[-1] == 'finish'
    assert result['api_doc_path'] == 'docs/api.md'
    assert (tmp_path / 'src' / 'server.py').exists()


def test_loop_raises_after_max_steps(tmp_path: Path):
    workspace = Workspace(tmp_path)

    class NeverFinish:
        async def reply(self, messages):
            return json.dumps({'type': 'message', 'content': '还在想'})

    try:
        asyncio.run(run_agent_loop(
            role=PM,
            task_text='任务',
            workspace=workspace,
            backend=NeverFinish(),
            max_steps=2,
        ))
    except Exception as exc:
        assert '最大步数' in str(exc)
    else:
        raise AssertionError('应当因超过 max_steps 抛错')


def test_tool_path_escape_rejected(tmp_path: Path):
    workspace = Workspace(tmp_path)
    out = asyncio.run(execute_tool(workspace, 'write_file', {'path': '../evil.txt', 'content': 'x'}))
    assert out.startswith('[error]')
    out = asyncio.run(execute_tool(workspace, 'read_file', {'path': '/etc/passwd'}))
    assert out.startswith('[error]')
    assert not (tmp_path.parent / 'evil.txt').exists()


def test_tool_run_command(tmp_path: Path):
    workspace = Workspace(tmp_path)
    out = asyncio.run(execute_tool(workspace, 'run_command', {'command': 'echo hello'}))
    assert 'exit_code: 0' in out
    assert 'hello' in out


def test_finish_with_missing_files_is_rejected(tmp_path: Path):
    """Model claims docs/prd.md without writing it → loop pushes feedback and continues."""
    from app.agents.loop import find_missing_result_files

    workspace = Workspace(tmp_path / 'ws')
    workspace.root.mkdir(parents=True, exist_ok=True)
    (workspace.root / 'docs').mkdir()
    (workspace.root / 'docs' / 'prd.md').write_text('# PRD', encoding='utf-8')

    missing = find_missing_result_files(workspace, {
        'doc_path': 'docs/prd.md',
        'api_doc_path': 'docs/api.md',
        'summary': '已写入 docs/prd.md（不是纯路径，不应被校验）',
        'verdict': 'pass',
        'files_changed': ['src/server.py'],
    })
    assert missing == ['docs/api.md', 'src/server.py']


def test_finish_summary_claiming_missing_files_is_rejected(tmp_path: Path):
    from app.agents.loop import find_missing_result_files

    workspace = Workspace(tmp_path / 'ws')
    (workspace.root / 'src').mkdir(parents=True)
    (workspace.root / 'src' / 'app.js').write_text('console.log("ok")', encoding='utf-8')

    missing = find_missing_result_files(workspace, {
        'files_changed': ['src/app.js'],
        'summary': 'src/app.js 已写入，页面文件 src/index.html 与样式 ./src/style.css 也已存在。',
    })

    assert missing == []


def test_finish_reports_root_entry_path_mismatch(tmp_path: Path):
    from app.agents.loop import find_missing_result_files

    workspace = Workspace(tmp_path / 'ws')
    (workspace.root / 'index.html').write_text('<html />', encoding='utf-8')

    missing = find_missing_result_files(workspace, {
        'files_changed': ['src/index.html'],
    })

    assert missing == ['src/index.html（实际文件为 index.html，请修正 finish 路径或移动文件）']


def test_code_review_file_references_are_not_artifact_validation(tmp_path: Path):
    from app.agents.loop import find_missing_result_files

    workspace = Workspace(tmp_path / 'ws')
    (workspace.root / 'src').mkdir(parents=True)
    (workspace.root / 'src' / 'app.js').write_text('const ok = true;', encoding='utf-8')

    missing = find_missing_result_files(workspace, {
        'verdict': 'reject',
        'issues': [
            {'file': 'main.js', 'comment': 'main.js 不存在'},
            {'file': 'package.json', 'comment': 'package.json 缺失'},
        ],
        'summary': '审查了 main.js、package.json 和 src/main.js。',
    })

    assert missing == []


def test_loop_rejects_finish_claiming_missing_file_then_recovers(tmp_path: Path):
    """Backend first finishes with a phantom file, then writes it and finishes for real."""
    class HallucinatingBackend:
        def __init__(self) -> None:
            self._replies = [
                json.dumps({'type': 'finish', 'result': {'doc_path': 'docs/prd.md', 'summary': '写好了'}}),
                json.dumps({'type': 'tool_call', 'tool': 'write_file', 'args': {'path': 'docs/prd.md', 'content': '# PRD'}}),
                json.dumps({'type': 'finish', 'result': {'doc_path': 'docs/prd.md', 'summary': '写好了'}}),
            ]

        async def reply(self, messages: list[dict[str, str]]) -> str:
            return self._replies.pop(0)

    workspace = Workspace(tmp_path / 'ws')
    result = asyncio.run(run_agent_loop(
        role=PM,
        task_text='写 PRD',
        workspace=workspace,
        backend=HallucinatingBackend(),
    ))
    assert result['doc_path'] == 'docs/prd.md'
    assert (workspace.root / 'docs' / 'prd.md').is_file()


def test_loop_rejects_finish_after_failed_command_then_recovers(tmp_path: Path):
    class RepairingBackend:
        def __init__(self) -> None:
            self._replies = [
                json.dumps({
                    'type': 'tool_call',
                    'tool': 'run_command',
                    'args': {'command': 'python -c "raise RuntimeError(\'broken\')"'},
                }),
                json.dumps({'type': 'finish', 'result': {'summary': '错误地声称完成'}}),
                json.dumps({
                    'type': 'tool_call',
                    'tool': 'run_command',
                    'args': {'command': 'python -c "print(\'fixed\')"'},
                }),
                json.dumps({'type': 'finish', 'result': {'summary': '修复并验证完成'}}),
            ]

        async def reply(self, messages: list[dict[str, str]]) -> str:
            return self._replies.pop(0)

    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    result = asyncio.run(run_agent_loop(
        role=PM,
        task_text='修复代码',
        workspace=Workspace(tmp_path / 'ws'),
        backend=RepairingBackend(),
        max_steps=4,
        emit=emit,
    ))

    assert result['summary'] == '修复并验证完成'
    assert any('最近一次代码检查失败' in event.get('content', '') for event in events)
