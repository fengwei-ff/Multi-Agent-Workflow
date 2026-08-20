import type { WorkflowNodeType } from '@workflow-agent/shared';
import { NODE_TYPE_LABELS } from './nodeTypes';

export type PaletteItem = {
  type: WorkflowNodeType;
  label: string;
};

export type PaletteGroup = {
  title: string;
  items: PaletteItem[];
};

export const PALETTE_GROUPS: PaletteGroup[] = [
  {
    title: 'Agent',
    items: [{ type: 'agent', label: NODE_TYPE_LABELS.agent }],
  },
  {
    title: 'HITL',
    items: [{ type: 'hitl', label: NODE_TYPE_LABELS.hitl }],
  },
  {
    title: 'Control',
    items: [
      { type: 'start', label: NODE_TYPE_LABELS.start },
      { type: 'end', label: NODE_TYPE_LABELS.end },
    ],
  },
];

/** 已有 start 时不再提供添加入口（工作流只需一个）；end 可多个 */
export function filterPaletteGroups(
  groups: PaletteGroup[],
  existingTypes: Iterable<string>,
): PaletteGroup[] {
  const typeSet = new Set(existingTypes);
  return groups
    .map((group) => ({
      ...group,
      items: group.items.filter((item) => {
        if (item.type === 'start') {
          return !typeSet.has('start');
        }
        return true;
      }),
    }))
    .filter((group) => group.items.length > 0);
}
