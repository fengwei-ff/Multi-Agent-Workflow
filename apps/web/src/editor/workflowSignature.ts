import type { WorkflowDef } from '@workflow-agent/shared';

export function workflowContentSignature(workflow: WorkflowDef): string {
  const viewport = workflow.viewport
    ? {
        x: Number(workflow.viewport.x.toFixed(2)),
        y: Number(workflow.viewport.y.toFixed(2)),
        zoom: Number(workflow.viewport.zoom.toFixed(3)),
      }
    : undefined;

  return JSON.stringify({
    name: workflow.name,
    description: workflow.description,
    nodes: workflow.nodes,
    edges: workflow.edges,
    viewport,
  });
}
