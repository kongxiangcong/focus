import { useEffect, useRef, useState } from "react";
import type { BackendSetupAction, BackendSetupInput, BackendSetupResult, ReaderHost } from "@focus/reader-contracts";

const defaults = { codex: "gpt-6-astra", deepseek: "deepseek-v4-flash" } as const;

export function BackendSetupPanel({ host, effective }: { host: ReaderHost; effective?: string }) {
  const [input, setInput] = useState<BackendSetupInput>({ backend: "codex", model: defaults.codex });
  const [result, setResult] = useState<BackendSetupResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [installations, setInstallations] = useState<BackendSetupResult[]>([]);
  const [error, setError] = useState("");
  const [login, setLogin] = useState<BackendSetupResult | null>(null);
  const revision = useRef(0);
  const alive = useRef(true);
  const firstPreparation = useRef(false);
  useEffect(() => { alive.current = true; return () => { alive.current = false; revision.current++; }; }, []);
  useEffect(() => {
    if (!firstPreparation.current && host.backendSetup) {
      firstPreparation.current = true;
      void prepare();
    }
  }, [host]);

  function change(next: BackendSetupInput) {
    revision.current++;
    setInput(next); setResult(null); setChecking(false); setError("");
  }
  async function run(action: BackendSetupAction) {
    if (!host.backendSetup) return;
    const version = ++revision.current;
    setError(""); setChecking(true);
    try {
      const response = await host.backendSetup(action, { ...input, loginId: login?.loginId });
      if (!alive.current || version !== revision.current) return;
      if (!response.ok) { setError(response.error.message); return; }
      setResult(response.value);
      if (action.startsWith("login-")) setLogin(response.value.status === "waiting" ? { ...login, ...response.value } : null);
    } catch { if (alive.current && version === revision.current) setError("设置请求失败，请重试。"); }
    finally { if (alive.current && version === revision.current) setChecking(false); }
  }
  useEffect(() => {
    if (!login || login.status !== "waiting") return;
    const timer = window.setInterval(() => { if (!checking) void run("login-status"); }, 1500);
    return () => window.clearInterval(timer);
  }, [login, checking, input, host]);

  async function prepare() {
    if (!host.backendSetup || preparing) return;
    revision.current++;
    setResult(null); setChecking(false); setPreparing(true); setInstallations([]);
    try {
      const results = await Promise.all((["codex", "deepseek"] as const).map(async backend => {
        const response = await host.backendSetup!("prepare", { backend,
          runtimePath: backend === input.backend ? input.runtimePath : undefined });
        return response.ok ? response.value : { backend, runtimePath: null, status: "failed", message: response.error.message };
      }));
      if (alive.current) setInstallations(results);
    } catch { if (alive.current) setError("依赖准备请求失败，请重试。"); }
    finally { if (alive.current) setPreparing(false); }
  }

  return <section className="backend-setup focus-reader__appearance-panel" aria-label="Backend 准备与检查">
    <h2>后端</h2>
    <p>当前生效：{effective === "deepseek" ? "DeepSeek" : "Codex"}。此处准备和检查不会切换任务使用的后端。</p>
    <button disabled={preparing || !host.backendSetup} onClick={() => void prepare()}>{preparing ? "正在准备依赖…" : "准备两套后端依赖"}</button>
    <p>只安装缺失依赖，不会自动登录或调用模型。</p>
    {installations.map(item => <p key={item.backend}>{item.backend}：{item.message} {item.runtimePath}</p>)}
    <fieldset disabled={!!login}>
      <legend>选择要检查的后端</legend>
      {(["codex", "deepseek"] as const).map(backend => <label key={backend}>
        <input type="radio" name="setup-backend" checked={input.backend === backend}
          onChange={() => change({ backend, model: defaults[backend] })} />{backend === "codex" ? "Codex" : "DeepSeek"}
      </label>)}
      <label>Runtime 路径（留空复用本机安装）<input value={input.runtimePath ?? ""}
        onChange={event => change({ ...input, runtimePath: event.target.value })} /></label>
      <label>模型<select value={input.model} onChange={event => change({ ...input, model: event.target.value })}>
        <option value={defaults[input.backend]}>{defaults[input.backend]}</option>
      </select></label>
      {input.backend === "deepseek" && <label>Host 凭据文件路径（默认读取 .env）<input value={input.credentialFile ?? ""}
        onChange={event => change({ ...input, credentialFile: event.target.value })} /></label>}
    </fieldset>
    <button disabled={checking || !!login || !host.backendSetup} onClick={() => void run("inspect")}>检查安装路径</button>
    {input.backend === "codex" && <>
      <button disabled={checking || !!login || !host.backendSetup} onClick={() => void run("account")}>检查 Codex 登录</button>
      <button disabled={checking || !!login || !host.backendSetup} onClick={() => void run("login-start")}>登录 Codex</button>
    </>}
    {login?.authUrl && <p><a href={login.authUrl} target="_blank" rel="noopener noreferrer">打开浏览器授权</a>
      <button disabled={checking} onClick={() => void run("login-cancel")}>取消登录</button></p>}
    <button disabled={checking || !!login || !host.backendSetup} onClick={() => void run("check")}>连通性检查</button>
    <p role="status">{checking ? "检查中…" : result?.message ?? "未检查"}</p>
    {result?.runtimePath && <p>实际 Runtime：<code>{result.runtimePath}</code></p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
