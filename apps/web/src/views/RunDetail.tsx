import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  stepperFromWorkflow,
  type ChatMessage,
  type RoleDef,
  type ThreadStateView,
  type WorkflowNode,
} from '@workflow-agent/shared';
import {
  buildPreview,
  getThread,
  listRoles,
  listWorkspaceFiles,
  readWorkspaceFile,
  resumeThread,
  retryThread,
  runThread,
  type AgentStreamEvent,
  type StreamEvent,
} from '../api';

type Props = {
  threadId: string;
  onBack: () => void;
  /** Full user request when opening a freshly created run (meta.title may be truncated). */
  seedRequest?: string;
};

/** Survives remounts so Strict Mode / re-entry cannot double-start the same thread. */
const autoStartedThreadIds = new Set<string>();

const EMPTY_STATE: ThreadStateView = {
  thread_id: '',
  phase: 'running',
  user_request: '',
  active_node_id: '',
  node_outputs: {},
  hitl: null,
  workspace_dir: '',
  last_assistant_message: '',
  messages: [],
  interrupted: false,
  interrupt: null,
  can_retry: false,
  pending_nodes: [],
};

type ToolEvent = AgentStreamEvent & { id: number };

const PHASE_LABELS: Record<ThreadStateView['phase'], string> = {
  running: '运行中',
  done: '已完成',
  failed: '已失败',
};

function nodeLabel(node: WorkflowNode | undefined, roles: RoleDef[]): string {
  if (!node) {
    return '';
  }
  if (node.type === 'hitl') {
    return String(node.data?.title || '人工审批');
  }
  if (node.type === 'agent') {
    const roleId = String(node.data?.role_id || '');
    return roles.find((role) => role.id === roleId)?.name || roleId || node.id;
  }
  return node.id;
}

function toolEventText(event: ToolEvent): string {
  if (event.kind === 'tool_call') {
    const args = event.args ? JSON.stringify(event.args) : '';
    const trimmed = args.length > 200 ? `${args.slice(0, 200)}…` : args;
    return `调用工具 ${event.tool ?? ''} ${trimmed}`;
  }
  if (event.kind === 'tool_result') {
    const text = typeof event.result === 'string' ? event.result : JSON.stringify(event.result);
    const trimmed = text && text.length > 400 ? `${text.slice(0, 400)}…` : text;
    return `工具结果：${trimmed ?? ''}`;
  }
  if (event.kind === 'finish') {
    return `完成：${event.content ?? ''}`;
  }
  return event.content ?? '';
}

