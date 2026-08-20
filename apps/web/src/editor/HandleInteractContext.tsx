import { createContext, useContext } from 'react';

export type HandleAnchor = {
  nodeId: string;
  handleId: string | null;
  handleType: 'source' | 'target';
  clientX: number;
  clientY: number;
};

type HandleInteractContextValue = {
  openPicker: (anchor: HandleAnchor) => void;
  readOnly: boolean;
};

export const HandleInteractContext = createContext<HandleInteractContextValue | null>(null);

export function useHandleInteract(): HandleInteractContextValue | null {
  return useContext(HandleInteractContext);
}
