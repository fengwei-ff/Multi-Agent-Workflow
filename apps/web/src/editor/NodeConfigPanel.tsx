import type { RoleDef, WorkflowNode, WorkflowNodeType } from '@workflow-agent/shared';
import { NODE_TYPE_LABELS } from './nodeTypes';

type Props = {
  selected: WorkflowNode | null;
  readOnly: boolean;
  roles: RoleDef[];
  onChange: (nodeId: string, patch: { data?: Record<string, unknown>; name?: string }) => void;
  onDelete?: (nodeId: string) => void;
};

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function optionsToCsv(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(String).join(', ');
  }
  return asString(value);
}

function csvToOptions(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function NodeConfigPanel({ selected, readOnly, roles, onChange, onDelete }: Props) {
  if (!selected) {
    return (
      <aside
        className="node-config-panel"
        onMouseDown={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === 'Backspace' || event.key === 'Delete') {
            event.stopPropagation();
          }
        }}
      >
        <h3>节点配置</h3>
        <p className="muted">选中节点或连线进行配置</p>
      </aside>
    );
  }

  const type = selected.type as WorkflowNodeType;
  const data = selected.data ?? {};
  const disabled = readOnly;
  const canDelete = !readOnly && type !== 'start' && type !== 'end';

  const patchData = (partial: Record<string, unknown>) => {
    onChange(selected.id, { data: { ...data, ...partial } });
  };

  return (
    <aside
      className={`node-config-panel${readOnly ? ' is-readonly' : ''}`}
      onMouseDown={(event) => event.stopPropagation()}
      onKeyDown={(event) => {
        if (event.key === 'Backspace' || event.key === 'Delete') {
          event.stopPropagation();
        }
      }}
    >
      <h3>节点配置</h3>
      <div className="config-meta">
        <div>
          <span className="muted">类型</span>
          <strong>{NODE_TYPE_LABELS[type] || type}</strong>
        </div>
        <div>
          <span className="muted">ID</span>
          <code>{selected.id}</code>
        </div>
      </div>

      <label className="config-field">
        <span>标题</span>
        <input
          type="text"
          disabled={disabled}
          value={asString(data.title)}
          placeholder={NODE_TYPE_LABELS[type]}
          onChange={(event) => patchData({ title: event.target.value })}
        />
      </label>

      {type === 'agent' ? (
        <>
          <label className="config-field">
            <span>角色</span>
            <select
              disabled={disabled}
              value={asString(data.role_id)}
              onChange={(event) => {
                const role = roles.find((item) => item.id === event.target.value);
                patchData({ role_id: event.target.value, role_name: role?.name ?? '' });
              }}
            >
              <option value="">选择角色…</option>
              {roles.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name}
                  {role.builtin ? '（内置）' : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="config-field">
            <span>task_template（支持 {'{user_request}'} / {'{node_outputs.xx.yy}'} 占位符）</span>
            <textarea
              disabled={disabled}
              rows={5}
              value={asString(data.task_template, '{user_request}')}
              onChange={(event) => patchData({ task_template: event.target.value })}
            />
          </label>
          <label className="config-field">
            <span>max_steps（留空用全局默认）</span>
            <input
              type="number"
              min={1}
              disabled={disabled}
              value={asNumber(data.max_steps) ?? ''}
              placeholder="30"
              onChange={(event) =>
                patchData({
                  max_steps: event.target.value ? Number(event.target.value) : null,
                })
              }
            />
          </label>
        </>
      ) : null}

      {type === 'hitl' ? (
        <>
          <label className="config-field">
            <span>审批选项 options（逗号分隔）</span>
            <input
              type="text"
              disabled={disabled}
              value={optionsToCsv(data.options)}
              placeholder="approve, reject"
              onChange={(event) => patchData({ options: csvToOptions(event.target.value) })}
            />
          </label>
          <label className="config-field">
            <span>展示字段 summary_fields（逗号分隔的状态路径）</span>
            <input
              type="text"
              disabled={disabled}
              value={optionsToCsv(data.summary_fields)}
              placeholder="node_outputs.pm.summary"
              onChange={(event) =>
                patchData({ summary_fields: csvToOptions(event.target.value) })
              }
            />
          </label>
        </>
      ) : null}

      {canDelete && onDelete ? (
        <button
          type="button"
          className="btn ghost config-delete-btn"
          onClick={() => onDelete(selected.id)}
        >
          删除节点
        </button>
      ) : null}
    </aside>
  );
}
