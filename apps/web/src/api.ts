import type {
  CreateThreadResponse,
  CreateWorkflowRequest,
  ResumeRequest,
  RoleDef,
  ThreadStateView,
  ThreadSummary,
  UpdateWorkflowRequest,
  WorkflowDef,
  WorkflowSummary,
} from '@workflow-agent/shared';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function detailToMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (item && typeof item === 'object' && 'message' in item) {
          return String((item as { message: unknown }).message);
        }
        if (item && typeof item === 'object' && 'msg' in item) {
          return String((item as { msg: unknown }).msg);
        }
        return null;
      })
      .filter((value): value is string => Boolean(value));
    if (messages.length > 0) {
      return messages.join('；');
    }
    try {
      return JSON.stringify(detail);
    } catch {
      return fallback;
    }
  }
  if (detail != null) {
    try {
      return typeof detail === 'object' ? JSON.stringify(detail) : String(detail);
    } catch {
      return fallback;
    }
  }
  return fallback;
}

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? body;
    } catch {
      // ignore
    }
    throw new ApiError(detailToMessage(detail, '请求失败'), response.status, detail);
  }
  return response.json() as Promise<T>;
}

export async function listWorkflows(): Promise<WorkflowSummary[]> {
  const data = await parseJson<{ workflows: WorkflowSummary[] }>(
    await fetch(`${API_BASE}/workflows`),
  );
  return data.workflows;
}

export async function getWorkflow(id: string): Promise<WorkflowDef> {
  return parseJson<WorkflowDef>(await fetch(`${API_BASE}/workflows/${id}`));
}

export async function createWorkflow(body: CreateWorkflowRequest): Promise<WorkflowDef> {
  return parseJson<WorkflowDef>(
    await fetch(`${API_BASE}/workflows`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
}

export async function updateWorkflow(
  id: string,
  body: UpdateWorkflowRequest,
): Promise<WorkflowDef> {
  return parseJson<WorkflowDef>(
    await fetch(`${API_BASE}/workflows/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
}

export async function deleteWorkflow(id: string): Promise<void> {
  await parseJson<unknown>(
    await fetch(`${API_BASE}/workflows/${id}`, {
      method: 'DELETE',
    }),
  );
}

export async function duplicateWorkflow(id: string): Promise<WorkflowDef> {
  return parseJson<WorkflowDef>(
    await fetch(`${API_BASE}/workflows/${id}/duplicate`, {
      method: 'POST',
    }),
  );
}

export async function listWorkflowRuns(workflowId: string): Promise<ThreadSummary[]> {
  const data = await parseJson<{ threads: ThreadSummary[] }>(
    await fetch(`${API_BASE}/workflows/${workflowId}/runs`),
  );
  return data.threads;
}

export async function createWorkflowRun(
  workflowId: string,
  userRequest: string,
): Promise<string> {
  const data = await parseJson<{ thread_id: string }>(
    await fetch(`${API_BASE}/workflows/${workflowId}/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_request: userRequest }),
    }),
  );
  return data.thread_id;
}

export async function listThreads(): Promise<ThreadSummary[]> {
  const data = await parseJson<{ threads: ThreadSummary[] }>(
    await fetch(`${API_BASE}/threads`),
  );
  return data.threads;
}

export async function deleteThread(threadId: string): Promise<void> {
  await parseJson<unknown>(
    await fetch(`${API_BASE}/threads/${threadId}`, {
      method: 'DELETE',
    }),
  );
}

export async function createThread(
  userRequest: string,
  workflowId = 'dev_delivery',
): Promise<string> {
  const data = await parseJson<CreateThreadResponse>(
    await fetch(`${API_BASE}/threads`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_request: userRequest,
        workflow_id: workflowId,
      }),
    }),
  );
  return data.thread_id;
}

export async function getThread(threadId: string): Promise<ThreadStateView> {
  return parseJson<ThreadStateView>(await fetch(`${API_BASE}/threads/${threadId}`));
}

export interface AgentStreamEvent {
  type: 'agent';
  node: string;
  kind: 'tool_call' | 'tool_result' | 'message' | 'finish';
  step: number;
  tool?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  content?: string;
}

export type StreamEvent =
  | { type: 'node'; node: string; data: Record<string, unknown> }
  | AgentStreamEvent
  | { type: 'interrupt'; data: ThreadStateView['interrupt'] }
  | { type: 'state'; data: ThreadStateView }
  | { type: 'artifact'; artifact: 'generated_code'; delta: string }
  | { type: 'error'; message: string }
  | { type: 'done' };

