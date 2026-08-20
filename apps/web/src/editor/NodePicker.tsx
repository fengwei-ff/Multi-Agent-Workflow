import type { WorkflowNodeType } from '@workflow-agent/shared';
import { filterPaletteGroups, PALETTE_GROUPS } from './paletteCatalog';

type Props = {
  screenX: number;
  screenY: number;
  existingTypes: string[];
  onPick: (type: WorkflowNodeType) => void;
  onClose: () => void;
};

export default function NodePicker({
  screenX,
  screenY,
  existingTypes,
  onPick,
  onClose,
}: Props) {
  const groups = filterPaletteGroups(PALETTE_GROUPS, existingTypes);

  return (
    <>
      <button
        type="button"
        className="node-picker-backdrop"
        aria-label="关闭添加节点菜单"
        onClick={onClose}
      />
      <div
        className="node-picker"
        style={{ left: screenX, top: screenY }}
        role="dialog"
        aria-label="添加节点"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="node-picker-header">添加节点</div>
        {groups.length === 0 ? (
          <p className="hint">暂无可添加节点</p>
        ) : (
          groups.map((group) => (
            <div key={group.title} className="palette-group">
              <div className="palette-group-title">{group.title}</div>
              <div className="palette-items">
                {group.items.map((item) => (
                  <button
                    key={item.type}
                    type="button"
                    className="palette-item node-picker-item"
                    title={item.type}
                    onClick={() => onPick(item.type)}
                  >
                    <code>{item.type}</code>
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </>
  );
}
