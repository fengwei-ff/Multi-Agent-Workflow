import { Position, type NodeProps } from '@xyflow/react';
import type { WorkflowNodeType } from '@workflow-agent/shared';
import WorkflowHandle from './WorkflowHandle';

export const NODE_TYPE_LABELS: Record<WorkflowNodeType, string> = {
  start: '开始',
  end: '结束',
  agent: 'Agent 角色',
  hitl: '人工审批',
};

export type WorkflowRfData = Record<string, unknown> & {
  title?: string;
  role_name?: string;
  _hasError?: boolean;
  _errorMessage?: string;
};

function nodeTitle(type: WorkflowNodeType, data: WorkflowRfData): string {
  const title = typeof data.title === 'string' ? data.title.trim() : '';
  if (title) return title;
  if (type === 'agent') {
    const roleName = typeof data.role_name === 'string' ? data.role_name.trim() : '';
    if (roleName) return roleName;
  }
  return NODE_TYPE_LABELS[type] || type;
}

function WorkflowNodeView({ data, type }: NodeProps) {
  const nodeType = (type || 'agent') as WorkflowNodeType;
  const nodeData = (data || {}) as WorkflowRfData;
  const title = nodeTitle(nodeType, nodeData);
  const hasError = Boolean(nodeData._hasError);
  const errorMessage =
    typeof nodeData._errorMessage === 'string' ? nodeData._errorMessage : '校验失败';

  return (
    <div
      className={`wf-node wf-node-${nodeType} wf-node-single-line${hasError ? ' wf-node-has-error' : ''}`}
      data-type={nodeType}
      title={title}
    >
      {hasError ? (
        <span className="wf-node-error-badge" title={errorMessage}>
          !
        </span>
      ) : null}

      {nodeType !== 'start' ? (
        <WorkflowHandle type="target" position={Position.Left} className="wf-handle" />
      ) : null}

      <div className="wf-node-title">{title}</div>

      {nodeType !== 'end' ? (
        <WorkflowHandle type="source" position={Position.Right} className="wf-handle" />
      ) : null}
    </div>
  );
}

const ALL_TYPES: WorkflowNodeType[] = ['start', 'end', 'agent', 'hitl'];

export const nodeTypes = Object.fromEntries(
  ALL_TYPES.map((type) => [type, WorkflowNodeView]),
);
