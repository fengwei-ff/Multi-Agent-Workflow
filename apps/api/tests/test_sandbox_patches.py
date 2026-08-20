from __future__ import annotations

from pathlib import Path

from app.sandbox import _patch_preview_project


def test_patch_preview_project_fixes_generated_edit_handler(tmp_path: Path):
    app_file = tmp_path / 'src' / 'app.js'
    app_file.parent.mkdir(parents=True)
    app_file.write_text(
        """const editBtn = document.createElement('button');
editBtn.addEventListener('click', () => {
        editingId = null;
        render();
      });
""",
        encoding='utf-8',
    )

    notes = _patch_preview_project(tmp_path)

    assert 'editingId = todo.id;' in app_file.read_text(encoding='utf-8')
    assert any('编辑按钮状态' in note for note in notes)
