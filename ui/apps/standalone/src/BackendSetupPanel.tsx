import { useEffect, useRef, useState } from "react";
import type { BackendConfigurationState, BackendSetupInput, ReaderHost, ReadingWindow } from "@focus/reader-contracts";

const models = {
  codex: ["gpt-6-astra", "gpt-6-sol"],
  deepseek: ["deepseek-v4-flash", "deepseek-flash"],
} as const;
type Backend = keyof typeof models;

export function BackendSetupPanel({ host, configuration, onSaved }: {
  host: ReaderHost; configuration?: BackendConfigurationState; onSaved?: (view: ReadingWindow) => void;
}) {
  const [input, setInput] = useState<BackendSetupInput>({ backend: "codex", model: models.codex[0] });
  const [checking, setChecking] = useState(false);
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
      // A successful check selects this backend and model. Configuration stays off the UI.
      const selected = await host.saveBackendConfiguration({ ...payload, credentialFile: undefined });
      if (!alive.current || version !== revision.current) return;
      if (!selected.ok) { setError(selected.error.message); return; }
      onSaved?.(selected.value);
      const applied = await host.refreshBackendConfiguration();
      if (!alive.current || version !== revision.current) return;
      if (!applied.ok) { setError(applied.error.message); return; }
      onSaved?.(applied.value);
      setFeedback(applied.value.configuration?.pending ? "连接成功，任务结束后刷新页面应用。" : "连接成功，已启用所选模型。");
    } catch { if (alive.current && version === revision.current) setError("连接检查失败，请重试。"); }
    finally { if (alive.current && version === revision.current) setChecking(false); }
  }

  const options = [...new Set([...(models[input.backend] as readonly string[]),
    ...(saved?.backend === input.backend ? [saved.model] : []), input.model ?? ""])].filter(Boolean);
  return <section className="backend-setup focus-reader__appearance-panel" aria-label="后端设置">
    <h2>后端</h2>
    <fieldset disabled={checking}>
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
    <button disabled={checking || configuration?.busy || !host.backendSetup || !host.saveBackendConfiguration || !host.refreshBackendConfiguration}
      onClick={() => void check()}>{checking ? "检查中…" : "连接检查"}</button>
    {feedback && <p role="status">{feedback}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