export default function RunDetail({ threadId, onBack, seedRequest }: Props) {
  const [state, setState] = useState<ThreadStateView>(EMPTY_STATE);
  const [roles, setRoles] = useState<RoleDef[]>([]);
  const [toolEvents, setToolEvents] = useState<ToolEvent[]>([]);
  const [replyText, setReplyText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusLine, setStatusLine] = useState('就绪');
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [workspaceFiles, setWorkspaceFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [fileError, setFileError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewDevice, setPreviewDevice] = useState<'mobile' | 'desktop'>('mobile');
  const [previewOpen, setPreviewOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const toolEventSeq = useRef(0);

  const workflowNodes: WorkflowNode[] = useMemo(
    () =>
      (state.workflow_nodes ?? []).map((node) => ({
        id: node.id,
        type: node.type,
        position: { x: 0, y: 0 },
        data: node.data ?? {},
      })),
    [state.workflow_nodes],
  );

  const stepperSteps = useMemo(
    () => stepperFromWorkflow(workflowNodes, roles),
    [workflowNodes, roles],
  );

  const currentNodeId = useMemo(() => {
    const interruptNodeId = state.interrupt?.payload?.node_id;
    if (typeof interruptNodeId === 'string' && interruptNodeId) {
      return interruptNodeId;
    }

    const visibleStepIds = new Set(stepperSteps.map((step) => step.id));
    const pendingNodeId = state.pending_nodes.find((nodeId) => visibleStepIds.has(nodeId));
    if (pendingNodeId) {
      return pendingNodeId;
    }

    if (state.active_node_id && !state.node_outputs[state.active_node_id]) {
      return state.active_node_id;
    }
    return '';
  }, [state.active_node_id, state.interrupt, state.node_outputs, state.pending_nodes, stepperSteps]);

  const activeNode = useMemo(
    () => workflowNodes.find((node) => node.id === currentNodeId),
    [currentNodeId, workflowNodes],
  );

  const stepStatus = useCallback(
    (stepId: string): 'done' | 'current' | 'todo' => {
      if (stepId === '__done__') {
        return state.phase === 'done' ? 'done' : 'todo';
      }
      if (state.node_outputs[stepId]) {
        return currentNodeId === stepId ? 'current' : 'done';
      }
      if (currentNodeId === stepId) {
        return 'current';
      }
      return 'todo';
    },
    [currentNodeId, state.node_outputs, state.phase],
  );

  const beginStream = useCallback(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    return controller.signal;
  }, []);

  const applyState = useCallback((next: ThreadStateView) => {
    if (!mountedRef.current) {
      return;
    }
    setState(next);
  }, []);

  const refreshWorkspaceFiles = useCallback(async () => {
    try {
      const files = await listWorkspaceFiles(threadId);
      if (mountedRef.current) {
        setWorkspaceFiles(files);
      }
    } catch {
      // workspace may not exist yet
    }
  }, [threadId]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    listRoles()
      .then((items) => {
        if (mountedRef.current) {
          setRoles(items);
        }
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    void refreshWorkspaceFiles();
  }, [refreshWorkspaceFiles]);

  useEffect(() => {
    if (!busy || runStartedAt === null) {
      setElapsedSeconds(0);
      return;
    }
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - runStartedAt) / 1000)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [busy, runStartedAt]);

  const patchFromNode = useCallback((data: Record<string, unknown>) => {
    if (!mountedRef.current) {
      return;
    }
    setState((prev) => {
      const nextMessages =
        Array.isArray(data.messages) && data.messages.length > 0
          ? [
            ...prev.messages,
            ...(data.messages as ChatMessage[]).filter(
              (msg) =>
                !prev.messages.some(
                  (existing) => existing.content === msg.content && existing.role === msg.role,
                ),
            ),
          ]
          : prev.messages;

      const nodeOutputs =
        data.node_outputs && typeof data.node_outputs === 'object'
          ? { ...prev.node_outputs, ...(data.node_outputs as ThreadStateView['node_outputs']) }
          : prev.node_outputs;

      return {
        ...prev,
        messages: nextMessages,
        node_outputs: nodeOutputs,
        phase:
          typeof data.phase === 'string'
            ? (data.phase as ThreadStateView['phase'])
            : prev.phase,
        active_node_id:
          typeof data.active_node_id === 'string' ? data.active_node_id : prev.active_node_id,
        last_assistant_message:
          typeof data.last_assistant_message === 'string'
            ? data.last_assistant_message
            : prev.last_assistant_message,
        hitl:
          data.hitl && typeof data.hitl === 'object'
            ? (data.hitl as ThreadStateView['hitl'])
            : prev.hitl,
      };
    });
  }, []);

  const handleStreamEvent = useCallback(
    (event: StreamEvent) => {
      if (!mountedRef.current) {
        return;
      }
      if (event.type === 'node') {
        setStatusLine(`执行：${event.node}`);
        patchFromNode(event.data);
        return;
      }
      if (event.type === 'agent') {
        setState((prev) => ({ ...prev, active_node_id: event.node }));
        toolEventSeq.current += 1;
        const item: ToolEvent = { ...event, id: toolEventSeq.current };
        setToolEvents((prev) => [...prev.slice(-199), item]);
        if (event.kind === 'tool_call') {
          setStatusLine(`${event.node}：调用 ${event.tool ?? '工具'}`);
        } else if (
          event.kind === 'tool_result'
          && event.tool === 'write_file'
          && typeof event.result === 'string'
          && event.result.toLowerCase().startsWith('[ok]')
        ) {
          void refreshWorkspaceFiles();
        } else if (event.kind === 'finish') {
          setStatusLine(`${event.node}：完成`);
        }
        return;
      }
      if (event.type === 'state') {
        applyState(event.data);
        return;
      }
      if (event.type === 'interrupt') {
        setState((prev) => ({
          ...prev,
          active_node_id:
            typeof event.data?.payload?.node_id === 'string'
              ? event.data.payload.node_id
              : prev.active_node_id,
          interrupted: true,
          interrupt: event.data ?? prev.interrupt,
        }));
        setBusy(false);
        setRunStartedAt(null);
        setStatusLine('等待人工确认');
        void refreshWorkspaceFiles();
        return;
      }
      if (event.type === 'error') {
        setError(event.message);
        setBusy(false);
        setRunStartedAt(null);
        setStatusLine('出错');
        return;
      }
      if (event.type === 'done') {
        setBusy(false);
        setRunStartedAt(null);
        setStatusLine('本轮完成');
        void refreshWorkspaceFiles();
      }
    },
    [applyState, patchFromNode, refreshWorkspaceFiles],
  );

  const startRun = useCallback(
    async (request: string) => {
      const text = request.trim();
      if (!text) {
        setError('缺少需求描述，无法启动流程');
        return;
      }
      const signal = beginStream();
      setBusy(true);
      setRunStartedAt(Date.now());
      setError(null);
      setStatusLine('启动流程');
      setToolEvents([]);
      setPreviewUrl('');
      setPreviewError(null);
      setPreviewOpen(false);
      setState({
        ...EMPTY_STATE,
        thread_id: threadId,
        user_request: text,
        messages: [{ role: 'user', content: text }],
      });
      try {
        await runThread(threadId, text, handleStreamEvent, signal);
      } catch (err) {
        if (!mountedRef.current || signal.aborted) {
          return;
        }
        setError(err instanceof Error ? err.message : '启动失败');
      } finally {
        if (mountedRef.current && !signal.aborted) {
          setBusy(false);
        }
      }
    },
    [beginStream, handleStreamEvent, threadId],
  );

  const loadThread = useCallback(
    async (id: string) => {
      setBusy(true);
      setError(null);
      try {
        const next = await getThread(id);
        if (!mountedRef.current) {
          return;
        }
        applyState(next);
        setPreviewUrl('');
        setPreviewError(null);
        setStatusLine(
          next.interrupted
            ? next.interrupt
              ? '等待人工确认'
              : next.can_retry
                ? '流程已中断，可重试当前节点'
                : '流程已中断'
            : PHASE_LABELS[next.phase],
        );

        const neverStarted = next.messages.length === 0 && !next.interrupted && !next.can_retry;
        if (neverStarted) {
          const request = (seedRequest || next.user_request || '').trim();
          if (request) {
            if (autoStartedThreadIds.has(id)) {
              return;
            }
            autoStartedThreadIds.add(id);
            await startRun(request);
            return;
          }
        }
      } catch (err) {
        if (!mountedRef.current) {
          return;
        }
        setError(err instanceof Error ? err.message : '加载失败');
      } finally {
        if (mountedRef.current) {
          setBusy(false);
        }
      }
    },
    [applyState, seedRequest, startRun],
  );

  useEffect(() => {
    void loadThread(threadId);
    return () => {
      abortRef.current?.abort();
    };
    // Only re-bootstrap when the opened run changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  const onResume = async (action: string) => {
    const signal = beginStream();
    setBusy(true);
    setRunStartedAt(Date.now());
    setError(null);
    setToolEvents([]);
    setState((prev) => ({
      ...prev,
      interrupted: false,
      interrupt: null,
    }));
    setStatusLine(`已提交：${action}`);
    try {
      await resumeThread(
        threadId,
        {
          action,
          message: replyText.trim() || undefined,
        },
        handleStreamEvent,
        signal,
      );
      if (!mountedRef.current || signal.aborted) {
        return;
      }
      setReplyText('');
    } catch (err) {
      if (!mountedRef.current || signal.aborted) {
        return;
      }
      setError(err instanceof Error ? err.message : '确认失败');
    } finally {
      if (mountedRef.current && !signal.aborted) {
        setBusy(false);
      }
    }
  };

  const onRetry = async () => {
    if (!state.can_retry) {
      return;
    }
    const signal = beginStream();
    setBusy(true);
    setRunStartedAt(Date.now());
    setError(null);
    setPreviewUrl('');
    setPreviewError(null);
    setStatusLine(`正在重试当前节点：${state.pending_nodes[0] ?? state.active_node_id}`);
    setState((prev) => ({
      ...prev,
      interrupted: false,
      can_retry: false,
      pending_nodes: [],
    }));
    try {
      await retryThread(threadId, handleStreamEvent, signal);
    } catch (err) {
      if (!mountedRef.current || signal.aborted) {
        return;
      }
      setError(err instanceof Error ? err.message : '重试失败');
      await loadThread(threadId);
    } finally {
      if (mountedRef.current && !signal.aborted) {
        setBusy(false);
      }
    }
  };

  const openFile = useCallback(
    async (path: string) => {
      setSelectedFile(path);
      setFileContent('');
      setFileError(null);
      try {
        const result = await readWorkspaceFile(threadId, path);
        if (mountedRef.current) {
          setFileContent(result.content);
        }
      } catch (err) {
        if (mountedRef.current) {
          setFileError(err instanceof Error ? err.message : '读取文件失败');
        }
      }
    },
    [threadId],
  );

  const ensurePreviewBuilt = useCallback(
    async (force = false) => {
      if (previewBusy) {
        return false;
      }
      if (previewUrl && !force) {
        return true;
      }
      setPreviewBusy(true);
      setPreviewError(null);
      try {
        const result = await buildPreview(threadId);
        setPreviewUrl(result.preview_url);
        return true;
      } catch (err) {
        setPreviewUrl('');
        setPreviewError(err instanceof Error ? err.message : '预览构建失败');
        return false;
      } finally {
        setPreviewBusy(false);
      }
    },
    [previewBusy, previewUrl, threadId],
  );

  const openPreviewFloat = useCallback(async () => {
    setPreviewOpen(true);
    await ensurePreviewBuilt(!previewUrl);
  }, [ensurePreviewBuilt, previewUrl]);

  useEffect(() => {
    if (!previewOpen) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPreviewOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [previewOpen]);

  const interruptOptions = state.interrupt?.options ?? [];
  const isSystemInterrupted = state.interrupted && !state.interrupt;
  const busyLabel = currentNodeId
    ? `正在执行：${nodeLabel(activeNode, roles) || currentNodeId}`
    : '正在与模型交互';

  const isMarkdownFile = selectedFile?.endsWith('.md') ?? false;

  return (
    <>
      <header className="bar">
        <div className="bar-left">
          <button
            type="button"
            className="btn ghost btn-icon"
            onClick={onBack}
            disabled={busy}
            aria-label="返回任务实例"
            title="返回任务实例"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true" className="btn-icon-svg">
              <path
                d="M14.5 5.5L8 12l6.5 6.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
          <nav className="flow" aria-label="流程节点">
            {stepperSteps.map((step, index) => {
              const status = stepStatus(step.id);
              return (
                <div key={step.id} className="flow-item">
                  {index > 0 ? <span className={`flow-edge ${status !== 'todo' ? 'active' : ''}`} /> : null}
                  <div className={`flow-node ${status}`}>
                    <span className="flow-index">{index + 1}</span>
                    <span className="flow-label">{step.label}</span>
                  </div>
                </div>
              );
            })}
          </nav>
        </div>
        <span className="meta">{statusLine}</span>
      </header>

      {error ? <div className="err">{error}</div> : null}

      <div className="layout">
        <section className="chat">
          <div className="msgs">
            {isSystemInterrupted ? (
              <div className="interrupted-card">
                <strong>本次流程已中断</strong>
                <p>
                  该会话在未完成节点时被服务重启或异常打断。
                  {state.can_retry
                    ? ` 可从当前节点继续：${state.pending_nodes.join(' -> ') || state.active_node_id}。`
                    : ' 当前没有可恢复的待执行节点。'}
                </p>
                <div className="actions">
                  {state.can_retry ? (
                    <button
                      type="button"
                      className="btn primary"
                      disabled={busy}
                      onClick={() => void onRetry()}
                    >
                      重试当前节点
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className={state.can_retry ? 'btn ghost' : 'btn primary'}
                    onClick={onBack}
                  >
                    返回任务实例
                  </button>
                </div>
              </div>
            ) : null}
            {state.messages.map((msg, index) => (
              <div key={`${msg.role}-${index}`} className={`msg ${msg.role}`}>
                <b>{msg.role === 'user' ? '你' : 'Agent'}</b>
                <p>{msg.content}</p>
              </div>
            ))}
            {toolEvents.map((event) => (
              <div key={event.id} className={`tool-event ${event.kind}`}>
                <span className="tool-event-node">{event.node}</span>
                <span className="tool-event-step">#{event.step}</span>
                <span className="tool-event-text">{toolEventText(event)}</span>
              </div>
            ))}
            {busy ? (
              <div className="loading-card">
                <div className="spinner" />
                <div>
                  <strong>{busyLabel}</strong>
                  <p>已等待 {elapsedSeconds}s，Agent 节点可能需要多步工具调用。</p>
                </div>
              </div>
            ) : null}
          </div>

          {state.interrupted && state.interrupt ? (
            <div className="gate">
              <h3>{state.interrupt.title}</h3>
              {state.interrupt.summary ? (
                <div className="md gate-summary">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {state.interrupt.summary}
                  </ReactMarkdown>
                </div>
              ) : null}
              <textarea
                value={replyText}
                onChange={(event) => setReplyText(event.target.value)}
                placeholder="补充说明 / 修订意见（可选）"
                rows={2}
              />
              <div className="actions">
                {interruptOptions.map((option, index) => (
                  <button
                    key={option}
                    type="button"
                    className={index === 0 ? 'btn primary' : 'btn'}
                    disabled={busy}
                    onClick={() => void onResume(option)}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <p className="hint">{busy ? '执行中…' : '等待操作'}</p>
          )}
        </section>

        <section className="artifacts">
          <div className="panel-toolbar workspace-toolbar">
            <span>工作区文件</span>
            <div className="mode-switch">
              <button
                type="button"
                className="mode-btn"
                onClick={() => void refreshWorkspaceFiles()}
              >
                刷新
              </button>
              <button
                type="button"
                className="mode-btn"
                onClick={() => void openPreviewFloat()}
              >
                预览
              </button>
            </div>
          </div>
          <div className="workspace-body">
            <div className="workspace-tree">
              {workspaceFiles.length === 0 ? (
                <p className="hint">暂无文件</p>
              ) : (
                workspaceFiles.map((path) => (
                  <button
                    key={path}
                    type="button"
                    className={selectedFile === path ? 'workspace-file on' : 'workspace-file'}
                    onClick={() => void openFile(path)}
                  >
                    {path}
                  </button>
                ))
              )}
            </div>
            <div className="workspace-viewer">
              {fileError ? (
                <div className="err">{fileError}</div>
              ) : selectedFile ? (
                isMarkdownFile ? (
                  <div className="md">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {fileContent || '_空文件_'}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <pre className="markdown-source">{fileContent || '_空文件_'}</pre>
                )
              ) : (
                <p className="hint">选择左侧文件查看内容</p>
              )}
            </div>
          </div>
        </section>
      </div>

      {previewOpen ? (
        <div className="preview-float" role="dialog" aria-modal="true" aria-label="页面预览">
          <button
            type="button"
            className="preview-float-mask"
            aria-label="关闭预览"
            onClick={() => setPreviewOpen(false)}
          />
          <div className="preview-float-panel">
            <div className="preview-toolbar">
              <div className="preview-toolbar-left">
                <strong className="preview-float-title">实时预览</strong>
                <div className="device-switch" role="group" aria-label="预览设备">
                  <button
                    type="button"
                    className={previewDevice === 'mobile' ? 'device-btn on' : 'device-btn'}
                    onClick={() => setPreviewDevice('mobile')}
                  >
                    <span className="device-icon mobile" aria-hidden="true" />
                    手机
                  </button>
                  <button
                    type="button"
                    className={previewDevice === 'desktop' ? 'device-btn on' : 'device-btn'}
                    onClick={() => setPreviewDevice('desktop')}
                  >
                    <span className="device-icon desktop" aria-hidden="true" />
                    PC
                  </button>
                </div>
              </div>
              <div className="preview-toolbar-right">
                {previewUrl ? (
                  <a
                    className="preview-action"
                    href={previewUrl}
                    target="_blank"
                    rel="noreferrer"
                  >
                    新窗口
                  </a>
                ) : null}
                <button
                  type="button"
                  className="preview-action solid"
                  disabled={previewBusy}
                  onClick={() => void ensurePreviewBuilt(true)}
                >
                  {previewBusy ? '构建中' : '重新构建'}
                </button>
                <button
                  type="button"
                  className="preview-action"
                  onClick={() => setPreviewOpen(false)}
                >
                  关闭
                </button>
              </div>
            </div>

            <div className={`preview-stage float ${previewDevice}`}>
              {previewBusy && !previewUrl ? (
                <div className="preview-empty">
                  <div className="spinner" />
                  <span>正在打包并构建预览…</span>
                </div>
              ) : previewError && !previewUrl ? (
                <div className="preview-empty">{previewError}</div>
              ) : previewUrl ? (
                <div className={`preview-device ${previewDevice}`}>
                  {previewDevice === 'mobile' ? <div className="preview-notch" /> : null}
                  <iframe
                    title="Code preview"
                    className="preview-frame"
                    sandbox="allow-scripts allow-same-origin allow-forms allow-modals"
                    src={previewUrl}
                  />
                </div>
              ) : (
                <div className="preview-empty">暂无可预览内容</div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
