import { useCallback, useEffect, useMemo, useState } from 'react';
import type { RoleDef } from '@workflow-agent/shared';
import {
  createRole,
  deleteRole,
  duplicateRole,
  listRoles,
  updateRole,
} from '../api';
import { showToast } from '../components/toast';

export default function RolesManager() {
  const [roles, setRoles] = useState<RoleDef[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<RoleDef | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (selectId?: string) => {
    try {
      const items = await listRoles();
      setRoles(items);
      if (selectId) {
        setSelectedId(selectId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载角色失败');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const role = roles.find((item) => item.id === selectedId) ?? null;
    setDraft(role ? { ...role, output_schema: { ...role.output_schema } } : null);
  }, [roles, selectedId]);

  const onCreate = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await createRole({ name: '新角色', system_prompt: '' });
      showToast('角色已创建');
      await refresh(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建角色失败');
    } finally {
      setBusy(false);
    }
  };

  const onSave = async () => {
    if (!draft || draft.builtin) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      let schema: Record<string, unknown> = draft.output_schema;
      if (typeof schema === 'string') {
        schema = JSON.parse(schema || '{}') as Record<string, unknown>;
      }
      await updateRole(draft.id, {
        name: draft.name,
        system_prompt: draft.system_prompt,
        output_schema: schema,
        max_steps: draft.max_steps ?? null,
      });
      showToast('保存成功');
      await refresh(draft.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
      showToast(err instanceof Error ? err.message : '保存失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const onDuplicate = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      const copy = await duplicateRole(id);
      showToast('已复制为可编辑角色');
      await refresh(copy.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '复制失败');
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (role: RoleDef) => {
    const confirmed = window.confirm(`确定删除角色「${role.name}」？`);
    if (!confirmed) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteRole(role.id);
      showToast('删除成功');
      setSelectedId(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    } finally {
      setBusy(false);
    }
  };

  const schemaText =
    typeof draft?.output_schema === 'string'
      ? (draft.output_schema as unknown as string)
      : JSON.stringify(draft?.output_schema ?? {}, null, 2);

  const builtinCount = useMemo(() => roles.filter((r) => r.builtin).length, [roles]);
  const customCount = useMemo(() => roles.filter((r) => !r.builtin).length, [roles]);

  return (
    <div className="workspace roles-manager">
      <header className="bar workspace-bar">
        <div className="workspace-title">
          <h1>角色管理</h1>
          <span className="role-count">
            {roles.length} 个角色 · {builtinCount} 内置 · {customCount} 自定义
          </span>
        </div>
        <div className="workspace-actions">
          <button
            type="button"
            className="btn primary"
            disabled={busy}
            onClick={() => void onCreate()}
          >
            + 新建角色
          </button>
        </div>
      </header>

      {error ? <div className="err">{error}</div> : null}

      <div className="roles-layout">
        <aside className="roles-sidebar">
          <div className="roles-sidebar-header">
            <span>角色列表</span>
          </div>
          <div className="role-list">
            {roles.map((role) => (
              <button
                key={role.id}
                type="button"
                className={selectedId === role.id ? 'role-item on' : 'role-item'}
                disabled={busy}
                onClick={() => setSelectedId(role.id)}
              >
                <span className="role-item-name">{role.name}</span>
                {role.builtin ? (
                  <span className="role-badge builtin">内置</span>
                ) : (
                  <span className="role-badge custom">自定义</span>
                )}
              </button>
            ))}
          </div>
        </aside>

        <section className="roles-content">
          {!draft ? (
            <div className="roles-empty">
              <div className="roles-empty-icon">🎭</div>
              <h3>选择一个角色</h3>
              <p>从左侧列表选择角色查看或编辑，或点击右上角创建新角色。</p>
            </div>
          ) : (
            <>
              <div className="roles-content-header">
                <div className="roles-content-title">
                  <h2>{draft.name}</h2>
                  {draft.builtin ? (
                    <span className="role-badge builtin">内置 · 只读</span>
                  ) : (
                    <span className="role-badge custom">自定义</span>
                  )}
                </div>
                <div className="workspace-actions">
                  {draft.builtin ? (
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => void onDuplicate(draft.id)}
                    >
                      复制为可编辑角色
                    </button>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="btn ghost"
                        disabled={busy}
                        onClick={() => void onDelete(draft)}
                      >
                        删除
                      </button>
                      <button
                        type="button"
                        className="btn primary"
                        disabled={busy}
                        onClick={() => void onSave()}
                      >
                        保存
                      </button>
                    </>
                  )}
                </div>
              </div>

              <div className="roles-form">
                <div className="roles-section">
                  <h3 className="roles-section-title">基本信息</h3>
                  <div className="roles-section-body">
                    <label className="config-field">
                      <span>角色名称</span>
                      <input
                        type="text"
                        disabled={draft.builtin || busy}
                        value={draft.name}
                        onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                        placeholder="给角色起个名字"
                      />
                    </label>

                    <label className="config-field">
                      <span>最大步数</span>
                      <small className="field-hint">留空则使用全局默认值（30）</small>
                      <input
                        type="number"
                        min={1}
                        disabled={draft.builtin || busy}
                        value={draft.max_steps ?? ''}
                        onChange={(event) =>
                          setDraft({
                            ...draft,
                            max_steps: event.target.value ? Number(event.target.value) : null,
                          })
                        }
                        placeholder="30"
                      />
                    </label>
                  </div>
                </div>

                <div className="roles-section">
                  <h3 className="roles-section-title">提示词配置</h3>
                  <div className="roles-section-body">
                    <label className="config-field">
                      <span>System Prompt</span>
                      <small className="field-hint">定义角色的人设、工作规范和产物说明</small>
                      <textarea
                        className="code"
                        rows={12}
                        disabled={draft.builtin || busy}
                        value={draft.system_prompt}
                        onChange={(event) =>
                          setDraft({ ...draft, system_prompt: event.target.value })
                        }
                        placeholder="输入 system prompt..."
                      />
                    </label>
                  </div>
                </div>

                <div className="roles-section">
                  <h3 className="roles-section-title">输出约束</h3>
                  <div className="roles-section-body">
                    <label className="config-field">
                      <span>Output Schema（JSON）</span>
                      <small className="field-hint">用 JSON Schema 定义模型输出格式</small>
                      <textarea
                        className="code"
                        rows={10}
                        disabled={draft.builtin || busy}
                        value={schemaText}
                        onChange={(event) =>
                          setDraft({
                            ...draft,
                            output_schema:
                              event.target.value as unknown as Record<string, unknown>,
                          })
                        }
                        placeholder="{}"
                      />
                    </label>
                  </div>
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
