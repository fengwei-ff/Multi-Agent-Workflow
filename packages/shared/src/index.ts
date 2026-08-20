export type WorkflowPhase = 'running' | 'done' | 'failed';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: string;
}

export interface ThreadSummary {
  thread_id: string;
  title: string;
  phase?: WorkflowPhase;
  workflow_id?: string;
  workflow_name?: string;
  created_at: string;
  updated_at: string;
}

export type WorkflowNodeType = 'start' | 'end' | 'agent' | 'hitl';

export interface WorkflowNodeSummary {
  id: string;
  type: WorkflowNodeType;
  data?: Record<string, unknown>;
}

export interface HitlState {
  node_id: string;
  action: string;
  message: string;
}

export interface ThreadStateView {
  thread_id: string;
  phase: WorkflowPhase;
  workflow_id?: string;
  workflow_name?: string;
  workflow_nodes?: WorkflowNodeSummary[];
  user_request: string;
  active_node_id: string;
  node_outputs: Record<string, Record<string, unknown>>;
  hitl?: HitlState | null;
  workspace_dir: string;
  last_assistant_message: string;
  messages: ChatMessage[];
  interrupted: boolean;
  interrupt?: InterruptPayload | null;
  can_retry: boolean;
  pending_nodes: string[];
}

export interface InterruptPayload {
  kind: string;
  title: string;
  summary: string;
  options: string[];
  payload?: Record<string, unknown>;
}

export interface CreateThreadRequest {
  user_request: string;
  workflow_id?: string;
}

export interface CreateThreadResponse {
  thread_id: string;
}

export interface ResumeRequest {
  action: string;
  message?: string;
  feedback?: string;
}

export type ConditionOp = 'eq' | 'neq' | 'in' | 'contains' | 'gt' | 'lt' | 'exists';

export interface EdgeCondition {
  left: string;
  op: ConditionOp;
  value?: unknown;
}

export interface AgentNodeData {
  role_id: string;
  task_template: string;
  max_steps?: number;
}

export interface HitlNodeData {
  title: string;
  options: string[];
  summary_fields: string[];
}

export interface RoleDef {
  id: string;
  name: string;
  builtin: boolean;
  system_prompt: string;
  output_schema: Record<string, unknown>;
  max_steps?: number | null;
  created_at: string;
  updated_at: string;
}

/** Derive stepper stages from workflow graph nodes (snapshot / template). */
export function stepperFromWorkflow(
  nodes: WorkflowNode[],
  roles?: RoleDef[],
): Array<{ id: string; label: string }> {
  const stages: Array<{ id: string; label: string }> = [];
  for (const n of nodes) {
    if (n.type === 'start' || n.type === 'end') continue;
    let label = n.id;
    if (n.type === 'hitl') {
      label = String(n.data?.title || '人工审批');
    } else if (n.type === 'agent') {
      const roleId = String(n.data?.role_id || '');
      label = roles?.find((r) => r.id === roleId)?.name || roleId || n.id;
    }
    stages.push({ id: n.id, label });
  }
  stages.push({ id: '__done__', label: '完成' });
  return stages;
}

export interface WorkflowNodePosition {
  x: number;
  y: number;
}

export interface WorkflowNode {
  id: string;
  type: WorkflowNodeType;
  position: WorkflowNodePosition;
  data: Record<string, unknown>;
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  condition?: EdgeCondition | null;
  max_iterations?: number | null;
  label?: string;
}

export interface WorkflowViewport {
  x: number;
  y: number;
  zoom: number;
}

export interface WorkflowDef {
  id: string;
  name: string;
  description?: string;
  builtin: boolean;
  created_at: string;
  updated_at: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  viewport?: WorkflowViewport;
}

export interface WorkflowSummary {
  id: string;
  name: string;
  description?: string;
  builtin: boolean;
  updated_at: string;
}

export interface CreateWorkflowRequest {
  name: string;
  description?: string;
  nodes?: WorkflowNode[];
  edges?: WorkflowEdge[];
}

export interface UpdateWorkflowRequest {
  name?: string;
  description?: string;
  nodes?: WorkflowNode[];
  edges?: WorkflowEdge[];
  viewport?: WorkflowViewport;
}

export interface CreateRunRequest {
  user_request: string;
}

export interface CreateRunResponse {
  thread_id: string;
}
