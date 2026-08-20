import { Handle, useNodeId, type HandleProps } from '@xyflow/react';
import type { MouseEvent } from 'react';
import { useHandleInteract } from './HandleInteractContext';

export default function WorkflowHandle(props: HandleProps) {
  const ctx = useHandleInteract();
  const nodeId = useNodeId();

  const onClick = (event: MouseEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (!ctx) {
      return;
    }
    if (ctx.readOnly || !nodeId || !props.type) {
      return;
    }
    ctx.openPicker({
      nodeId,
      handleId: props.id ?? null,
      handleType: props.type,
      clientX: event.clientX,
      clientY: event.clientY,
    });
  };

  return <Handle {...props} onClick={onClick} />;
}
