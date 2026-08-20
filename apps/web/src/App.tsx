import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import type { WorkflowSummary } from '@workflow-agent/shared';
import { createWorkflow, listWorkflows } from './api';
import { ToastHost } from './components/toast';

const RolesManager = lazy(() => import('./views/RolesManager'));
const RunDetail = lazy(() => import('./views/RunDetail'));
const TemplateWorkspace = lazy(() => import('./views/TemplateWorkspace'));

type View =
  | { kind: 'workspace'; workflowId: string; tab: 'editor' | 'runs' }
  | { kind: 'run'; workflowId: string; threadId: string; seedRequest?: string }
  | { kind: 'roles' };

const PREFERRED_WORKFLOW_ID = 'dev_delivery';

export default function App() {
  const [workflows, setWorkflows] = useState<WorkflowSummary[]>([]);
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sideCollapsed, setSideCollapsed] = useState(false);

  const refreshWorkflows = useCallback(async (selectId?: string) => {
    try {
      const items = await listWorkflows();
      setWorkflows(items);
      setView((prev) => {
        if (selectId) {
          return { kind: 'workspace', workflowId: selectId, tab: 'editor' };
        }
        if (prev?.kind === 'workspace' || prev?.kind === 'run') {
          const stillExists = items.some((item) => item.id === prev.workflowId);
          if (stillExists) {
            return prev;
          }
        }
        if (items.length === 0) {
          return null;
        }
        const preferred =
          items.find((item) => item.id === PREFERRED_WORKFLOW_ID) ?? items[0];
        return { kind: 'workspace', workflowId: preferred.id, tab: 'editor' };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载工作流失败');
    }
  }, []);

  useEffect(() => {
    void refreshWorkflows();
  }, [refreshWorkflows]);

  const onCreateWorkflow = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await createWorkflow({ name: '未命名工作流' });
      await refreshWorkflows(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建工作流失败');
    } finally {
      setBusy(false);
    }
  };

  const selectedWorkflowId =
    view?.kind === 'workspace' || view?.kind === 'run' ? view.workflowId : null;

  return (
    <div className={`shell${sideCollapsed ? ' side-collapsed' : ''}`}>
      <ToastHost />
      <aside className={`side${sideCollapsed ? ' is-collapsed' : ''}`}>
        {!sideCollapsed ? (
          <>
            <div className="brand">
              <strong>Multi-Agent Workflow</strong>
              <span>编排多 Agent 任务流</span>
            </div>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => void onCreateWorkflow()}
            >
              + 新建任务流
            </button>
            <div className="thread-list workflow-list">
              {workflows.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={selectedWorkflowId === item.id ? 'thread on' : 'thread'}
                  disabled={busy}
                  title={item.name}
                  onClick={() =>
                    setView({ kind: 'workspace', workflowId: item.id, tab: 'editor' })
                  }
                >
                  <span className="workflow-name">{item.name}</span>
                  {item.builtin ? <span className="badge tiny">内置</span> : null}
                </button>
              ))}
            </div>
            <button
              type="button"
              className={view?.kind === 'roles' ? 'thread on' : 'thread'}
              disabled={busy}
              onClick={() => setView({ kind: 'roles' })}
            >
              <span className="workflow-name">角色管理</span>
            </button>
          </>
        ) : null}
        <button
          type="button"
          className="rail-toggle"
          aria-expanded={!sideCollapsed}
          aria-label={sideCollapsed ? '展开工作流列表' : '收起工作流列表'}
          title={sideCollapsed ? '展开' : '收起'}
          onClick={() => setSideCollapsed((value) => !value)}
        >
          {sideCollapsed ? '›' : '‹'}
        </button>
      </aside>

      <main className="main">
        {error ? <div className="err">{error}</div> : null}

        <Suspense fallback={<section className="start">加载模块中…</section>}>
          {!view ? (
            <section className="start">
              <p className="eyebrow">Multi-Agent Orchestration</p>
              <h1>Multi-Agent Workflow</h1>
              <p>暂无工作流，点击左侧「+ 新建」创建一个。</p>
            </section>
          ) : view.kind === 'roles' ? (
            <RolesManager />
          ) : view.kind === 'workspace' ? (
            <TemplateWorkspace
              workflowId={view.workflowId}
              tab={view.tab}
              onTabChange={(tab) =>
                setView({ kind: 'workspace', workflowId: view.workflowId, tab })
              }
              onOpenRun={(threadId, seedRequest) =>
                setView({
                  kind: 'run',
                  workflowId: view.workflowId,
                  threadId,
                  seedRequest,
                })
              }
              onWorkflowsChanged={(selectId?: string) => {
                void refreshWorkflows(selectId);
              }}
            />
          ) : (
            <RunDetail
              threadId={view.threadId}
              seedRequest={view.seedRequest}
              onBack={() =>
                setView({
                  kind: 'workspace',
                  workflowId: view.workflowId,
                  tab: 'runs',
                })
              }
            />
          )}
        </Suspense>
      </main>
    </div>
  );
}
