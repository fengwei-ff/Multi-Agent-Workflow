import { useEffect, useState } from 'react';

export type ToastTone = 'success' | 'error' | 'info';

type ToastItem = {
  id: number;
  message: string;
  tone: ToastTone;
};

let toastId = 0;
const listeners = new Set<(item: ToastItem) => void>();

export function showToast(message: string, tone: ToastTone = 'success') {
  const item = { id: ++toastId, message, tone };
  listeners.forEach((listener) => listener(item));
}

export function ToastHost() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    const onToast = (item: ToastItem) => {
      setItems([item]);
    };
    listeners.add(onToast);
    return () => {
      listeners.delete(onToast);
    };
  }, []);

  if (items.length === 0) {
    return null;
  }

  return (
    <div className="toast-host" aria-live="polite">
      {items.map((item) => (
        <div key={item.id} className={`toast toast-${item.tone}`}>
          <span>{item.message}</span>
          <button
            type="button"
            className="toast-close"
            aria-label="关闭提示"
            onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
