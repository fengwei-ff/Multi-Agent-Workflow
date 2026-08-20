import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type OnSelectionChangeParams,
  type Viewport,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type {
  WorkflowDef,
  WorkflowEdge,
  WorkflowNode,
  WorkflowNodeType,
  WorkflowViewport,
} from '@workflow-agent/shared';
import {
  HandleInteractContext,
  type HandleAnchor,
} from './HandleInteractContext';
import NodePicker from './NodePicker';
import SelectableEdge from './SelectableEdge';
import { NODE_TYPE_LABELS, nodeTypes, type WorkflowRfData } from './nodeTypes';

const edgeTypes = {
  selectable: SelectableEdge,
};

type CanvasChange = {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  viewport?: WorkflowViewport;
};

type Props = {
  workflow: WorkflowDef;
  readOnly: boolean;
  onChange: (next: CanvasChange) => void;
  onSelectNode?: (nodeId: string | null) => void;
  onSelectEdge?: (edgeId: string | null) => void;
  errorNodeIds?: string[];
  errorMessagesByNode?: Record<string, string>;
};

type PendingAdd = {
  screenX: number;
  screenY: number;
  flowX: number;
  flowY: number;
  fromNodeId: string;
  fromHandleId: string | null;
  fromHandleType: 'source' | 'target';
};