function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === 'AbortError')
    || (err instanceof Error && err.name === 'AbortError')
  );
}

async function consumeSse(
  response: Response,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (!response.ok || !response.body) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // ignore
    }
    throw new Error(detail || '流式请求失败');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const cancelQuietly = async () => {
    try {
      await reader.cancel();
    } catch {
      // ignore
    }
  };

  while (true) {
    if (signal?.aborted) {
      await cancelQuietly();
      return;
    }
    let done = false;
    let value: Uint8Array | undefined;
    try {
      ({ done, value } = await reader.read());
    } catch (err) {
      if (signal?.aborted || isAbortError(err)) {
        await cancelQuietly();
        return;
      }
      throw err;
    }
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split('\n\n');
    buffer = chunks.pop() || '';
    for (const chunk of chunks) {
      if (signal?.aborted) {
        await cancelQuietly();
        return;
      }
      const line = chunk
        .split('\n')
        .map((item) => item.trim())
        .find((item) => item.startsWith('data:'));
      if (!line) {
        continue;
      }
      const payload = line.slice(5).trim();
      if (!payload) {
        continue;
      }
      try {
        onEvent(JSON.parse(payload) as StreamEvent);
      } catch {
        // ignore malformed chunk
      }
    }
  }
}

export async function runThread(
  threadId: string,
  userRequest: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/threads/${threadId}/runs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_request: userRequest }),
      signal,
    });
    await consumeSse(response, onEvent, signal);
  } catch (err) {
    if (signal?.aborted || isAbortError(err)) {
      return;
    }
    throw err;
  }
}

export async function resumeThread(
  threadId: string,
  body: ResumeRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/threads/${threadId}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    });
    await consumeSse(response, onEvent, signal);
  } catch (err) {
    if (signal?.aborted || isAbortError(err)) {
      return;
    }
    throw err;
  }
}

export async function retryThread(
  threadId: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/threads/${threadId}/retry`, {
      method: 'POST',
      signal,
    });
    await consumeSse(response, onEvent, signal);
  } catch (err) {
    if (signal?.aborted || isAbortError(err)) {
      return;
    }
    throw err;
  }
}

export interface PreviewBuildResponse {
  preview_id: string;
  preview_url: string;
  logs: string;
}

export async function buildPreview(threadId: string): Promise<PreviewBuildResponse> {
  return parseJson<PreviewBuildResponse>(
    await fetch(`${API_BASE}/threads/${threadId}/preview`, {
      method: 'POST',
    }),
  );
}

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

export async function listRoles(): Promise<RoleDef[]> {
  const data = await parseJson<{ roles: RoleDef[] }>(await fetch(`${API_BASE}/roles`));
  return data.roles;
}

export async function createRole(body: {
  name: string;
  system_prompt?: string;
  output_schema?: Record<string, unknown>;
  max_steps?: number | null;
}): Promise<RoleDef> {
  return parseJson<RoleDef>(
    await fetch(`${API_BASE}/roles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
}

export async function updateRole(
  id: string,
  body: {
    name?: string;
    system_prompt?: string;
    output_schema?: Record<string, unknown>;
    max_steps?: number | null;
  },
): Promise<RoleDef> {
  return parseJson<RoleDef>(
    await fetch(`${API_BASE}/roles/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
}

export async function deleteRole(id: string): Promise<void> {
  await parseJson<unknown>(await fetch(`${API_BASE}/roles/${id}`, { method: 'DELETE' }));
}

export async function duplicateRole(id: string): Promise<RoleDef> {
  return parseJson<RoleDef>(
    await fetch(`${API_BASE}/roles/${id}/duplicate`, { method: 'POST' }),
  );
}

// ---------------------------------------------------------------------------
// Workspace files
// ---------------------------------------------------------------------------

export async function listWorkspaceFiles(threadId: string): Promise<string[]> {
  const data = await parseJson<{ files: string[] }>(
    await fetch(`${API_BASE}/threads/${threadId}/workspace/files`),
  );
  return data.files;
}

export async function readWorkspaceFile(
  threadId: string,
  path: string,
): Promise<{ path: string; content: string }> {
  return parseJson<{ path: string; content: string }>(
    await fetch(`${API_BASE}/threads/${threadId}/workspace/file?path=${encodeURIComponent(path)}`),
  );
}
