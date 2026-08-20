import type { WorkflowDef } from '@workflow-agent/shared';

export type WorkflowValidationError = {
  code: string;
  message: string;
  node_id?: string;
  edge_id?: string;
};

const CONDITION_ROOTS = new Set(['node_outputs', 'hitl', 'loop_counts', 'user_request', 'phase']);

function reachableTargets(edges: WorkflowDef['edges'], startId: string): Set<string> {
  const outgoing = new Map<string, string[]>();
  for (const edge of edges) {
    const list = outgoing.get(edge.source) ?? [];
    list.push(edge.target);
    outgoing.set(edge.source, list);
  }
  const seen = new Set<string>();
  const stack = [startId];
  while (stack.length) {
    const current = stack.pop()!;
    for (const next of outgoing.get(current) ?? []) {
      if (!seen.has(next)) {
        seen.add(next);
        stack.push(next);
      }
    }
  }
  return seen;
}

function findBackEdges(workflow: WorkflowDef): Set<string> {
  // DFS from start; u→v is a back edge iff v is still on the DFS stack (gray)
  // when u is explored — singles out the "return" edge of each cycle.
  const outgoing = new Map<string, WorkflowDef['edges']>();
  for (const edge of workflow.edges) {
    const list = outgoing.get(edge.source) ?? [];
    list.push(edge);
    outgoing.set(edge.source, list);
  }
  const starts = workflow.nodes.filter((node) => node.type === 'start').map((node) => node.id);
  const roots = starts.length ? starts : (workflow.nodes.length ? [workflow.nodes[0].id] : []);
  const WHITE = 0;
  const GRAY = 1;
  const BLACK = 2;
  const color = new Map<string, number>();
  const back = new Set<string>();
  for (const root of roots) {
    if ((color.get(root) ?? WHITE) !== WHITE) continue;
    color.set(root, GRAY);
    const stack: Array<[string, WorkflowDef['edges']]> = [[root, [...(outgoing.get(root) ?? [])]]];
    while (stack.length) {
      const [current, pending] = stack[stack.length - 1];
      const edge = pending.shift();
      if (!edge) {
        color.set(current, BLACK);
        stack.pop();
        continue;
      }
      const targetColor = color.get(edge.target) ?? WHITE;
      if (targetColor === GRAY) {
        back.add(edge.id);
      } else if (targetColor === WHITE) {
        color.set(edge.target, GRAY);
        stack.push([edge.target, [...(outgoing.get(edge.target) ?? [])]]);
      }
    }
  }
  return back;
}

/** Client-side mirror of apps/api/app/workflows/validate.py. */
export function validateWorkflowClient(workflow: WorkflowDef): WorkflowValidationError[] {
  const errors: WorkflowValidationError[] = [];
  const nodes = workflow.nodes;
  const edges = workflow.edges;

  const starts = nodes.filter((node) => node.type === 'start');
  const ends = nodes.filter((node) => node.type === 'end');
  if (starts.length !== 1) {
    errors.push({
      code: 'start_count',
      message: `需要恰好 1 个 start 节点，当前 ${starts.length} 个`,
    });
  }
  if (ends.length < 1) {
    errors.push({ code: 'end_count', message: '至少需要 1 个 end 节点' });
  }

  const idSet = new Set(nodes.map((node) => node.id));
  for (const edge of edges) {
    if (!idSet.has(edge.source)) {
      errors.push({
        code: 'missing_source',
        message: `边的 source 不存在: ${edge.source}`,
        edge_id: edge.id,
      });
    }
    if (!idSet.has(edge.target)) {
      errors.push({
        code: 'missing_target',
        message: `边的 target 不存在: ${edge.target}`,
        edge_id: edge.id,
      });
    }
    if (edge.condition) {
      const root = (edge.condition.left || '').split('.')[0];
      if (!CONDITION_ROOTS.has(root)) {
        errors.push({
          code: 'condition_path',
          message: `条件路径根不在白名单内: ${edge.condition.left}`,
          edge_id: edge.id,
        });
      }
    }
  }

  if (starts.length === 1) {
    const reachable = reachableTargets(edges, starts[0].id);
    reachable.add(starts[0].id);
    for (const node of nodes) {
      if (!reachable.has(node.id)) {
        errors.push({
          code: 'unreachable_node',
          message: `节点从 start 不可达: ${node.id}`,
          node_id: node.id,
        });
      }
    }
  }

  const outgoing = new Map<string, typeof edges>();
  for (const node of nodes) {
    outgoing.set(node.id, []);
  }
  for (const edge of edges) {
    outgoing.get(edge.source)?.push(edge);
  }

  const backEdges = findBackEdges(workflow);

  for (const node of nodes) {
    const outs = outgoing.get(node.id) ?? [];
    if (node.type === 'end') continue;
    if (outs.length === 0) {
      errors.push({ code: 'no_outgoing', message: `节点缺少出边: ${node.id}`, node_id: node.id });
    }
    const defaults = outs.filter((edge) => !edge.condition);
    if (outs.length > 1 && defaults.length !== 1) {
      errors.push({
        code: 'default_edge_count',
        message: `节点 ${node.id} 有 ${outs.length} 条出边，必须恰好一条无条件 default 边`,
        node_id: node.id,
      });
    }
    for (const edge of defaults) {
      if (backEdges.has(edge.id)) {
        errors.push({
          code: 'default_is_back_edge',
          message: `default 边不能是回头边: ${edge.id}`,
          node_id: node.id,
          edge_id: edge.id,
        });
      }
    }
    if (node.type === 'agent') {
      const roleId = String(node.data?.role_id ?? '').trim();
      if (!roleId) {
        errors.push({
          code: 'agent_missing_role',
          message: `agent 节点未配置角色: ${node.id}`,
          node_id: node.id,
        });
      }
    }
    if (node.type === 'hitl') {
      const options = Array.isArray(node.data?.options) ? node.data.options : [];
      if (options.length === 0) {
        errors.push({
          code: 'hitl_missing_options',
          message: `hitl 节点未配置审批选项: ${node.id}`,
          node_id: node.id,
        });
      }
    }
  }

  for (const edge of edges) {
    if (backEdges.has(edge.id) && !edge.max_iterations) {
      errors.push({
        code: 'back_edge_no_limit',
        message: `回头边缺少 max_iterations: ${edge.id}`,
        edge_id: edge.id,
      });
    }
  }

  return errors;
}

export function formatValidationErrors(errors: WorkflowValidationError[]): string {
  return errors.map((error) => error.message).join('；');
}

export function errorNodeIds(errors: WorkflowValidationError[]): string[] {
  return [
    ...new Set(
      errors
        .map((error) => error.node_id)
        .filter((value): value is string => Boolean(value)),
    ),
  ];
}

/** Parse FastAPI 422 detail into structured workflow validation errors when possible. */
export function parseApiValidationDetail(detail: unknown): WorkflowValidationError[] | null {
  if (!Array.isArray(detail)) {
    return null;
  }
  const parsed: WorkflowValidationError[] = [];
  for (const item of detail) {
    if (!item || typeof item !== 'object') {
      return null;
    }
    const record = item as Record<string, unknown>;
    if (typeof record.code !== 'string' || typeof record.message !== 'string') {
      return null;
    }
    parsed.push({
      code: record.code,
      message: record.message,
      node_id: typeof record.node_id === 'string' ? record.node_id : undefined,
      edge_id: typeof record.edge_id === 'string' ? record.edge_id : undefined,
    });
  }
  return parsed;
}
