from __future__ import annotations

import asyncio
import os
import signal
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
SANDBOX_ROOT = WORKSPACE_ROOT / '.sandbox-runs'
PREVIEW_ROOT = WORKSPACE_ROOT / '.preview-runs'


@dataclass
class ParsedFile:
    path: str
    language: str
    content: str


@dataclass
class PreviewBuildResult:
    preview_id: str
    entry_dir: Path
    logs: str


def _normalize_path(raw_path: str) -> str | None:
    normalized = raw_path.replace('\\', '/').strip().lstrip('./')
    if not normalized or normalized.startswith('/') or '..' in Path(normalized).parts:
        return None
    return normalized


def _rewrite_preview_asset_paths(entry_dir: Path) -> None:
    index_file = entry_dir / 'index.html'
    if not index_file.exists():
        return
    html = index_file.read_text(encoding='utf-8')
    html = html.replace('src="/assets/', 'src="./assets/')
    html = html.replace("src='/assets/", "src='./assets/")
    html = html.replace('href="/assets/', 'href="./assets/')
    html = html.replace("href='/assets/", "href='./assets/")
    index_file.write_text(html, encoding='utf-8')


def _patch_preview_project(project_dir: Path) -> list[str]:
    """Fix common LLM-generated runtime bugs before preview build."""
    notes: list[str] = []
    source_paths = [*project_dir.rglob('*.tsx'), *project_dir.rglob('*.js')]
    for path in source_paths:
        original = path.read_text(encoding='utf-8')
        updated = original

        # Empty object is truthy; cleanup must clear to null, not {}.
        if 'dispatch(setCurrentDish({} as any))' in updated:
            if 'clearCurrentDish' not in updated:
                updated = updated.replace(
                    'setCurrentDish, toggleFavoriteLocal, setComments, appendComment, setNickname',
                    'setCurrentDish, clearCurrentDish, toggleFavoriteLocal, setComments, appendComment, setNickname',
                )
            updated = updated.replace(
                'dispatch(setCurrentDish({} as any))',
                'dispatch(clearCurrentDish())',
            )

        # Guard incomplete dish objects before ingredients/steps access.
        if 'dish.ingredients.filter' in updated:
            updated = updated.replace('if (!dish) {', 'if (!dish?.id || !dish?.ingredients) {')
            updated = updated.replace(
                'dish.ingredients.filter',
                '(dish.ingredients ?? []).filter',
            )
            updated = updated.replace(
                'dish.steps.map',
                '(dish.steps ?? []).map',
            )

        # antd-mobile Rate uses readOnly, not disabled.
        updated = updated.replace(
            '<Rate value={comment.rating} disabled />',
            '<Rate value={comment.rating} readOnly />',
        )

        # Dialog.prompt may not exist; fall back to window.prompt.
        if 'Dialog.prompt' in updated:
            updated = updated.replace(
                'const result = await Dialog.prompt({\n'
                "        title: '请输入昵称',\n"
                "        defaultValue: '',\n"
                "        placeholderText: '昵称将用于展示',\n"
                '      })',
                "const result = window.prompt('请输入昵称', '')",
            )

        if (
            "editBtn.addEventListener('click', () => {\n"
            '        editingId = null;\n'
            '        render();\n'
            '      });'
        ) in updated:
            updated = updated.replace(
                "editBtn.addEventListener('click', () => {\n"
                '        editingId = null;\n'
                '        render();\n'
                '      });',
                "editBtn.addEventListener('click', () => {\n"
                '        editingId = todo.id;\n'
                '        render();\n'
                '      });',
            )
            notes.append(f'已修复编辑按钮状态：{path.relative_to(project_dir)}')

        if updated != original:
            path.write_text(updated, encoding='utf-8')
            notes.append(f'已修复运行时风险：{path.relative_to(project_dir)}')
    return notes


