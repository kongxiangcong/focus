import { useEffect, useRef, useState } from "react";
import { createReaderId, type BackendConfigurationState, type BackendDescriptor, type BackendSetupInput, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";

const legacyBackends: readonly BackendDescriptor[] = [
  { id: "codex", label: "Codex" },
  { id: "deepseek", label: "DeepSeek" },
];

export function BackendSetupPanel({ host, configuration, onSaved }: {
  host: ReaderHost; configuration?: BackendConfigurationState; onSaved?: (view: ReadingWindow) => void;
}) {
  const backends = configuration?.backends ?? legacyBackends;
  const available = backends.filter(backend => backend.available);
  const saved = configuration?.startupOverride ? configuration.effective : configuration?.saved ?? configuration?.effective;
  const suggested = saved?.backend ?? (configuration?.backends ? available.length === 1 ? available[0].id : "" : "codex");
  const [choice, setChoice] = useState<string | null>(null);
  const [models, setModels] = useState<Record<string, string | undefined>>({});
  const backend = choice ?? suggested;
  const descriptor = backends.find(candidate => candidate.id === backend);
  const preference = configuration?.startupOverride && saved?.backend === backend ? saved :
    configuration?.preferences?.[backend] ?? (saved?.backend === backend ? saved : undefined);
  const model = Object.hasOwn(models, backend) ? models[backend] : preference?.model ?? undefined;
  const runtimePath = preference?.runtimePath ?? descriptor?.runtimePath ?? undefined;
  const credentialFile = preference?.credentialFile ?? undefined;
  const input: BackendSetupInput = { backend, model, runtimePath, credentialFile };
  const [catalog, setCatalog] = useState<readonly string[]>([]);
  const [catalogError, setCatalogError] = useState("");
  const [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const [checking, setChecking] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const revision = useRef(0);
  const ownSave = useRef<string | null>(null);
  const discovery = descriptor?.capabilities?.modelDiscovery;
  const installed = descriptor?.available;

  useEffect(() => {
    if (ownSave.current && configuration?.operationId === ownSave.current) return;
    revision.current++;
    setChoice(null); setModels({}); setFeedback(""); setError(""); setChecking(false);
  }, [saved?.backend, saved?.model, saved?.runtimePath, saved?.credentialFile, configuration?.operationId, configuration?.startupOverride]);
  useEffect(() => () => { revision.current++; }, []);

  useEffect(() => {
    let current = true;
    setCatalog([]); setCatalogError("");
    if (!host.backendSetup || !backend || installed === false || !discovery || discovery === "none") {
      setLoading(false);
      return;
    }
    setLoading(true);
    void host.backendSetup("models", { backend, runtimePath, credentialFile }).then(result => {
      if (!current) return;
      if (result.ok && result.value.catalogStatus === "loaded") setCatalog(result.value.models ?? []);
      else setCatalogError(result.ok ? result.value.message : result.error.message);
    }).catch(() => { if (current) setCatalogError("模型清单加载失败。"); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [host, backend, runtimePath, credentialFile, installed, discovery, retry]);

  function clearResult() {
    revision.current++;
    setFeedback(""); setError(""); setChecking(false);
  }
  async function check() {
    if (!host.backendSetup || checking) return;
    const version = ++revision.current;
    setChecking(true); setFeedback(""); setError("");
    let saving = false;
    try {
      const connected = await host.backendSetup("check", input);
      if (version !== revision.current) return;
      if (!connected.ok || connected.value.status !== "success") {
        setError(connected.ok ? connected.value.message : connected.error.message);
        return;
      }
      const verified = `连接检查通过（${connected.value.checkedModel ?? model ?? descriptor?.defaultModel ?? "默认模型"}）`;
      const persisted = configuration?.saved;
      const persistedModel = configuration?.preferences?.[backend] ?? persisted;
      const alreadyApplied = !configuration?.startupOverride && persisted?.backend === backend
        && configuration?.effective?.backend === backend && (persistedModel?.model ?? undefined) === model;
      if (host.saveBackendConfiguration && !alreadyApplied) {
        saving = true;
        const requestId = createReaderId();
        ownSave.current = requestId;
        let result = await host.saveBackendConfiguration({ ...input, requestId });
        if (version !== revision.current) return;
        if (!result.ok && result.error.retryable && host.getReadingWindow) {
          const authority = await host.getReadingWindow();
          if (version !== revision.current) return;
          if (authority.ok && authority.value.configuration?.operationId === requestId) result = authority;
        }
        if (!result.ok) { setError(`${verified}，保存失败：${result.error.message}`); return; }
        onSaved?.(result.value);
        setFeedback(`${verified}，已保存并应用。`);
      } else setFeedback(`${verified}。`);
    } catch {
      if (version === revision.current) setError(saving ? "连接检查通过，保存结果未知，请刷新确认。" : "连接检查失败，请重试。");
    } finally {
      if (version === revision.current) setChecking(false);
    }
  }

  const options = [...new Set([...catalog, ...(model ? [model] : [])])];
  const disabled = !descriptor || installed === false;
  return <section className="backend-setup focus-reader__appearance-panel" aria-label="模型与后端">
    <h2>模型与后端</h2>
    {configuration?.startupError && <p role="alert">{configuration.startupError}</p>}
    {configuration?.backends && available.length === 0 && <p>未发现 CLI。请安装所需 CLI 后重新运行部署脚本 python deploy.py --discover-only。</p>}
    {!!configuration?.backendErrors?.length && <ul aria-label="Backend 配置错误">{configuration.backendErrors.map(({ file, message }) =>
      <li key={file}>{file} · {message}</li>)}</ul>}
    <fieldset disabled={checking}>
      <legend>选择后端</legend>
      {backends.map(({ id, label, available }) => <label key={id}>
        <input type="radio" name="setup-backend" disabled={available === false} checked={backend === id}
          onChange={() => { clearResult(); setChoice(id); }} />{label}
      </label>)}
    </fieldset>
    <div className="backend-setup__model">
      <label>模型<select disabled={disabled || checking} value={model ?? ""}
        onFocus={() => { if (catalogError) setRetry(n => n + 1); }}
        onChange={event => { clearResult(); setModels({ ...models, [backend]: event.target.value || undefined }); }}>
        <option value="">{loading ? "正在读取模型…" : descriptor?.defaultModel === null ? "请选择模型" : "使用默认模型"}</option>
        {options.map(option => <option key={option} value={option}>{option}</option>)}
      </select></label>
      <button type="button" className="workspace-primary" disabled={disabled || loading || checking || (descriptor?.defaultModel === null && !model) || configuration?.busy || !host.backendSetup}
        title="检查所选模型的连接，通过后保存并应用" onClick={() => void check()}>{checking ? "检查中…" : "连接检查"}</button>
    </div>
    {catalogError && <p role="alert">{catalogError} 再次聚焦模型框可重试。</p>}
    {configuration?.busy && <p role="status">当前任务正在使用后端，请在任务结束后检查连接。</p>}
    {feedback && <p role="status">{feedback}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
