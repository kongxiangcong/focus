import { useEffect, useRef } from "react";
import type { AnnotationToastValue } from "./types";
export function AnnotationToast({ toast, onDismiss }: { toast: AnnotationToastValue | null; onDismiss: () => void }) {
  const dismiss = useRef(onDismiss); dismiss.current = onDismiss;
  useEffect(() => { if (toast) { const timer = setTimeout(() => dismiss.current(), 6000); return () => clearTimeout(timer); } }, [toast]);
  return toast ? <div className="reader-anno-toast" role="status" aria-live="polite"><span>{toast.message}</span>
    {toast.action && <button type="button" onClick={toast.action}>{toast.actionLabel}</button>}</div> : null;
}
