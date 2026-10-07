import { useEffect, useRef, useState } from "react";
import type { BackendConfigurationState, BackendSetupInput, BackendSetupResult, ReaderHost, ReadingWindow } from "@focus/reader-contracts";

type Backend = 'codex' | 'deepseek';

export function BackendSetupPanel({ host, configuration, onSaved, onSaveAppearance, onCancelAppearance, onDraft }: {
  host: ReaderHost; configuration?: BackendConfigurationState; onSaved?: (view: ReadingWindow) => void; onSaveAppearance?: () => boolean; onCancelAppearance?: () => void;
  onDraft?: (input: BackendSetupInput) => void;
}) {
  const [input, setInput] = useState<BackendSetupInput>({ backend: "codex" });
  const drafts = useRef<Partial<Record<Backend, BackendSetupInput>>>({});
  const [catalog, setCatalog] = useState<Partial<Record<Backend, BackendSetupResult>>>({});
  const [checked, setChecked] = useState<BackendSetupResult | null>(null);
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
      revision.current++;
      setChecked(null); setChecking(false);
      setFeedback(previous => previous.startsWith('连接检查通过') ? '' : previous);
      drafts.current = Object.fromEntries(Object.entries(configuration?.preferences ?? {}).map(([backend, preference]) =>
        [backend, { backend, model: preference?.model ?? undefined, runtimePath: preference?.runtimePath ?? undefined, credentialFile: preference?.credentialFile ?? undefined }]));
      setInput(drafts.current[saved.backend] ?? (configuration?.preferences === undefined ? {
        backend: saved.backend, model: saved.model, runtimePath: saved.runtimePath ?? undefined,
        credentialFile: saved.credentialFile ?? undefined,
      } : { backend: saved.backend }));
    }
  }, [saved?.backend, saved?.model, saved?.runtimePath, saved?.credentialFile, configuration?.operationId]);
  useEffect(() => { onDraft?.({ ...input, preferences: drafts.current }); }, [input, onDraft]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; revision.current++; }; }, []);

  function change(next: BackendSetupInput) {
    revision.current++;
    drafts.current[next.backend] = next;
    setInput(next); setChecking(false); setFeedback(""); setError("");
    setChecked(null);
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
    if (!host.backendSetup) return;
    const version = ++revision.current;
    setChecking(true); setFeedback(""); setError(""); setChecked(null);
    try {
      // Reuse a previously configured runtime for the same backend, without exposing its path.
      const runtimePath = input.runtimePath;
      const payload = { ...input, runtimePath };
      const prepared = await host.backendSetup("prepare", payload);
      if (!alive.current || version !== revision.current) return;
      if (!prepared.ok) { setError(prepared.error.message); return; }
      if (prepared.value.status !== "installed") { setError(prepared.value.message); return; }
      const connected = await host.backendSetup("check", payload);
      if (!alive.current || version !== revision.current) return;
      if (!connected.ok) { setError(connected.error.message); return; }
      if (connected.value.status !== "success") { setError(connected.value.message); return; }
      setChecked(connected.value);
      setCatalog(previous => ({ ...previous, [input.backend]: connected.value }));
      setFeedback(`连接检查通过；已检模型：${connected.value.checkedModel ?? '本次请求模型'}。${connected.value.catalogMessage ?? ''}`);
    } catch { if (alive.current && version === revision.current) setError("连接检查失败，请重试。"); }
    finally { if (alive.current && version === revision.current) setChecking(false); }
  }

  async function save() {
    const appearanceSaved = onSaveAppearance?.();
    if (!host.saveBackendConfiguration) { setFeedback(appearanceSaved ? "外观已保存；此宿主不支持保存后端配置。" : "外观未保存。此宿主不支持保存后端配置。"); return; }
    const version = ++revision.current;
    setChecking(true); setError(""); setFeedback("");
    try {
      const requestId = crypto.randomUUID();
      let result = await host.saveBackendConfiguration({ ...input, preferences: drafts.current, requestId });
      if (!alive.current || version !== revision.current) return;
      if (!result.ok && result.error.retryable && host.getReadingWindow) {
        const authority = await host.getReadingWindow();
        if (!alive.current || version !== revision.current) return;
        if (authority.ok && authority.value.configuration?.operationId === requestId) result = authority;
      }
      if (!result.ok) { setError(`${appearanceSaved ? "外观已保存；" : appearanceSaved === false ? "外观未保存；" : ""}后端配置未保存：${result.error.message}`); return; }
      onSaved?.(result.value);
      setFeedback(appearanceSaved === false ? "后端设置已保存并应用；外观未保存，请重试。" : "设置已保存并应用。");
    } catch { setError(`${appearanceSaved ? "外观已保存；" : appearanceSaved === false ? "外观未保存；" : ""}后端保存结果未知，请刷新配置确认后重试。`); }
    finally { if (alive.current && version === revision.current) setChecking(false); }
  }

  const currentCatalog = catalog[input.backend];
  const options = [...new Set([...(currentCatalog?.models ?? []), input.model ?? ""])].filter(Boolean);
  return <section className="backend-setup focus-reader__appearance-panel" aria-label="后端设置">
    <h2>后端</h2>
    <fieldset disabled={loginBusy || !!login}>
      <legend>选择后端</legend>
      {(["codex", "deepseek"] as Backend[]).map(backend => <label key={backend}>
        <input type="radio" name="setup-backend" checked={input.backend === backend}
          onChange={() => change(drafts.current[backend] ?? { backend })} />
        {backend === "codex" ? "Codex" : "DeepSeek"}
      </label>)}
      <label>模型<select value={input.model ?? ''} onChange={event => change({ ...input, model: event.target.value || undefined })}>
        <option value="">使用默认模型</option>
        {options.map(model => <option key={model} value={model}>{model}</option>)}
      </select></label>
    </fieldset>
    <div className="backend-setup__actions">
    <button type="button" disabled={checking || loginBusy || !!login || !host.backendSetup}
      onClick={() => void check()}>{checking ? "检查中…" : "连接检查"}</button>
    {currentCatalog?.catalogStatus === 'failed' && <button type="button" disabled={checking} onClick={async () => {
      const version = ++revision.current;
      setChecking(true);
      try {
        const result = await host.backendSetup?.('models', input);
        if (!alive.current || version !== revision.current || !result) return;
        if (result.ok) { setCatalog(previous => ({ ...previous, [input.backend]: result.value })); setFeedback(result.value.message); }
        else setError(result.error.message);
      } finally { if (alive.current && version === revision.current) setChecking(false); }
    }}>重试模型清单</button>}
    {input.backend === "codex" && <button type="button" disabled={checking || loginBusy || !!login || !host.backendSetup}
      onClick={() => void loginOperation("login-start")}>{loginBusy ? "登录处理中…" : "登录 Codex"}</button>}
    </div>
    {input.model && currentCatalog?.catalogStatus === 'loaded' && !currentCatalog.models?.includes(input.model) && <p role="status">已保存的模型不在当前清单中；保留选择，可重检或返回默认。</p>}
    <p>{checked && checked.backend === input.backend && (!input.model || checked.checkedModel === input.model) ? '当前模型已验证（仅本次最小请求）。' : '当前模型尚未验证。'}</p>
    {login?.authUrl && <p><a href={login.authUrl} target="_blank" rel="noopener noreferrer">打开浏览器授权</a>
      <button type="button" disabled={loginBusy} onClick={() => void loginOperation("login-cancel")}>取消登录</button></p>}
    {!onDraft && <button type="button" disabled={checking || loginBusy || !!login || configuration?.busy }
      onClick={() => void save()}>保存并应用</button>}
    {!onDraft && <button type="button" disabled={checking || loginBusy || !!login} onClick={() => {
      onCancelAppearance?.();
      const backend = saved?.backend ?? 'codex';
      change({ backend, model: configuration?.preferences?.[backend]?.model ?? undefined });
    }}>取消修改</button>}
    <small>API 密钥等配置可在项目目录的 .env 文件中填写；Codex 使用已有登录。路径及 Backend／模型选项由应用自动保存。</small>
    {configuration?.busy && <p role="status">当前任务正在使用后端，请等待任务结束后保存；可先编辑设置。</p>}
    {feedback && <p role="status">{feedback}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
