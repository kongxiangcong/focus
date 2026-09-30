import { useEffect, useRef, useState } from "react";
import type { BackendConfigurationState, BackendSetupInput, BackendSetupResult, ReaderHost, ReadingWindow } from "@focus/reader-contracts";

const models = {
  codex: ["gpt-6-astra", "gpt-6-sol"],
  deepseek: ["deepseek-v4-flash", "deepseek-flash"],
} as const;
type Backend = keyof typeof models;

export function BackendSetupPanel({ host, configuration, onSaved, onSaveAppearance, onCancelAppearance }: {
  host: ReaderHost; configuration?: BackendConfigurationState; onSaved?: (view: ReadingWindow) => void; onSaveAppearance?: () => boolean; onCancelAppearance?: () => void;
}) {
  const [input, setInput] = useState<BackendSetupInput>({ backend: "codex", model: models.codex[0] });
  const [checking, setChecking] = useState(false);
  const [loginBusy, setLoginBusy] = useState(false);
  const [login, setLogin] = useState<BackendSetupResult | null>(null);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const revision = useRef(0);
  const alive = useRef(true);
  const saved = configuration?.saved;
  useEffect(() => {
    if (saved) {
      setInput({ backend: saved.backend, model: saved.model });
    }
  }, [saved?.backend, saved?.model]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; revision.current++; }; }, []);

  function change(next: BackendSetupInput) {
    revision.current++;
    setInput(next); setChecking(false); setFeedback(""); setError("");
  }
  async function loginOperation(action: "login-start" | "login-status" | "login-cancel") {
    if (!host.backendSetup || (action !== "login-start" && !login?.loginId)) return;
    const version = action === "login-start" ? ++revision.current : revision.current;
    setLoginBusy(true); setFeedback(""); setError("");
    try {
      const payload = { ...input, runtimePath: saved?.backend === "codex" ? saved.runtimePath ?? undefined : undefined,
        loginId: login?.loginId };
      if (action === "login-start") {
        const prepared = await host.backendSetup("prepare", payload);
        if (!alive.current || version !== revision.current) return;
        if (!prepared.ok) { setError(prepared.error.message); return; }
        if (prepared.value.status !== "installed") { setError(prepared.value.message); return; }
      }
      const response = await host.backendSetup(action, payload);
      if (!alive.current || version !== revision.current) return;
      if (!response.ok) { setError(response.error.message); setLogin(null); return; }
      if (response.value.status === "waiting") setLogin({ ...response.value, authUrl: response.value.authUrl ?? login?.authUrl });
      else {
        setLogin(null);
        if (response.value.status === "authenticated") setFeedback("Codex 登录成功。可继续进行连接检查。");
        else if (response.value.status !== "cancelled") setError(response.value.message);
      }
    } catch { if (alive.current && version === revision.current) { setLogin(null); setError("Codex 登录失败，请重试。"); } }
    finally { if (alive.current && version === revision.current) setLoginBusy(false); }
  }
  useEffect(() => {
    if (login?.status !== "waiting" || loginBusy) return;
    const timer = window.setTimeout(() => void loginOperation("login-status"), 1500);
    return () => window.clearTimeout(timer);
  }, [login, loginBusy, host]);
  async function check() {
    if (!host.backendSetup || !host.saveBackendConfiguration || !host.refreshBackendConfiguration) return;
    const version = ++revision.current;
    setChecking(true); setFeedback(""); setError("");
    try {
      // Reuse a previously configured runtime for the same backend, without exposing its path.
      const runtimePath = saved?.backend === input.backend ? saved.runtimePath ?? undefined : undefined;
      const payload = { ...input, runtimePath };
      const prepared = await host.backendSetup("prepare", payload);
      if (!alive.current || version !== revision.current) return;
      if (!prepared.ok) { setError(prepared.error.message); return; }
      if (prepared.value.status !== "installed") { setError(prepared.value.message); return; }
      const connected = await host.backendSetup("check", payload);
      if (!alive.current || version !== revision.current) return;
      if (!connected.ok) { setError(connected.error.message); return; }
      if (connected.value.status !== "success") { setError(connected.value.message); return; }
      setFeedback("连接检查通过；点击保存设置后启用。");
    } catch { if (alive.current && version === revision.current) setError("连接检查失败，请重试。"); }
    finally { if (alive.current && version === revision.current) setChecking(false); }
  }

  async function save() {
    const appearanceSaved = onSaveAppearance?.();
    if (!host.saveBackendConfiguration || !host.refreshBackendConfiguration) { setFeedback(appearanceSaved ? "外观已保存；此宿主不支持保存后端配置。" : "外观未保存。此宿主不支持保存后端配置。"); return; }
    setChecking(true); setError(""); setFeedback("");
    try {
      const result = await host.saveBackendConfiguration({ ...input,
        runtimePath: saved?.backend === input.backend ? saved.runtimePath ?? undefined : undefined });
      if (!result.ok) { setError(`${appearanceSaved ? "外观已保存；" : appearanceSaved === false ? "外观未保存；" : ""}后端配置未保存：${result.error.message}`); return; }
      onSaved?.(result.value);
      const applied = await host.refreshBackendConfiguration();
      if (!applied.ok) { setError(`配置已保存，但尚未应用：${applied.error.message}`); return; }
      onSaved?.(applied.value); setFeedback(appearanceSaved === false ? "后端设置已保存并应用；外观未保存，请重试。" : "设置已保存并应用。");
    } catch { setError(`${appearanceSaved ? "外观已保存；" : appearanceSaved === false ? "外观未保存；" : ""}后端保存结果未知，请刷新配置确认后重试。`); }
    finally { setChecking(false); }
  }

  const options = [...new Set([...(models[input.backend] as readonly string[]),
    ...(saved?.backend === input.backend ? [saved.model] : []), input.model ?? ""])].filter(Boolean);
  return <section className="backend-setup focus-reader__appearance-panel" aria-label="后端设置">
    <h2>后端</h2>
    <fieldset disabled={checking || loginBusy || !!login}>
      <legend>选择后端</legend>
      {(["codex", "deepseek"] as Backend[]).map(backend => <label key={backend}>
        <input type="radio" name="setup-backend" checked={input.backend === backend}
          onChange={() => change({ backend, model: saved?.backend === backend ? saved.model : models[backend][0] })} />
        {backend === "codex" ? "Codex" : "DeepSeek"}
      </label>)}
      <label>模型<select value={input.model} onChange={event => change({ ...input, model: event.target.value })}>
        {options.map(model => <option key={model} value={model}>{model}</option>)}
      </select></label>
    </fieldset>
    <button disabled={checking || loginBusy || !!login || configuration?.busy || !host.backendSetup || !host.saveBackendConfiguration || !host.refreshBackendConfiguration}
      onClick={() => void check()}>{checking ? "检查中…" : "连接检查"}</button>
    {input.backend === "codex" && <button disabled={checking || loginBusy || !!login || !host.backendSetup}
      onClick={() => void loginOperation("login-start")}>{loginBusy ? "登录处理中…" : "登录 Codex"}</button>}
    {login?.authUrl && <p><a href={login.authUrl} target="_blank" rel="noopener noreferrer">打开浏览器授权</a>
      <button disabled={loginBusy} onClick={() => void loginOperation("login-cancel")}>取消登录</button></p>}
    <button disabled={checking || loginBusy || !!login || configuration?.busy }
      onClick={() => void save()}>保存设置</button>
    <button disabled={checking || loginBusy || !!login} onClick={() => {
      onCancelAppearance?.();
      change({ backend: saved?.backend ?? "codex", model: saved?.model ?? models.codex[0] });
    }}>取消修改</button>
    {configuration?.busy && <p role="status">当前任务正在使用后端，请等待任务结束后保存；可先编辑设置。</p>}
    {feedback && <p role="status">{feedback}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
