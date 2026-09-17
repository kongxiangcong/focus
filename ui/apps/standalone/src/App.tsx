import { useEffect, useState } from "react";
import { WorkspaceApp } from "./WorkspaceApp";
import { createStandaloneReaderHost } from "./adapters/create-standalone-reader-host";

const baseUrl = import.meta.env.VITE_FOCUS_READER_BASE_URL?.trim() ?? "";
const readerHost = createStandaloneReaderHost(baseUrl);

export function App() {
  const [ready, setReady] = useState(baseUrl === "fixture");
  const [checking, setChecking] = useState(baseUrl !== "fixture");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (baseUrl !== "fixture") void fetch(`${baseUrl}/reader/window`).then(r => {
      if (r.status !== 401) setReady(true);
      setChecking(false);
    }).catch(() => { setChecking(false); setReady(true); });
  }, []);
  if (checking) return <main className="focus-login"><h1>FOCUS</h1><p role="status">正在打开…</p></main>;
  if (ready) return <WorkspaceApp host={readerHost} />;
  return <main className="focus-login"><h1>focus.</h1><p>输入 FOCUS 后台启动时显示的访问口令。</p>
    <form onSubmit={async e => {
      e.preventDefault();
      try {
        const response = await fetch(`${baseUrl}/reader/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token }) });
        if (!response.ok) throw new Error("访问口令不正确");
        setToken(""); setReady(true);
      } catch (e) { setError(String(e)); }
    }}><label>访问口令 <input type="password" value={token} onChange={e => setToken(e.target.value)} autoComplete="current-password" /></label>
      <button type="submit">进入阅读空间</button></form>{error && <p role="alert">{error}</p>}</main>;
}