function newId(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}_${crypto.randomUUID()}`;
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function defaultNodeData(type: WorkflowNodeType): Record<string, unknown> {
  switch (type) {
    case 'agent':
      return {
        role_id: '',
        task_template: '{user_request}',
        title: NODE_TYPE_LABELS.agent,
      };
    case 'hitl':
      return {
        title: NODE_TYPE_LABELS.hitl,
        options: ['approve', 'reject'],
        summary_fields: [],
      };
    default:
      return { title: NODE_TYPE_LABELS[type] };
  }
}

function toRfData(
  node: WorkflowNode,
  errorNodeIds?: Set<string>,
  errorMessagesByNode?: Record<string, string>,
): WorkflowRfData {
  const data: WorkflowRfData = { ...(node.data ?? {}) };
  if (errorNodeIds?.has(node.id)) {
    data._hasError = true;
    data._errorMessage = errorMessagesByNode?.[node.id] || '校验失败';
  }
  return data;
}

function stripRfData(data: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!data) {
    return {};
  }
  const next = { ...data };
  delete next._hasError;
  delete next._errorMessage;
  return next;
}

function toRfNodes(
  workflow: WorkflowDef,
  errorNodeIds?: Set<string>,
  errorMessagesByNode?: Record<string, string>,
): Node[] {
  return workflow.nodes.map((node) => ({
    id: node.id,
    type: node.type,
    position: { ...node.position },
    data: toRfData(node, errorNodeIds, errorMessagesByNode),
  }));
}

function edgeLabel(edge: WorkflowEdge): string {
  if (edge.label) {
    return edge.label;
  }
  if (edge.condition) {
    const value =
      edge.condition.value === undefined || edge.condition.value === null
        ? ''
        : ` ${JSON.stringify(edge.condition.value)}`;
    return `${edge.condition.left} ${edge.condition.op}${value}`;
  }
  return 'default';
}

function toRfEdges(
  workflow: WorkflowDef,
  onDeleteEdge?: (edgeId: string) => void,
): Edge[] {
  return workflow.edges.map((edge) => ({
    id: edge.id,
    type: 'selectable',
    source: edge.source,
    target: edge.target,
    label: edgeLabel(edge),
    data: {
      condition: edge.condition ?? null,
      max_iterations: edge.max_iterations ?? null,
      label: edge.label ?? undefined,
      onDeleteEdge,
    },
  }));
}

function fromRfNodes(nodes: Node[]): WorkflowNode[] {
  return nodes.map((node) => ({
    id: node.id,
    type: (node.type || 'agent') as WorkflowNodeType,
    position: { x: node.position.x, y: node.position.y },
    data: stripRfData(node.data as Record<string, unknown> | undefined),
  }));
}

function fromRfEdges(edges: Edge[]): WorkflowEdge[] {
  return edges.map((edge) => {
    const data = (edge.data ?? {}) as Record<string, unknown>;
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      condition: (data.condition as WorkflowEdge['condition']) ?? null,
      max_iterations: (data.max_iterations as number | null | undefined) ?? null,
      label: typeof data.label === 'string' ? data.label : undefined,
    };
  });
}

function graphStructureSignature(nodes: WorkflowNode[], edges: WorkflowEdge[]): string {
  return JSON.stringify({
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.type,
      position: node.position,
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      condition: edge.condition ?? null,
      max_iterations: edge.max_iterations ?? null,
      label: edge.label ?? null,
    })),
  });
}

function mergeNodesFromWorkflow(
  current: Node[],
  workflow: WorkflowDef,
  errorIdSet: Set<string>,
  errorMessagesByNode?: Record<string, string>,
): Node[] {
  const workflowById = new Map(workflow.nodes.map((node) => [node.id, node]));
  const seen = new Set<string>();
  const merged = current.map((node) => {
    const wfNode = workflowById.get(node.id);
    if (!wfNode) {
      return node;
    }
    seen.add(node.id);
    return {
      ...node,
      type: wfNode.type,
      position: { ...wfNode.position },
      data: toRfData(wfNode, errorIdSet, errorMessagesByNode),
    };
  });
  for (const wfNode of workflow.nodes) {
    if (seen.has(wfNode.id)) {
      continue;
    }
    merged.push({
      id: wfNode.id,
      type: wfNode.type,
      position: { ...wfNode.position },
      data: toRfData(wfNode, errorIdSet, errorMessagesByNode),
    });
  }
  return merged;
}

function toWorkflowViewport(viewport: Viewport): WorkflowViewport {
  return { x: viewport.x, y: viewport.y, zoom: viewport.zoom };
}

function CanvasInner({
  workflow,
  readOnly,
  onChange,
  onSelectNode,
  onSelectEdge,
  errorNodeIds,
  errorMessagesByNode,
}: Props) {
  const errorIdSet = useMemo(
    () => new Set(errorNodeIds ?? []),
    [errorNodeIds],
  );
  const { screenToFlowPosition, getViewport } = useReactFlow();
  const [nodes, setNodes] = useState<Node[]>(() =>
    toRfNodes(workflow, errorIdSet, errorMessagesByNode),
  );
  const [edges, setEdges] = useState<Edge[]>(() => toRfEdges(workflow));
  const [pendingAdd, setPendingAdd] = useState<PendingAdd | null>(null);
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  const lastEmittedStructureSig = useRef(
    graphStructureSignature(workflow.nodes, workflow.edges),
  );
  const emitTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);

  const structureSig = useMemo(
    () => graphStructureSignature(workflow.nodes, workflow.edges),
    [workflow.nodes, workflow.edges],
  );

  nodesRef.current = nodes;
  edgesRef.current = edges;

  const cancelPendingEmit = useCallback(() => {
    if (emitTimer.current) {
      clearTimeout(emitTimer.current);
      emitTimer.current = null;
    }
  }, []);

  const emitChange = useCallback(
    (nextNodes: Node[], nextEdges: Edge[], viewport?: WorkflowViewport) => {
      const workflowNodes = fromRfNodes(nextNodes);
      const workflowEdges = fromRfEdges(nextEdges);
      lastEmittedStructureSig.current = graphStructureSignature(
        workflowNodes,
        workflowEdges,
      );
      if (emitTimer.current) {
        clearTimeout(emitTimer.current);
      }
      emitTimer.current = setTimeout(() => {
        onChange({
          nodes: workflowNodes,
          edges: workflowEdges,
          viewport: viewport ?? toWorkflowViewport(getViewport()),
        });
        emitTimer.current = null;
      }, 80);
    },
    [getViewport, onChange],
  );

  const deleteEdgeById = useCallback(
    (edgeId: string) => {
      setEdges((current) => {
        const next = current.filter((edge) => edge.id !== edgeId);
        if (next.length === current.length) {
          return current;
        }
        emitChange(nodesRef.current, next);
        return next;
      });
    },
    [emitChange],
  );

  useEffect(() => {
    cancelPendingEmit();

    if (structureSig === lastEmittedStructureSig.current) {
      setNodes((current) =>
        mergeNodesFromWorkflow(current, workflow, errorIdSet, errorMessagesByNode),
      );
      setEdges((current) => {
        const selectedIds = new Set(
          current.filter((edge) => edge.selected).map((edge) => edge.id),
        );
        return toRfEdges(workflow, deleteEdgeById).map((edge) =>
          selectedIds.has(edge.id) ? { ...edge, selected: true } : edge,
        );
      });
      return;
    }

    lastEmittedStructureSig.current = structureSig;
    const nextNodes = toRfNodes(workflow, errorIdSet, errorMessagesByNode);
    const nextEdges = toRfEdges(workflow, deleteEdgeById);
    setNodes((current) => {
      const selectedIds = new Set(
        current.filter((node) => node.selected).map((node) => node.id),
      );
      return nextNodes.map((node) =>
        selectedIds.has(node.id) ? { ...node, selected: true } : node,
      );
    });
    setEdges(nextEdges);
  }, [
    cancelPendingEmit,
    structureSig,
    workflow,
    errorIdSet,
    errorMessagesByNode,
    deleteEdgeById,
  ]);

  useEffect(() => {
    return () => {
      cancelPendingEmit();
    };
  }, [cancelPendingEmit]);

  useEffect(() => {
    if (!pendingAdd) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPendingAdd(null);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [pendingAdd]);

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      if (readOnly) {
        const allowed = changes.filter(
          (change) => change.type === 'select' || change.type === 'dimensions',
        );
        if (allowed.length === 0) {
          return;
        }
        setNodes((current) => applyNodeChanges(allowed, current));
        return;
      }
      setNodes((current) => {
        const protectedIds = new Set(
          current
            .filter((node) => node.type === 'start' || node.type === 'end')
            .map((node) => node.id),
        );
        const allowed = changes.filter(
          (change) =>
            change.type !== 'remove' || !protectedIds.has(change.id),
        );
        if (allowed.length === 0) {
          return current;
        }
        const next = applyNodeChanges(allowed, current);
        emitChange(next, edgesRef.current);
        return next;
      });
    },
    [emitChange, readOnly],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      if (readOnly) {
        const allowed = changes.filter((change) => change.type === 'select');
        if (allowed.length === 0) {
          return;
        }
        setEdges((current) => applyEdgeChanges(allowed, current));
        return;
      }
      setEdges((current) => {
        const next = applyEdgeChanges(changes, current);
        emitChange(nodesRef.current, next);
        return next;
      });
    },
    [emitChange, readOnly],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (readOnly || !connection.source || !connection.target) {
        return;
      }
      setPendingAdd(null);
      setEdges((current) => {
        const next = addEdge({ ...connection, id: newId('e') }, current);
        emitChange(nodesRef.current, next);
        return next;
      });
    },
    [emitChange, readOnly],
  );

  const openPicker = useCallback(
    (anchor: HandleAnchor) => {
      if (readOnly) {
        return;
      }
      const flow = screenToFlowPosition({ x: anchor.clientX, y: anchor.clientY });
      const rect = canvasRef.current?.getBoundingClientRect();
      setPendingAdd({
        screenX: rect ? anchor.clientX - rect.left : anchor.clientX,
        screenY: rect ? anchor.clientY - rect.top : anchor.clientY,
        flowX: flow.x,
        flowY: flow.y,
        fromNodeId: anchor.nodeId,
        fromHandleId: anchor.handleId,
        fromHandleType: anchor.handleType,
      });
    },
    [readOnly, screenToFlowPosition],
  );

  const handleInteract = useMemo(
    () => ({
      openPicker,
      readOnly,
    }),
    [openPicker, readOnly],
  );

  const onPickNodeType = useCallback(
    (type: WorkflowNodeType) => {
      if (!pendingAdd) {
        return;
      }
      const id = newId(type);
      const offsetX = pendingAdd.fromHandleType === 'source' ? 24 : -140;
      const position = {
        x: pendingAdd.flowX + offsetX,
        y: pendingAdd.flowY - 18,
      };
      const created: WorkflowNode = {
        id,
        type,
        position,
        data: defaultNodeData(type),
      };
      const nextNode: Node = {
        id,
        type,
        position,
        data: toRfData(created, errorIdSet, errorMessagesByNode),
        selected: true,
      };

      const connection: Connection =
        pendingAdd.fromHandleType === 'source'
          ? {
              source: pendingAdd.fromNodeId,
              target: id,
              sourceHandle: pendingAdd.fromHandleId,
              targetHandle: null,
            }
          : {
              source: id,
              target: pendingAdd.fromNodeId,
              sourceHandle: null,
              targetHandle: pendingAdd.fromHandleId,
            };

      const nextNodes = [
        ...nodesRef.current.map((node) => ({ ...node, selected: false })),
        nextNode,
      ];
      const nextEdges = addEdge({ ...connection, id: newId('e') }, edgesRef.current);
      setNodes(nextNodes);
      setEdges(nextEdges);
      emitChange(nextNodes, nextEdges);
      onSelectNode?.(id);
      setPendingAdd(null);
    },
    [emitChange, errorIdSet, errorMessagesByNode, onSelectNode, pendingAdd],
  );

  const onSelectionChange = useCallback(
    ({ nodes: selectedNodes, edges: selectedEdges }: OnSelectionChangeParams) => {
      // Ignore empty flashes during props sync; pane click clears selection explicitly.
      if (selectedNodes.length === 0 && selectedEdges.length === 0) {
        return;
      }
      if (selectedNodes.length > 0) {
        onSelectNode?.(selectedNodes[0]?.id ?? null);
        onSelectEdge?.(null);
        return;
      }
      onSelectNode?.(null);
      onSelectEdge?.(selectedEdges[0]?.id ?? null);
    },
    [onSelectNode, onSelectEdge],
  );

  const onPaneClick = useCallback(() => {
    setPendingAdd(null);
    onSelectNode?.(null);
    onSelectEdge?.(null);
  }, [onSelectNode, onSelectEdge]);

  const onMoveEnd = useCallback(
    (_: unknown, viewport: Viewport) => {
      if (readOnly) {
        return;
      }
      emitChange(nodesRef.current, edgesRef.current, toWorkflowViewport(viewport));
    },
    [emitChange, readOnly],
  );

  const existingTypes = useMemo(
    () => nodes.map((node) => String(node.type || '')),
    [nodes],
  );

  const defaultViewport = workflow.viewport
    ? { x: workflow.viewport.x, y: workflow.viewport.y, zoom: workflow.viewport.zoom }
    : { x: 0, y: 0, zoom: 0.85 };

  return (
    <HandleInteractContext.Provider value={handleInteract}>
      <div className="workflow-canvas-inner" ref={canvasRef}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          defaultViewport={defaultViewport}
          nodesDraggable={!readOnly}
          nodesConnectable={!readOnly}
          edgesReconnectable={!readOnly}
          elementsSelectable
          connectOnClick={false}
          connectionDragThreshold={8}
          deleteKeyCode={readOnly ? null : ['Backspace', 'Delete']}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onSelectionChange={onSelectionChange}
          onPaneClick={onPaneClick}
          onMoveEnd={onMoveEnd}
          fitView={!workflow.viewport}
          connectionRadius={28}
          proOptions={{ hideAttribution: true }}
          className="workflow-flow"
        >
          <Background gap={18} color="rgba(143, 200, 255, 0.12)" />
          <Controls showInteractive={!readOnly} />
        </ReactFlow>

        {!readOnly && pendingAdd ? (
          <NodePicker
            screenX={pendingAdd.screenX}
            screenY={pendingAdd.screenY}
            existingTypes={existingTypes}
            onPick={onPickNodeType}
            onClose={() => setPendingAdd(null)}
          />
        ) : null}
      </div>
    </HandleInteractContext.Provider>
  );
}

export default function WorkflowCanvas(props: Props) {
  return (
    <div className={`workflow-canvas${props.readOnly ? ' is-readonly' : ''}`}>
      <ReactFlowProvider>
        <CanvasInner key={props.workflow.id} {...props} />
      </ReactFlowProvider>
    </div>
  );
}
