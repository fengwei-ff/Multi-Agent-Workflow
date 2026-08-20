import { useState } from 'react';
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type Edge,
  type EdgeProps,
} from '@xyflow/react';

type SelectableEdgeData = {
  onDeleteEdge?: (edgeId: string) => void;
};

export default function SelectableEdge(props: EdgeProps<Edge<SelectableEdgeData>>) {
  const {
    id,
    data,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    markerEnd,
    markerStart,
    style,
  } = props;
  const [hovered, setHovered] = useState(false);
  const [buttonHovered, setButtonHovered] = useState(false);
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  return (
    <>
      <g onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)}>
        <BaseEdge
          path={path}
          markerEnd={markerEnd}
          markerStart={markerStart}
          style={style}
          interactionWidth={16}
        />
      </g>
      {hovered || buttonHovered ? (
        <EdgeLabelRenderer>
          <button
            type="button"
            className="edge-delete-btn"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
            onMouseEnter={() => setButtonHovered(true)}
            onMouseLeave={() => setButtonHovered(false)}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              data?.onDeleteEdge?.(id);
            }}
            aria-label="删除连线"
            title="删除连线"
          >
            ×
          </button>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}
