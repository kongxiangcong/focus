import { useEffect, useMemo, useState } from "react";
import { WorkspaceSelection, workspaceRequest, type WorkspaceBindingStatus } from './WorkspaceSelection';
import { WorkspaceApp } from "./WorkspaceApp";
import { createStandaloneReaderHost } from "./adapters/create-standalone-reader-host";
import { BackendSetupPanel } from './BackendSetupPanel';
import type { BackendConfigurationState, BackendSetupInput } from '@focus/reader-contracts';

const baseUrl = import.meta.env.VITE_FOCUS_READER_BASE_URL?.trim() ?? "";


export function App() {
  const [ready, setReady] = useState(baseUrl === "fixture");
  const [checking, setChecking] = useState(baseUrl !== "fixture");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [binding, setBinding] = useState<WorkspaceBindingStatus | null>(null);
  const [expired, setExpired] = useState(false);
  const [configuration, setConfiguration] = useState<BackendConfigurationState>();
  const [draft, setDraft] = useState<BackendSetupInput>({ backend: 'codex' });
  const readerHost = useMemo(() => createStandaloneReaderHost(baseUrl, binding?.workspace?.instanceId), [binding?.workspace?.instanceId]);
  async function loadBinding() {
    try { setBinding(await workspaceRequest('/reader/workspace')); } catch { /* Direct test Hosts retain their established interface. */ }
  }
  useEffect(() => {
    if (binding && !binding.bound) void fetch(baseUrl + '/reader/configuration').then(response => response.json()).then(body => {
      if (body.ok) setConfiguration(body.value);
    }).catch(() => {});
  }, [binding?.bound]);
  useEffect(() => {
    const opened = (event: Event) => { setBinding((event as CustomEvent<WorkspaceBindingStatus>).detail); setExpired(false); };
    window.addEventListener('focus-workspace-opened', opened);
    return () => window.removeEventListener('focus-workspace-opened', opened);
  }, []);
  useEffect(() => {
    if (!binding?.workspace || expired) return;
    let alive = true;
    const instance = binding.workspace.instanceId;
    const timer = window.setInterval(() => { void workspaceRequest('/reader/workspace').then(next => {
      if (alive && next.workspace?.instanceId !== instance) setExpired(true);
    }).catch(() => {}); }, 1000);
    return () => { alive = false; clearInterval(timer); };
  }, [binding?.workspace?.instanceId, expired]);
  useEffect(() => {
    if (baseUrl !== "fixture") void (async () => {
      try {
        const response = await fetch(`${baseUrl}/reader/workspace`);
        if (response.status === 401) return;
        if (response.ok) {
          const body = await response.json();
          if (body.ok) setBinding(body.value);
        } else {
          const legacy = await fetch(`${baseUrl}/reader/window`);
          if (legacy.status === 401) return;
        }
        setReady(true);
      } catch (cause) { setError(String(cause)); }
      finally { setChecking(false); }
    })();
  }, []);
  if (checking) return <main className="focus-login"><h1>FOCUS</h1><p role="status">正在打开…</p></main>;
  if (expired) return <main className="focus-login"><h1>工作区已更换</h1><p>旧操作已暂停，旧草稿不会提交到新工作区。</p><button onClick={() => location.reload()}>重新载入</button></main>;
  if (ready && binding && !binding.bound) return <main className="focus-login"><WorkspaceSelection status={binding} onOpened={setBinding} configuration={draft}>
    <BackendSetupPanel host={readerHost} configuration={configuration} onDraft={setDraft} />
  </WorkspaceSelection></main>;
  if (ready) return <WorkspaceApp key={binding?.workspace?.instanceId} host={readerHost} />;
  return <main className="focus-login"><h1>focus.</h1><p>输入 FOCUS 后台启动时显示的访问口令。</p>
    <form onSubmit={async e => {
      e.preventDefault();
      try {
        const response = await fetch(`${baseUrl}/reader/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token }) });
        if (!response.ok) throw new Error("访问口令不正确");
        setToken(""); await loadBinding(); setReady(true);
      } catch (e) { setError(String(e)); }
    }}><label>访问口令 <input type="password" value={token} onChange={e => setToken(e.target.value)} autoComplete="current-password" /></label>
      <button type="submit">进入阅读空间</button></form>{error && <p role="alert">{error}</p>}</main>;
}
