import { useEffect, useRef, useState } from "react";
import { createReaderId, type BackendConfigurationState, type BackendDescriptor, type BackendSetupInput, type BackendSetupResult, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";

const legacyBackends: readonly BackendDescriptor[] = [
  { id: "codex", label: "Codex", capabilities: { authMode: "interactive-oauth", modelDiscovery: "codex-model-list" } },
  { id: "deepseek", label: "DeepSeek", capabilities: { modelDiscovery: "deepseek-models" } },
];

function catalogKey(input: BackendSetupInput) {
  return JSON.stringify([input.backend, input.runtimePath ?? "", input.credentialFile ?? ""]);
}

export function BackendSetupPanel({ host, configuration, onSaved }: {
  host: ReaderHost; configuration?: BackendConfigurationState; onSaved?: (view: ReadingWindow) => void;
}) {
  const [input, setInput] = useState<BackendSetupInput>({ backend: "" });
  const [scan, setScan] = useState<BackendSetupResult | null>(null);
  const [scanning, setScanning] = useState(false);
  const manualChoice = useRef(false);
  const drafts = useRef<Partial<Record<string, BackendSetupInput>>>({});
  const [catalog, setCatalog] = useState<Partial<Record<string, BackendSetupResult>>>({});
  const [checked, setChecked] = useState<BackendSetupResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [loginBusy, setLoginBusy] = useState(false);
  const [login, setLogin] = useState<BackendSetupResult | null>(null);
  const loginInput = useRef<BackendSetupInput | null>(null);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const revision = useRef(0);
  const alive = useRef(true);
  const startupOverride = configuration?.startupOverride;
  const saved = startupOverride ? configuration?.effective : configuration?.saved ?? configuration?.effective;
  const discovered = scan?.backends ?? configuration?.backends;
  const backends = discovered ?? legacyBackends;
  const available = backends.filter(backend => backend.available);
  const suggested = available.length === 1 ? available[0].id : discovered ? "" : legacyBackends[0].id;
  const selectedBackend = backends.find(backend => backend.id === input.backend);
  const needsModel = selectedBackend?.defaultModel === null && !input.model?.trim();
  useEffect(() => { setScan(null); }, [configuration?.backends]);
  useEffect(() => {
    if (saved) {
      manualChoice.current = false;
      revision.current++;
      setChecked(null); setChecking(false);
      setFeedback(previous => previous.startsWith('连接检查通过') ? '' : previous);
      drafts.current = Object.fromEntries(Object.entries(configuration?.preferences ?? {}).map(([backend, preference]) =>
        [backend, { backend, model: preference?.model ?? undefined, runtimePath: preference?.runtimePath ?? undefined, credentialFile: preference?.credentialFile ?? undefined }]));
      const draft = Object.hasOwn(drafts.current, saved.backend) ? drafts.current[saved.backend] : undefined;
      setInput((!startupOverride ? draft : undefined) ?? (startupOverride || configuration?.preferences === undefined ? {
        backend: saved.backend, model: saved.model ?? undefined, runtimePath: saved.runtimePath ?? undefined,
        credentialFile: saved.credentialFile ?? undefined,
      } : { backend: saved.backend }));
    }
  }, [saved?.backend, saved?.model, saved?.runtimePath, saved?.credentialFile, configuration?.operationId, startupOverride]);
  useEffect(() => {
    if (saved || (manualChoice.current && selectedBackend)) return;
    manualChoice.current = false;
    if (input.backend !== suggested) setInput({ backend: suggested });
  }, [saved?.backend, selectedBackend?.id, suggested, input.backend]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; revision.current++; }; }, []);

  function change(next: BackendSetupInput, manuallySelected = true) {
    revision.current++;
    manualChoice.current = manuallySelected;
    if (next.backend) drafts.current[next.backend] = next;
    setInput(next); setChecking(false); setFeedback(""); setError("");
    setChecked(null);
  }
  async function rescan() {
    if (!host.backendSetup) return;
    setScanning(true); setError(""); setFeedback("");
    try {
      const result = await host.backendSetup("rescan", { backend: "" });
      if (!alive.current) return;
      if (result.ok && result.value.status === "success") {
        setScan(result.value);
        setCatalog({});
        setChecked(null);
        setFeedback(result.value.message);
      } else setError(result.ok ? result.value.message : result.error.message);
    } catch {
      if (alive.current) setError("扫描失败，请重试。");
    } finally {
      if (alive.current) setScanning(false);
    }
  }
  async function loginOperation(action: "login-start" | "login-status" | "login-cancel") {
    if (!host.backendSetup || (action !== "login-start" && !login?.loginId)) return;
    const version = action === "login-start" ? ++revision.current : revision.current;
    setLoginBusy(true); setFeedback(""); setError("");
    try {
      const selection = action === "login-start" ? input : loginInput.current ?? input;
      const payload = { ...selection, loginId: login?.loginId };
      if (action === "login-start") {
        const prepared = await host.backendSetup("prepare", payload);
        if (!alive.current || version !== revision.current) return;
        if (!prepared.ok) { setError(prepared.error.message); return; }
        if (prepared.value.status !== "installed") { setError(prepared.value.message); return; }
      }
      const response = await host.backendSetup(action, payload);
      if (!alive.current || version !== revision.current) return;
      if (!response.ok) { setError(response.error.message); setLogin(null); return; }
      if (response.value.status === "waiting") {
        loginInput.current = { ...selection, runtimePath: response.value.runtimePath ?? selection.runtimePath };
        setLogin({ ...response.value, authUrl: response.value.authUrl ?? login?.authUrl });
      }
      else {
        loginInput.current = null;
        setLogin(null);
        if (response.value.status === "authenticated") setFeedback(`${selectedBackend?.label ?? "Backend"} 登录成功。可继续进行连接检查。`);
        else if (response.value.status !== "cancelled") setError(response.value.message);
      }
    } catch { if (alive.current && version === revision.current) { setLogin(null); setError("登录失败，请重试。"); } }
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
      if (connected.value.catalogStatus) setCatalog(previous => ({ ...previous, [catalogKey(input)]: connected.value }));
      setFeedback(`连接检查通过；已检模型：${connected.value.checkedModel ?? '本次请求模型'}。${connected.value.catalogMessage ?? ''}`);
    } catch { if (alive.current && version === revision.current) setError("连接检查失败，请重试。"); }
    finally { if (alive.current && version === revision.current) setChecking(false); }
  }

  async function loadModels() {
    if (!host.backendSetup) return;
    const version = ++revision.current;
    setChecking(true); setError(""); setFeedback("");
    try {
      const result = await host.backendSetup("models", input);
      if (!alive.current || version !== revision.current) return;
      if (result.ok) {
        setCatalog(previous => ({ ...previous, [catalogKey(input)]: result.value }));
        if (result.value.catalogStatus === "loaded") setFeedback(result.value.message);
        else setError(result.value.message);
      } else setError(result.error.message);
    } catch {
      if (alive.current && version === revision.current) setError("模型清单加载失败，请重试。");
    } finally {
      if (alive.current && version === revision.current) setChecking(false);
    }
  }

  async function save() {
    if (!host.saveBackendConfiguration) { setFeedback("此宿主不支持保存后端配置。"); return; }
    const version = ++revision.current;
    setChecking(true); setError(""); setFeedback("");
    try {
      const requestId = createReaderId();
      let result = await host.saveBackendConfiguration({ ...input, preferences: drafts.current, requestId });
      if (!alive.current || version !== revision.current) return;
      if (!result.ok && result.error.retryable && host.getReadingWindow) {
        const authority = await host.getReadingWindow();
        if (!alive.current || version !== revision.current) return;
        if (authority.ok && authority.value.configuration?.operationId === requestId) result = authority;
      }
      if (!result.ok) { setError(`后端配置未保存：${result.error.message}`); return; }
      onSaved?.(result.value);
      setFeedback("设置已保存并应用。");
    } catch { setError("后端保存结果未知，请刷新配置确认后重试。"); }
    finally { if (alive.current && version === revision.current) setChecking(false); }
  }

  const currentCatalog = catalog[catalogKey(input)];
  const options = [...new Set([...(currentCatalog?.models ?? []), input.model ?? ""])].filter(Boolean);
  const manifestErrors = scan?.backendErrors ?? configuration?.backendErrors ?? [];
  return <section className="backend-setup focus-reader__appearance-panel" aria-label="模型与后端">
    <h2>模型与后端</h2>
    {configuration?.startupError && <p role="alert">{configuration.startupError}</p>}
    {discovered && available.length === 0 && <p>未找到可用的 Backend。请安装，或选择一项后指定可执行文件。</p>}
    {!!manifestErrors.length && <ul aria-label="Backend 配置错误">{manifestErrors.map(({ file, message }) =>
      <li key={file}>{file} · {message}</li>)}</ul>}
    <fieldset disabled={loginBusy || !!login}>
      <legend>选择后端</legend>
      {backends.map(({ id, label, available: installed, installHint }) => <label key={id}
        title={installed === undefined ? undefined : installed ? "已找到可执行文件" : installHint}>
        <input type="radio" name="setup-backend" checked={input.backend === id}
          onChange={() => change((Object.hasOwn(drafts.current, id) && drafts.current[id]) || { backend: id })} />
        {label}
      </label>)}
      <label>模型<select disabled={!input.backend} value={input.model ?? ''} onChange={event => change({ ...input, model: event.target.value || undefined })}>
        <option value="">{selectedBackend?.defaultModel === null ? "请选择或手动输入模型" : "使用默认模型"}</option>
        {options.map(model => <option key={model} value={model}>{model}</option>)}
      </select></label>
      <details>
        <summary>手动设置模型</summary>
        <label>手动输入模型<input disabled={!input.backend} value={input.model ?? ""} onChange={event => change({ ...input, model: event.target.value || undefined })} /></label>
      </details>
      {!!selectedBackend?.credentialEnv?.length && <label>凭据文件路径<input value={input.credentialFile ?? ""}
        onChange={event => change({ ...input, credentialFile: event.target.value || undefined })} /></label>}
      {discovered && input.backend && <details open={selectedBackend?.available === false || undefined}>
        <summary>可执行文件</summary>
        <label>可执行文件路径<input value={input.runtimePath ?? ""} placeholder={selectedBackend?.runtimePath ?? "输入本机安装路径"}
          onChange={event => change({ ...input, runtimePath: event.target.value || null })} /></label>
      </details>}
    </fieldset>
    {selectedBackend?.available === false && <p>{selectedBackend.unavailableReason ?? selectedBackend.installHint}</p>}
    {selectedBackend?.capabilities?.authMode === "external-cli" && selectedBackend.loginHint && <p>{selectedBackend.loginHint}</p>}
    <div className="backend-setup__actions">
    {discovered && <button type="button" disabled={scanning || checking || loginBusy || !!login || !host.backendSetup}
      onClick={() => void rescan()}>{scanning ? "正在扫描…" : "重新扫描 Backend"}</button>}
    <button type="button" disabled={!selectedBackend || needsModel || scanning || checking || loginBusy || !!login || !host.backendSetup}
      onClick={() => void check()}>{checking ? "检查中…" : "连接检查"}</button>
    {selectedBackend?.capabilities?.modelDiscovery && selectedBackend.capabilities.modelDiscovery !== "none" &&
      <button type="button" disabled={scanning || checking || loginBusy || !!login || !host.backendSetup} onClick={() => void loadModels()}>
        {currentCatalog?.catalogStatus === "failed" ? "重试模型清单" : "加载模型清单"}
      </button>}
    {selectedBackend?.capabilities?.authMode === "interactive-oauth" &&
      <button type="button" disabled={scanning || checking || loginBusy || !!login || !host.backendSetup}
        onClick={() => void loginOperation("login-start")}>{loginBusy ? "登录处理中…" : `登录 ${selectedBackend.label}`}</button>}
    </div>
    {input.model && currentCatalog?.catalogStatus === 'loaded' && !currentCatalog.models?.includes(input.model) && <p role="status">已保存的模型不在当前清单中；保留选择，可重检或返回默认。</p>}
    <p>{checked && checked.backend === input.backend && (!input.model || checked.checkedModel === input.model) ? '当前模型已验证（仅本次最小请求）。' : '当前模型尚未验证。'}</p>
    {login?.authUrl && <p><a href={login.authUrl} target="_blank" rel="noopener noreferrer">打开浏览器授权</a>
      <button type="button" disabled={loginBusy} onClick={() => void loginOperation("login-cancel")}>取消登录</button></p>}
    <div className="backend-setup__actions backend-setup__save-actions">
    <button type="button" className="workspace-primary" disabled={!selectedBackend || needsModel || scanning || checking || loginBusy || !!login || configuration?.busy }
      onClick={() => void save()}>保存并应用</button>
    <button type="button" disabled={checking || loginBusy || !!login} onClick={() => {
      const backend = saved?.backend ?? suggested;
      const preference = startupOverride ? saved : configuration?.preferences?.[backend];
      change({ backend, model: preference?.model ?? undefined, runtimePath: preference?.runtimePath ?? undefined,
        credentialFile: preference?.credentialFile ?? undefined }, false);
    }}>取消修改</button></div>
    {configuration?.busy && <p role="status">当前任务正在使用后端，请等待任务结束后保存；可先编辑设置。</p>}
    {feedback && <p role="status">{feedback}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
