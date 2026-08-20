from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.sandbox import SANDBOX_ROOT

logger = logging.getLogger('workflow_agent.agents.tools')

MAX_OUTPUT_CHARS = 4000
MAX_FILE_CHARS = 20000

TOOL_USAGE_DOC = """你可以通过输出 JSON 动作来使用工具。每一步必须输出且只输出一个 JSON 对象（可用 ```json 包裹），格式三选一：
1. 调用工具: {"type":"tool_call","tool":"<工具名>","args":{...}}
2. 结束并提交产物: {"type":"finish","result":{...符合产物契约的 JSON...}}
3. 说明情况(不结束): {"type":"message","content":"..."}

可用工具：
- read_file(path) — 读取工作区文件内容
- write_file(path, content) — 写入工作区文件（自动创建目录）
- list_files(dir) — 列出目录下文件（dir 为空则列根目录）
- run_command(command, timeout?) — 在工作区执行 shell 命令，返回输出（截断）
- http_request(method, url, body?) — 发起 HTTP 请求做接口测试，返回状态码与响应体

工作区路径一律使用相对路径（如 docs/prd.md），禁止 .. 与绝对路径。
前端静态项目约定：项目入口文件 `index.html` 放在工作区根目录；业务 JavaScript / TypeScript / CSS 文件放在 `src/` 目录。finish 中的路径必须与 write_file 的真实路径完全一致。
完成所有工作后必须用 finish 提交产物，产物必须是符合契约的 JSON。

重要纪律：
- 禁止在没有实际调用 write_file 的情况下声称文件已写入。finish 的 result 中提到的每个文件路径，系统都会校验其真实存在；不存在会被打回并要求你补写。
- run_command 返回非零 exit_code 或超时时禁止 finish；必须根据错误修正代码并重新检查成功。
- 先调用工具完成真实工作，再 finish。不要一步到位直接 finish。"""


def workspace_dir_for(thread_id: str) -> Path:
    return SANDBOX_ROOT / thread_id / 'workspace'


class Workspace:
    """Per-run shared workspace; all agent tools operate relative to its root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, rel_path: str) -> Path:
        normalized = rel_path.replace('\\', '/').strip()
        if not normalized or normalized.startswith('/') or '..' in Path(normalized).parts:
            raise ValueError(f'非法路径（越界或绝对路径）: {rel_path}')
        target = (self.root / normalized).resolve()
        if not target.is_relative_to(self.root.resolve()):
            raise ValueError(f'非法路径（逃逸工作区）: {rel_path}')
        return target

    async def read_file(self, path: str) -> str:
        target = self._resolve(path)
        if not target.exists() or not target.is_file():
            return f'[error] 文件不存在: {path}'
        content = target.read_text(encoding='utf-8', errors='replace')
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS] + f'\n...[已截断，共 {len(content)} 字符]'
        return content

    async def write_file(self, path: str, content: str) -> str:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return f'[ok] 已写入 {path} ({len(content)} 字符)'

    async def list_files(self, dir: str = '') -> str:
        base = self._resolve(dir) if dir else self.root
        if not base.exists():
            return f'[error] 目录不存在: {dir or "."}'
        entries: list[str] = []
        for item in sorted(base.rglob('*')):
            if item.is_file():
                entries.append(str(item.relative_to(self.root)))
            if len(entries) >= 200:
                entries.append('...[已截断]')
                break
        return '\n'.join(entries) if entries else '(空目录)'

    async def run_command(self, command: str, timeout: int = 120) -> str:
        settings = get_settings()
        if not settings.agent_shell_enabled:
            return '[error] Shell 工具已被服务端禁用'
        effective_timeout = min(max(1, timeout), max(1, settings.agent_command_timeout))
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=str(self.root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=effective_timeout)
            except TimeoutError:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.communicate()
                return f'[error] 命令超时（{effective_timeout}s）: {command}'
        except Exception as exc:
            return f'[error] 命令执行失败: {exc}'
        output = stdout.decode('utf-8', errors='replace')
        exit_code = process.returncode or 0
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + f'\n...[已截断，共 {len(output)} 字符]'
        return f'exit_code: {exit_code}\n{output.strip() or "(无输出)"}'

    async def http_request(self, method: str, url: str, body: Any = None) -> str:
        if not get_settings().agent_http_enabled:
            return '[error] HTTP 工具已被服务端禁用'
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method.upper(),
                    url,
                    json=body if body is not None else None,
                )
            text = response.text
            if len(text) > MAX_OUTPUT_CHARS:
                text = text[:MAX_OUTPUT_CHARS] + f'\n...[已截断，共 {len(text)} 字符]'
            return f'status: {response.status_code}\n{text}'
        except Exception as exc:
            return f'[error] HTTP 请求失败: {exc}'


async def execute_tool(workspace: Workspace, tool: str, args: dict[str, Any]) -> str:
    """Dispatch a tool call; never raises — errors are returned as text for the LLM."""
    try:
        if tool == 'read_file':
            return await workspace.read_file(str(args.get('path') or ''))
        if tool == 'write_file':
            return await workspace.write_file(
                str(args.get('path') or ''),
                str(args.get('content') or ''),
            )
        if tool == 'list_files':
            return await workspace.list_files(str(args.get('dir') or ''))
        if tool == 'run_command':
            return await workspace.run_command(
                str(args.get('command') or ''),
                timeout=int(args.get('timeout') or 120),
            )
        if tool == 'http_request':
            return await workspace.http_request(
                str(args.get('method') or 'GET'),
                str(args.get('url') or ''),
                body=args.get('body'),
            )
        return f'[error] 未知工具: {tool}'
    except ValueError as exc:
        return f'[error] {exc}'
    except Exception as exc:
        logger.exception('Tool execution failed: %s', tool)
        return f'[error] 工具执行异常: {exc}'