def parse_generated_code(markdown: str) -> list[ParsedFile]:
    lines = markdown.splitlines()
    files: list[ParsedFile] = []
    current_path: str | None = None
    current_language = ''
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        nonlocal current_path, current_language, buffer, in_fence
        if current_path:
            files.append(
                ParsedFile(
                    path=current_path,
                    language=current_language,
                    content='\n'.join(buffer),
                )
            )
        current_path = None
        current_language = ''
        buffer = []
        in_fence = False

    for line in lines:
        stripped = line.strip()
        if not in_fence:
            if stripped.startswith('## '):
                flush()
                current_path = _normalize_path(stripped[3:].strip())
                continue
            if stripped.startswith('```'):
                token = stripped[3:].strip()
                if current_path:
                    current_language = token
                    in_fence = True
                    continue
                guessed_path = _normalize_path(token)
                if guessed_path:
                    flush()
                    current_path = guessed_path
                    current_language = ''
                    in_fence = True
                continue
            continue

        if stripped == '```':
            flush()
            continue
        buffer.append(line)

    if current_path and buffer:
        flush()
    return files


def materialize_generated_code(markdown: str) -> tuple[Path, list[ParsedFile]]:
    parsed = parse_generated_code(markdown)
    run_dir = SANDBOX_ROOT / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=True)
    files_dir = run_dir / 'files'
    files_dir.mkdir(parents=True, exist_ok=True)

    if not parsed:
        fallback = files_dir / 'generated.md'
        fallback.write_text(markdown, encoding='utf-8')
        return run_dir, []

    for item in parsed:
        target = files_dir / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding='utf-8')

    return run_dir, parsed


async def _run_command(command: list[str], cwd: Path) -> tuple[int, str]:
    settings = get_settings()
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(),
            timeout=max(1, settings.agent_command_timeout),
        )
        exit_code = process.returncode or 0
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, _ = await process.communicate()
        exit_code = 124
        stdout += f'\nCommand timed out after {settings.agent_command_timeout}s.'.encode()

    output_limit = max(1_000, settings.agent_command_output_limit)
    truncated = len(stdout) > output_limit
    stdout = stdout[:output_limit]
    output = stdout.decode('utf-8', errors='replace')
    if truncated:
        output += f'\nOutput truncated at {output_limit} bytes.'
    return exit_code, output


async def run_sandbox_checks(run_dir: Path, files: list[ParsedFile]) -> str:
    if not files:
        return f'沙箱未执行：未能从生成结果中解析出文件。原始输出保存在 `{run_dir / "files" / "generated.md"}`。'

    report_lines = [f'沙箱目录：`{run_dir}`', '', '## 落盘文件']
    for item in files:
        report_lines.append(f'- `{item.path}`')

    python_files = [str((run_dir / 'files' / item.path).resolve()) for item in files if item.path.endswith('.py')]
    ts_like_files = [
        str((run_dir / 'files' / item.path).resolve())
        for item in files
        if item.path.endswith(('.ts', '.tsx', '.js', '.jsx'))
    ]

    if python_files:
        exit_code, output = await _run_command(
            ['python', '-m', 'py_compile', *python_files],
            cwd=WORKSPACE_ROOT,
        )
        report_lines.extend([
            '',
            '## Python 语法检查',
            f'- exit_code: {exit_code}',
            '```text',
            (output or 'ok').strip(),
            '```',
        ])

    if ts_like_files:
        exit_code, output = await _run_command(
            [
                'pnpm',
                'exec',
                'tsc',
                '--noEmit',
                '--skipLibCheck',
                '--jsx',
                'react-jsx',
                '--module',
                'esnext',
                '--target',
                'es2022',
                '--moduleResolution',
                'bundler',
                *ts_like_files,
            ],
            cwd=WORKSPACE_ROOT,
        )
        report_lines.extend([
            '',
            '## TypeScript/JS 检查',
            f'- exit_code: {exit_code}',
            '```text',
            (output or 'ok').strip(),
            '```',
        ])

    if not python_files and not ts_like_files:
        report_lines.extend([
            '',
            '## 执行结果',
            '未找到可直接执行的 Python / TS / JS 文件，暂未运行语法检查。',
        ])

    return '\n'.join(report_lines)


