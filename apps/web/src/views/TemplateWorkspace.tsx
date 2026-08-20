import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { RoleDef, ThreadSummary, WorkflowDef, WorkflowNode } from '@workflow-agent/shared';
import {
  ApiError,
  createWorkflowRun,
  deleteThread,
  deleteWorkflow,
  duplicateWorkflow,
  getWorkflow,
  listRoles,
  listWorkflowRuns,
  updateWorkflow,
} from '../api';
import { showToast } from '../components/toast';
import EdgeConfigPanel from '../editor/EdgeConfigPanel';
import NodeConfigPanel from '../editor/NodeConfigPanel';
import WorkflowCanvas from '../editor/WorkflowCanvas';
import { workflowContentSignature } from '../editor/workflowSignature';
import { formatDateTime } from '../utils/formatDateTime';
import {
  errorNodeIds,
  formatValidationErrors,
  parseApiValidationDetail,
  validateWorkflowClient,
  type WorkflowValidationError,
} from '../editor/validateWorkflow';

type Props = {
  workflowId: string;
  tab: 'editor' | 'runs';
  onTabChange: (tab: 'editor' | 'runs') => void;
  onOpenRun: (threadId: string, seedRequest?: string) => void;
  onWorkflowsChanged: (selectId?: string) => void;
};

