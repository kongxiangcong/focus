import { type ReactNode, useEffect, useId, useState } from 'react';
import { createReaderId, type BackendSetupInput } from '@focus/reader-contracts';

export interface WorkspaceBindingStatus {
  bound: boolean;
  workspace: { path: string; workspaceId: string; instanceId: string } | null;
  savedWorkspace: { path: string; workspaceId: string } | null;
  error: string | null;
  busy: boolean;
  operationId?: string;
  generation: string;
}

const baseUrl = import.meta.env.VITE_FOCUS_READER_BASE_URL?.trim() ?? '';
export async function workspaceRequest(path: string, payload?: unknown): Promise<WorkspaceBindingStatus> {
  const response = await fetch(baseUrl + path, payload === undefined ? undefined : {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok || !body.ok) throw new Error(body.error?.message ?? '工作区操作失败，请重试。');
  return body.value;
}

export function WorkspaceSelection({ status: initial, onOpened, children, configuration }: {
  status?: WorkspaceBindingStatus; onOpened?: (status: WorkspaceBindingStatus) => void; children?: ReactNode;
  configuration?: BackendSetupInput;
}) {
  const [status, setStatus] = useState(initial);
  const [editing, setEditing] = useState(!initial?.bound);
  const [mode, setMode] = useState<'import' | 'create' | 'relocate'>(initial?.savedWorkspace && !initial.bound ? 'relocate' : 'import');
  const [path, setPath] = useState('');
  const [name, setName] = useState('knowledge-base');
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState(false);
  const pathId = useId();
  const [error, setError] = useState('');
  useEffect(() => {
    if (!initial) void workspaceRequest('/reader/workspace').then(next => {
      setStatus(next); setEditing(!next.bound);
    }).catch(() => {});
  }, [initial]);
  if (!status) return null;
  return <section className="workspace-selection" aria-label="工作区选择">
    <h2>{status.bound ? '工作区' : '开始使用 FOCUS'}</h2>
    {!status.bound && <p className="workspace-entry-intro">选择工作区与后端，开始阅读。</p>}
    {status.workspace && <p className="workspace-location">{status.workspace.path}</p>}
    {!editing && <button disabled={status.busy} onClick={() => setEditing(true)}>更换工作区</button>}
    {editing && <form onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError('');
      let requestId: string | undefined;
      try {
        requestId = createReaderId();
        const next = await workspaceRequest('/reader/workspace', { mode, path, name, requestId, configuration, generation: status.generation });
        setStatus(next); setEditing(false);
        if (onOpened) onOpened(next);
        else window.dispatchEvent(new CustomEvent('focus-workspace-opened', { detail: next }));
      } catch (cause) {
        // A lost response is resolved by reading the authoritative binding.
        try {
          const next = await workspaceRequest('/reader/workspace');
          if (requestId && next.workspace && next.operationId === requestId) {
            setStatus(next); setEditing(false);
            if (onOpened) onOpened(next);
            else window.dispatchEvent(new CustomEvent('focus-workspace-opened', { detail: next }));
          } else setError(String(cause));
        } catch { setError(String(cause)); }
      } finally { setBusy(false); }
    }}>
      <div className="workspace-entry-fields">
      {status.error && <p role="alert">{status.error}</p>}
      {status.savedWorkspace && !status.bound && <p className="workspace-location">原位置：{status.savedWorkspace.path}</p>}
      <fieldset disabled={busy}><legend>打开方式</legend>
        {([['import', '导入工作区'], ['create', '新建工作区'], ...(status.savedWorkspace && !status.bound ? [['relocate', '重新定位原工作区']] : [])] as [typeof mode, string][]).map(([value, label]) =>
          <label key={value}><input type="radio" name="workspace-mode" value={value} checked={mode === value} onChange={() => setMode(value)} />{label}</label>)}
      </fieldset>
      <div className="workspace-path-field">
      <label htmlFor={pathId}>{mode === 'create' ? '父目录' : '工作区目录'}</label>
      <div className="workspace-path-row">
      <input id={pathId} autoFocus value={path} onChange={event => setPath(event.target.value)} disabled={busy || picking} placeholder="运行 FOCUS 这台电脑上的目录" required />
      <button type="button" disabled={busy || picking} onClick={async () => {
        setPicking(true); setError('');
        try {
          const response = await fetch(baseUrl + '/reader/workspace/pick', { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' });
          const body = await response.json();
          if (!response.ok || !body.ok) throw new Error(body.error?.message ?? '目录选择失败');
          if (body.value.path) setPath(body.value.path);
          if (body.value.error) setError(body.value.error);
        } catch (cause) { setError(String(cause)); } finally { setPicking(false); }
      }}>{picking ? '选择中…' : '选择目录'}</button>
      </div></div>
      {mode === 'create' && <label>名称<input value={name} disabled={busy} onChange={event => setName(event.target.value)} required /></label>}
      <p className="workspace-backup-hint">退出 FOCUS、完成落盘后，复制整个工作区即可备份；恢复后选择导入。</p>
      </div>
      {children && <div className="workspace-entry-backend">{children}</div>}
      <div className="workspace-entry-footer">
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">正在打开…</p>}
      {picking && <p role="status">请在弹出的窗口选择目录。</p>}
      <button type="submit" disabled={busy || picking || status.busy}>进入工作台</button>
      {status.bound && <button type="button" disabled={busy || picking} onClick={() => setEditing(false)}>取消</button>}
      </div>
    </form>}
  </section>;
}