async def build_preview(markdown: str) -> PreviewBuildResult:
    preview_id = uuid.uuid4().hex
    run_dir = PREVIEW_ROOT / preview_id
    project_dir = run_dir / 'project'
    project_dir.mkdir(parents=True, exist_ok=True)

    files = parse_generated_code(markdown)
    if not files:
        raise ValueError('当前生成结果无法解析为结构化代码文件，无法构建预览')

    for item in files:
        target = project_dir / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding='utf-8')

    return await _build_preview_from_project(preview_id, run_dir, project_dir)


async def build_preview_from_dir(source_dir: Path) -> PreviewBuildResult:
    """Build a preview from an existing workspace directory (agent-run output)."""
    import shutil

    if not source_dir.exists():
        raise ValueError('工作区不存在，无法构建预览')
    preview_id = uuid.uuid4().hex
    run_dir = PREVIEW_ROOT / preview_id
    project_dir = run_dir / 'project'
    shutil.copytree(source_dir, project_dir)
    return await _build_preview_from_project(preview_id, run_dir, project_dir)


async def _build_preview_from_project(
    preview_id: str,
    run_dir: Path,
    project_dir: Path,
) -> PreviewBuildResult:

    logs = [f'preview_id={preview_id}', f'project_dir={project_dir}']
    patch_notes = _patch_preview_project(project_dir)
    logs.extend(patch_notes)
    package_json = project_dir / 'package.json'
    index_html = project_dir / 'index.html'
    dist_dir = project_dir / 'dist'
    tsconfig_json = project_dir / 'tsconfig.json'
    tsconfig_node_json = project_dir / 'tsconfig.node.json'

    if tsconfig_json.exists() and not tsconfig_node_json.exists():
        tsconfig_content = tsconfig_json.read_text(encoding='utf-8')
        if 'tsconfig.node.json' in tsconfig_content:
            tsconfig_node_json.write_text(
                '{\n'
                '  "compilerOptions": {\n'
                '    "composite": true,\n'
                '    "skipLibCheck": true,\n'
                '    "module": "ESNext",\n'
                '    "moduleResolution": "bundler",\n'
                '    "allowSyntheticDefaultImports": true\n'
                '  },\n'
                '  "include": ["vite.config.ts"]\n'
                '}\n',
                encoding='utf-8',
            )
            logs.append('自动补齐 tsconfig.node.json')

    if package_json.exists():
        install_code, install_output = await _run_command(
            ['pnpm', 'install', '--ignore-workspace', '--no-frozen-lockfile'],
            cwd=project_dir,
        )
        logs.extend(['## pnpm install', install_output.strip() or 'ok'])
        if install_code != 0:
            raise ValueError(f'预览依赖安装失败：\n{install_output}')

        build_code, build_output = await _run_command(['pnpm', 'build'], cwd=project_dir)
        logs.extend(['## pnpm build', build_output.strip() or 'ok'])
        if build_code != 0:
            vite_code, vite_output = await _run_command(['pnpm', 'exec', 'vite', 'build'], cwd=project_dir)
            logs.extend(['## pnpm exec vite build', vite_output.strip() or 'ok'])
            if vite_code != 0:
                raise ValueError(f'预览构建失败：\n{build_output}\n\n--- vite fallback ---\n{vite_output}')
        if not dist_dir.exists():
            raise ValueError('预览构建完成，但未找到 dist 目录')
        _rewrite_preview_asset_paths(dist_dir)
        (run_dir / 'entry_dir.txt').write_text('project/dist', encoding='utf-8')
        return PreviewBuildResult(preview_id=preview_id, entry_dir=dist_dir, logs='\n\n'.join(logs))

    if index_html.exists():
        logs.append('## static preview\n直接使用生成的 index.html 作为预览入口')
        (run_dir / 'entry_dir.txt').write_text('project', encoding='utf-8')
        return PreviewBuildResult(preview_id=preview_id, entry_dir=project_dir, logs='\n\n'.join(logs))

    raise ValueError('未找到 package.json 或 index.html，无法构建预览')