export default function TemplateWorkspace({
  workflowId,
  tab,
  onTabChange,
  onOpenRun,
  onWorkflowsChanged,
}: Props) {
  const [workflow, setWorkflow] = useState<WorkflowDef | null>(null);
  const [runs, setRuns] = useState<ThreadSummary[]>([]);
  const [roles, setRoles] = useState<RoleDef[]>([]);
  const [userRequest, setUserRequest] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<WorkflowValidationError[]>([]);
  const [configCollapsed, setConfigCollapsed] = useState(false);
  const savedSnapshotRef = useRef('');
  const ignoreCanvasSyncRef = useRef(false);

  const syncDirtyState = useCallback((next: WorkflowDef) => {
    setDirty(workflowContentSignature(next) !== savedSnapshotRef.current);
  }, []);

  const errorIds = useMemo(() => errorNodeIds(validationErrors), [validationErrors]);
  const errorMessagesByNode = useMemo(() => {
    const map: Record<string, string> = {};
    for (const error of validationErrors) {
      if (!error.node_id) {
        continue;
      }
      map[error.node_id] = map[error.node_id]
        ? `${map[error.node_id]}；${error.message}`
        : error.message;
    }
    return map;
  }, [validationErrors]);

  const applyValidationErrors = useCallback((errors: WorkflowValidationError[]) => {
    setValidationErrors(errors);
    if (errors.length === 0) {
      setError(null);
    } else {
      setError(formatValidationErrors(errors));
    }
  }, []);

  const loadWorkflow = useCallback(async () => {
    setError(null);
    setDirty(false);
    setSelectedNodeId(null);
    setValidationErrors([]);
    try {
      const loaded = await getWorkflow(workflowId);
      savedSnapshotRef.current = workflowContentSignature(loaded);
      setWorkflow(loaded);
      setDirty(false);
    } catch (err) {
      setWorkflow(null);
      setError(err instanceof Error ? err.message : '加载工作流失败');
    }
  }, [workflowId]);

  const loadRuns = useCallback(async () => {
    try {
      setRuns(await listWorkflowRuns(workflowId));
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载任务实例失败');
    }
  }, [workflowId]);

  useEffect(() => {
    void loadWorkflow();
  }, [loadWorkflow]);

  useEffect(() => {
    listRoles()
      .then(setRoles)
      .catch(() => setRoles([]));
  }, []);

  useEffect(() => {
    if (tab === 'runs') {
      void loadRuns();
    }
  }, [tab, loadRuns]);

  const builtin = workflow?.builtin ?? true;
  const readOnly = builtin;

  const selectedNode: WorkflowNode | null = useMemo(() => {
    if (!workflow || !selectedNodeId) {
      return null;
    }
    return workflow.nodes.find((node) => node.id === selectedNodeId) ?? null;
  }, [workflow, selectedNodeId]);

  const selectedEdge = useMemo(() => {
    if (!workflow || !selectedEdgeId) {
      return null;
    }
    return workflow.edges.find((edge) => edge.id === selectedEdgeId) ?? null;
  }, [workflow, selectedEdgeId]);

  const onDuplicate = async () => {
    setBusy(true);
    setError(null);
    try {
      const copy = await duplicateWorkflow(workflowId);
      showToast('复制成功');
      onWorkflowsChanged(copy.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '复制失败');
      showToast(err instanceof Error ? err.message : '复制失败', 'error');
    } finally {
      setBusy(false);
    }
  };

  const onSave = async () => {
    if (!workflow || workflow.builtin) {
      return;
    }
    const clientErrors = validateWorkflowClient(workflow);
    if (clientErrors.length > 0) {
      applyValidationErrors(clientErrors);
      showToast('校验未通过，无法保存', 'error');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await updateWorkflow(workflow.id, {
        name: workflow.name,
        description: workflow.description,
        nodes: workflow.nodes,
        edges: workflow.edges,
        viewport: workflow.viewport,
      });
      ignoreCanvasSyncRef.current = true;
      savedSnapshotRef.current = workflowContentSignature(next);
      setWorkflow(next);
      setDirty(false);
      setValidationErrors([]);
      showToast('保存成功');
      onWorkflowsChanged();
      window.setTimeout(() => {
        ignoreCanvasSyncRef.current = false;
      }, 300);
    } catch (err) {
      if (err instanceof ApiError) {
        const structured = parseApiValidationDetail(err.detail);
        if (structured && structured.length > 0) {
          applyValidationErrors(structured);
          showToast('校验未通过，无法保存', 'error');
        } else {
          setError(err.message);
          showToast(err.message, 'error');
        }
      } else {
        const message = err instanceof Error ? err.message : '保存失败';
        setError(message);
        showToast(message, 'error');
      }
    } finally {
      setBusy(false);
    }
  };

  const onValidate = () => {
    if (!workflow) {
      return;
    }
    const errors = validateWorkflowClient(workflow);
    applyValidationErrors(errors);
    if (errors.length === 0) {
      showToast('校验通过');
    } else {
      showToast('校验未通过', 'error');
    }
  };

  const onDelete = async () => {
    if (!workflow || workflow.builtin) {
      return;
    }
    const confirmed = window.confirm(`确定删除工作流「${workflow.name}」？`);
    if (!confirmed) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteWorkflow(workflow.id);
      showToast('删除成功');
      onWorkflowsChanged();
    } catch (err) {
      const message = err instanceof Error ? err.message : '删除失败';
      setError(message);
      showToast(message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const onCreateRun = async () => {
    const text = userRequest.trim();
    if (!text) {
      setError('请先输入需求描述');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const threadId = await createWorkflowRun(workflowId, text);
      setUserRequest('');
      onOpenRun(threadId, text);
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建任务失败');
    } finally {
      setBusy(false);
    }
  };

  const onDeleteRun = async (threadId: string, title: string) => {
    const confirmed = window.confirm(`确定删除任务实例「${title}」？`);
    if (!confirmed) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteThread(threadId);
      setRuns((current) => current.filter((item) => item.thread_id !== threadId));
      showToast('实例删除成功');
    } catch (err) {
      const message = err instanceof Error ? err.message : '删除任务实例失败';
      setError(message);
      showToast(message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const onCanvasChange = useCallback(
    (next: {
      nodes: WorkflowDef['nodes'];
      edges: WorkflowDef['edges'];
      viewport?: WorkflowDef['viewport'];
    }) => {
      if (ignoreCanvasSyncRef.current) {
        return;
      }
      setWorkflow((current) => {
        if (!current || current.builtin) {
          return current;
        }
        const updated = {
          ...current,
          nodes: next.nodes,
          edges: next.edges,
          viewport: next.viewport ?? current.viewport,
        };
        syncDirtyState(updated);
        return updated;
      });
      setSelectedNodeId((currentId) => {
        if (!currentId) {
          return currentId;
        }
        return next.nodes.some((node) => node.id === currentId) ? currentId : null;
      });
    },
    [syncDirtyState],
  );

  const onNodeConfigChange = useCallback(
    (nodeId: string, patch: { data?: Record<string, unknown> }) => {
      setWorkflow((current) => {
        if (!current || current.builtin) {
          return current;
        }
        const updated = {
          ...current,
          nodes: current.nodes.map((node) =>
            node.id === nodeId
              ? { ...node, data: patch.data ?? node.data }
              : node,
          ),
        };
        syncDirtyState(updated);
        return updated;
      });
    },
    [syncDirtyState],
  );

  const onDeleteNode = useCallback((nodeId: string) => {
    setSelectedNodeId((current) => (current === nodeId ? null : current));
    setWorkflow((current) => {
      if (!current || current.builtin) {
        return current;
      }
      const target = current.nodes.find((node) => node.id === nodeId);
      if (!target || target.type === 'start' || target.type === 'end') {
        return current;
      }
      const updated = {
        ...current,
        nodes: current.nodes.filter((node) => node.id !== nodeId),
        edges: current.edges.filter(
          (edge) => edge.source !== nodeId && edge.target !== nodeId,
        ),
      };
      syncDirtyState(updated);
      return updated;
    });
  }, [syncDirtyState]);

  const onNameChange = (name: string) => {
    setWorkflow((current) => {
      if (!current || current.builtin) {
        return current;
      }
      const updated = { ...current, name };
      syncDirtyState(updated);
      return updated;
    });
  };

  const handleSelectNode = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
    if (nodeId) {
      setSelectedEdgeId(null);
      setConfigCollapsed(false);
    }
  }, []);

  const handleSelectEdge = useCallback((edgeId: string | null) => {
    setSelectedEdgeId(edgeId);
    if (edgeId) {
      setSelectedNodeId(null);
      setConfigCollapsed(false);
    }
  }, []);

  const onEdgeConfigChange = useCallback(
    (edgeId: string, patch: Partial<WorkflowDef['edges'][number]>) => {
      setWorkflow((current) => {
        if (!current || current.builtin) {
          return current;
        }
        const updated = {
          ...current,
          edges: current.edges.map((edge) =>
            edge.id === edgeId ? { ...edge, ...patch } : edge,
          ),
        };
        syncDirtyState(updated);
        return updated;
      });
    },
    [syncDirtyState],
  );

  const onDeleteEdge = useCallback(
    (edgeId: string) => {
      setSelectedEdgeId((current) => (current === edgeId ? null : current));
      setWorkflow((current) => {
        if (!current || current.builtin) {
          return current;
        }
        const updated = {
          ...current,
          edges: current.edges.filter((edge) => edge.id !== edgeId),
        };
        syncDirtyState(updated);
        return updated;
      });
    },
    [syncDirtyState],
  );

  return (
    <div className="workspace">
      <header className="bar workspace-bar">
        <div className="workspace-title">
          {workflow && !builtin ? (
            <input
              className="workspace-name-input"
              value={workflow.name}
              disabled={busy}
              onChange={(event) => onNameChange(event.target.value)}
              aria-label="工作流名称"
            />
          ) : (
            <h1>{workflow?.name || '加载中…'}</h1>
          )}
          {builtin ? <span className="badge">内置</span> : null}
          {dirty && !builtin ? <span className="badge tiny">未保存</span> : null}
        </div>
        <div className="workspace-actions">
          <button type="button" className="btn" disabled={busy} onClick={() => void onDuplicate()}>
            复制
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy || !workflow}
            onClick={onValidate}
          >
            校验
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy || builtin || !dirty}
            title={builtin ? '内置模板不可保存' : !dirty ? '没有未保存的更改' : undefined}
            onClick={() => void onSave()}
          >
            保存
          </button>
          <button
            type="button"
            className="btn ghost"
            disabled={busy || builtin}
            title={builtin ? '内置模板不可删除' : undefined}
            onClick={() => void onDelete()}
          >
            删除
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={busy}
            onClick={() => onTabChange('runs')}
          >
            新建任务
          </button>
        </div>
      </header>

      <div className="workspace-tabs" role="tablist" aria-label="工作流视图">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'editor'}
          className={tab === 'editor' ? 'ws-tab on' : 'ws-tab'}
          onClick={() => onTabChange('editor')}
        >
          编排
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'runs'}
          className={tab === 'runs' ? 'ws-tab on' : 'ws-tab'}
          onClick={() => onTabChange('runs')}
        >
          任务实例
        </button>
      </div>

      {error ? <div className="err">{error}</div> : null}

      {tab === 'editor' ? (
        <section className="workspace-panel editor-panel">
          {!workflow ? (
            <p className="hint">加载工作流…</p>
          ) : (
            <div
              className={[
                'editor-layout',
                configCollapsed ? 'config-collapsed' : '',
              ]
                .filter(Boolean)
                .join(' ')}
            >
              <WorkflowCanvas
                workflow={workflow}
                readOnly={readOnly}
                onChange={onCanvasChange}
                onSelectNode={handleSelectNode}
                onSelectEdge={handleSelectEdge}
                errorNodeIds={errorIds}
                errorMessagesByNode={errorMessagesByNode}
              />
              <div className={`editor-side editor-side-right${configCollapsed ? ' is-collapsed' : ''}`}>
                <button
                  type="button"
                  className="side-collapse-btn"
                  aria-expanded={!configCollapsed}
                  aria-label={configCollapsed ? '展开节点配置' : '收起节点配置'}
                  title={configCollapsed ? '展开节点配置' : '收起节点配置'}
                  onClick={() => setConfigCollapsed((value) => !value)}
                >
                  {configCollapsed ? '‹' : '›'}
                </button>
                {!configCollapsed ? (
                  selectedEdge && !selectedNode ? (
                    <EdgeConfigPanel
                      selected={selectedEdge}
                      readOnly={readOnly}
                      onChange={onEdgeConfigChange}
                      onDelete={onDeleteEdge}
                    />
                  ) : (
                    <NodeConfigPanel
                      selected={selectedNode}
                      readOnly={readOnly}
                      roles={roles}
                      onChange={onNodeConfigChange}
                      onDelete={onDeleteNode}
                    />
                  )
                ) : null}
              </div>
            </div>
          )}
        </section>
      ) : (
        <section className="workspace-panel runs-panel">
          <div className="run-create">
            <h2>新建任务实例</h2>
            <textarea
              value={userRequest}
              onChange={(event) => setUserRequest(event.target.value)}
              placeholder="例如：做一个工单助手…"
              rows={4}
            />
            <button
              type="button"
              className="btn primary"
              disabled={busy}
              onClick={() => void onCreateRun()}
            >
              {busy ? '创建中…' : '启动流程'}
            </button>
          </div>

          <div className="run-list">
            <h2>历史实例</h2>
            {runs.length === 0 ? (
              <p className="hint">暂无任务实例</p>
            ) : (
              runs.map((item) => (
                <div key={item.thread_id} className="run-item">
                  <button
                    type="button"
                    className="run-item-main"
                    disabled={busy}
                    title={item.title}
                    onClick={() => onOpenRun(item.thread_id)}
                  >
                    <span className="run-item-title">{item.title}</span>
                    <span className="run-item-meta">{formatDateTime(item.updated_at)}</span>
                  </button>
                  <button
                    type="button"
                    className="run-item-delete"
                    disabled={busy}
                    aria-label={`删除任务实例 ${item.title}`}
                    title="删除任务实例"
                    onClick={() => void onDeleteRun(item.thread_id, item.title)}
                  >
                    删除
                  </button>
                </div>
              ))
            )}
          </div>
        </section>
      )}
    </div>
  );
}
