import type { ConditionOp, WorkflowEdge } from '@workflow-agent/shared';

type Props = {
  selected: WorkflowEdge | null;
  readOnly: boolean;
  onChange: (edgeId: string, patch: Partial<WorkflowEdge>) => void;
  onDelete?: (edgeId: string) => void;
};

const OPS: Array<{ value: ConditionOp; label: string }> = [
  { value: 'eq', label: 'eq（等于）' },
  { value: 'neq', label: 'neq（不等于）' },
  { value: 'in', label: 'in（在数组中）' },
  { value: 'contains', label: 'contains（包含）' },
  { value: 'gt', label: 'gt（大于）' },
  { value: 'lt', label: 'lt（小于）' },
  { value: 'exists', label: 'exists（存在）' },
];

function valueToText(value: unknown): string {
  if (value === undefined || value === null) {
    return '';
  }
  if (typeof value === 'string') {
    return value;
  }
  return JSON.stringify(value);
}

function textToValue(text: string): unknown {
  const trimmed = text.trim();
  if (!trimmed) {
    return undefined;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return trimmed;
  }
}

export default function EdgeConfigPanel({ selected, readOnly, onChange, onDelete }: Props) {
  if (!selected) {
    return null;
  }

  const disabled = readOnly;
  const condition = selected.condition ?? null;
  const isDefault = !condition;

  const patch = (partial: Partial<WorkflowEdge>) => {
    onChange(selected.id, partial);
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
      <h3>连线配置</h3>
      <div className="config-meta">
        <div>
          <span className="muted">ID</span>
          <code>{selected.id}</code>
        </div>
        <div>
          <span className="muted">走向</span>
          <code>
            {selected.source} → {selected.target}
          </code>
        </div>
      </div>

      <label className="config-field">
        <span>标签 label</span>
        <input
          type="text"
          disabled={disabled}
          value={selected.label ?? ''}
          placeholder="如：打回修改"
          onChange={(event) => patch({ label: event.target.value || undefined })}
        />
      </label>

      <label className="config-field config-field-inline">
        <input
          type="checkbox"
          disabled={disabled}
          checked={isDefault}
          onChange={(event) => {
            if (event.target.checked) {
              patch({ condition: null });
            } else {
              patch({
                condition: { left: 'node_outputs.', op: 'eq', value: '' },
              });
            }
          }}
        />
        <span>default 兜底边（无条件）</span>
      </label>

      {condition ? (
        <>
          <label className="config-field">
            <span>条件路径 left（如 node_outputs.cr.verdict / hitl.action）</span>
            <input
              type="text"
              disabled={disabled}
              value={condition.left}
              onChange={(event) =>
                patch({ condition: { ...condition, left: event.target.value } })
              }
            />
          </label>
          <label className="config-field">
            <span>操作符 op</span>
            <select
              disabled={disabled}
              value={condition.op}
              onChange={(event) =>
                patch({ condition: { ...condition, op: event.target.value as ConditionOp } })
              }
            >
              {OPS.map((op) => (
                <option key={op.value} value={op.value}>
                  {op.label}
                </option>
              ))}
            </select>
          </label>
          {condition.op !== 'exists' ? (
            <label className="config-field">
              <span>比较值 value（JSON 或字符串）</span>
              <input
                type="text"
                disabled={disabled}
                value={valueToText(condition.value)}
                placeholder='如 "reject" 或 ["a","b"]'
                onChange={(event) =>
                  patch({ condition: { ...condition, value: textToValue(event.target.value) } })
                }
              />
            </label>
          ) : null}
        </>
      ) : null}

      <label className="config-field">
        <span>max_iterations（回头边必填，防死循环）</span>
        <input
          type="number"
          min={1}
          disabled={disabled}
          value={selected.max_iterations ?? ''}
          placeholder="5"
          onChange={(event) =>
            patch({
              max_iterations: event.target.value ? Number(event.target.value) : null,
            })
          }
        />
      </label>

      {!readOnly && onDelete ? (
        <button
          type="button"
          className="btn ghost config-delete-btn"
          onClick={() => onDelete(selected.id)}
        >
          删除连线
        </button>
      ) : null}
    </aside>
  );
}
