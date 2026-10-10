// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readerSuccess, type BackendSetupResult, type ReaderHostResult, type ReaderHost } from "@focus/reader-contracts";
import { BackendSetupPanel } from "./BackendSetupPanel";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('invalidates a successful proof after an authoritative backend change or failed recheck', async () => {
  let failed = false;
  const backendSetup = vi.fn(async (action: string, input: { backend: string }) => readerSuccess({
    backend: input.backend, runtimePath: '/runtime', environmentId: input.backend + '-env',
    checkedModel: 'default', status: action === 'prepare' ? 'installed' : failed ? 'failed' : 'success', message: 'check failed',
  }));
  const host = { backendSetup } as unknown as ReaderHost;
  const settings = (backend: 'codex' | 'deepseek', operationId: string) => ({
    saved: { backend, model: 'default', runtimePath: null, credentialFile: null },
    effective: { backend, model: 'default', runtimePath: null, credentialFile: null },
    pending: false, busy: false, refreshBlocked: false, preferences: {}, operationId,
  });
  const view = render(<BackendSetupPanel host={host} configuration={settings('codex', 'first')} />);
  fireEvent.click(screen.getByRole('button', { name: '连接检查' }));
  await screen.findByText('当前模型已验证（仅本次最小请求）。');
  view.rerender(<BackendSetupPanel host={host} configuration={settings('deepseek', 'second')} />);
  expect(screen.getByText('当前模型尚未验证。')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '连接检查' }));
  await screen.findByText('当前模型已验证（仅本次最小请求）。');
  failed = true;
  fireEvent.click(screen.getByRole('button', { name: '连接检查' }));
  await screen.findByRole('alert');
  expect(screen.getByText('当前模型尚未验证。')).toBeInTheDocument();
});
const empty = { status: "empty" as const, source: { sourceId: "", title: "", topicId: null }, current: null, history: [], conversation: [] };

it("checks without applying, then saves and applies only on explicit confirmation", async () => {
  const backendSetup = vi.fn(async (action: string, input: { backend: string }) => readerSuccess({
    backend: input.backend, runtimePath: "/private/runtime", status: action === "prepare" ? "installed" : "success", message: "OK",
    checkedModel: 'default', models: ['deepseek-flash'], catalogStatus: 'loaded',
  }));
  const saveBackendConfiguration = vi.fn(async () => readerSuccess(empty));
  const refreshBackendConfiguration = vi.fn(async () => readerSuccess(empty));
  const host = { backendSetup, saveBackendConfiguration, refreshBackendConfiguration } as unknown as ReaderHost;
  render(<BackendSetupPanel host={host} />);
  fireEvent.click(screen.getByRole("radio", { name: "DeepSeek" }));
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "连接检查" }));
  await screen.findByText(/连接检查通过；已检模型/);
  fireEvent.change(screen.getByRole("combobox", { name: "模型" }), { target: { value: "deepseek-flash" } });
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
  expect(refreshBackendConfiguration).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "保存并应用" }));
  await waitFor(() => expect(saveBackendConfiguration).toHaveBeenCalledOnce());
  expect(refreshBackendConfiguration).not.toHaveBeenCalled();
  expect(backendSetup.mock.calls.map(call => call[0])).toEqual(["prepare", "check"]);
  expect(saveBackendConfiguration).toHaveBeenCalledWith(expect.objectContaining({ backend: "deepseek", model: "deepseek-flash" }));
  expect(screen.queryByText(/private\/runtime/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /保存配置|准备|安装路径/ })).not.toBeInTheDocument();
});

it("does not attempt a connection or save if dependency installation fails", async () => {
  const backendSetup = vi.fn(async () => readerSuccess({ backend: "codex", runtimePath: null, status: "failed", message: "安装失败" }));
  const saveBackendConfiguration = vi.fn();
  render(<BackendSetupPanel host={{ backendSetup, saveBackendConfiguration, refreshBackendConfiguration: vi.fn() } as unknown as ReaderHost} />);
  fireEvent.click(screen.getByRole("button", { name: "连接检查" }));
  await screen.findByRole("alert");
  expect(backendSetup).toHaveBeenCalledOnce();
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
});

it("keeps the current selection when the model request fails", async () => {
  const backendSetup = vi.fn(async (action: string) => readerSuccess({
    backend: "deepseek", runtimePath: null, status: action === "prepare" ? "installed" : "failed", message: "凭据无效",
  }));
  const saveBackendConfiguration = vi.fn();
  render(<BackendSetupPanel host={{ backendSetup, saveBackendConfiguration, refreshBackendConfiguration: vi.fn() } as unknown as ReaderHost} />);
  fireEvent.click(screen.getByRole("radio", { name: "DeepSeek" }));
  fireEvent.click(screen.getByRole("button", { name: "连接检查" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("凭据无效");
  expect(backendSetup.mock.calls.map(call => call[0])).toEqual(["prepare", "check"]);
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
});

it("offers Codex browser login and waits for confirmed authentication", async () => {
  const backendSetup = vi.fn(async (action: string) => readerSuccess({
    backend: "codex", runtimePath: "/codex", status: action === "prepare" ? "installed" : action === "login-start" ? "waiting" : "authenticated",
    message: "OK", ...(action === "login-start" ? { loginId: "login-1", authUrl: "https://auth.openai.com/test" } : {}),
  }));
  render(<BackendSetupPanel host={{ backendSetup } as unknown as ReaderHost} />);
  expect(screen.getByRole("button", { name: "登录 Codex" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "登录 Codex" }));
  const link = await screen.findByRole("link", { name: "打开浏览器授权" });
  expect(link).toHaveAttribute("href", "https://auth.openai.com/test");
  expect(screen.getByRole("button", { name: "取消登录" })).toBeEnabled();
  await waitFor(() => expect(screen.getByText("Codex 登录成功。可继续进行连接检查。")).toBeInTheDocument(), { timeout: 3000 });
  expect(backendSetup.mock.calls.map(call => call[0])).toEqual(["prepare", "login-start", "login-status"]);
  expect(screen.queryByRole("link", { name: "打开浏览器授权" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("radio", { name: "DeepSeek" }));
  expect(screen.queryByRole("button", { name: "登录 Codex" })).not.toBeInTheDocument();
});

it("discards a late preparation after unmounting", async () => {
  let resolve!: (value: ReaderHostResult<BackendSetupResult>) => void;
  const backendSetup = vi.fn(() => new Promise<ReaderHostResult<BackendSetupResult>>(done => { resolve = done; }));
  const saveBackendConfiguration = vi.fn();
  const host = { backendSetup, saveBackendConfiguration, refreshBackendConfiguration: vi.fn() } as unknown as ReaderHost;
  const app = render(<BackendSetupPanel host={host} />);
  fireEvent.click(screen.getByRole("button", { name: "连接检查" }));
  app.unmount();
  await act(async () => resolve(readerSuccess({ backend: "codex", runtimePath: "/codex", status: "installed", message: "OK" })));
  expect(backendSetup).toHaveBeenCalledOnce();
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
});

it("T2 reports appearance failure separately from a successfully applied backend", async () => {
  render(<BackendSetupPanel host={{ saveBackendConfiguration: vi.fn(async () => readerSuccess(empty)),
    refreshBackendConfiguration: vi.fn(async () => readerSuccess(empty)) } as unknown as ReaderHost} onSaveAppearance={() => false} />);
  fireEvent.click(screen.getByRole("button", { name: "保存并应用" }));
  expect(await screen.findByRole("status")).toHaveTextContent("后端设置已保存并应用；外观未保存");
});

it('default onboarding mounts and changes backend without optional actions', async () => {
  const backendSetup = vi.fn();
  const onDraft = vi.fn();
  render(<BackendSetupPanel host={{ backendSetup } as unknown as ReaderHost} onDraft={onDraft} />);
  expect(screen.getByRole('combobox')).toHaveValue('');
  expect(screen.getAllByRole('option')).toHaveLength(1);
  fireEvent.click(screen.getByRole('radio', { name: 'DeepSeek' }));
  expect(screen.getByRole('combobox')).toHaveValue('');
  expect(backendSetup).not.toHaveBeenCalled();
  expect(screen.queryByRole('button', { name: '保存并应用' })).not.toBeInTheDocument();
  await waitFor(() => expect(onDraft).toHaveBeenLastCalledWith(expect.objectContaining({ backend: 'deepseek' })));
});

it('keeps independent explicit preferences, clears a default override and does not infer on model changes', async () => {
  const backendSetup = vi.fn(async (action: string, input: { backend: string }) => readerSuccess({
    backend: input.backend, runtimePath: '/runtime', status: action === 'prepare' ? 'installed' : 'success',
    message: 'OK', checkedModel: 'default', catalogStatus: 'loaded', models: ['offered'], environmentId: 'one',
  }));
  const configuration = { saved: { backend: 'codex' as const, model: 'published', runtimePath: null, credentialFile: null },
    effective: { backend: 'codex' as const, model: 'published', runtimePath: null, credentialFile: null },
    pending: false, busy: false, refreshBlocked: false,
    preferences: { codex: { model: 'saved-codex' }, deepseek: { model: 'saved-deepseek' } } };
  render(<BackendSetupPanel host={{ backendSetup } as unknown as ReaderHost} configuration={configuration} />);
  expect(screen.getByRole('combobox')).toHaveValue('saved-codex');
  fireEvent.click(screen.getByRole('radio', { name: 'DeepSeek' }));
  expect(screen.getByRole('combobox')).toHaveValue('saved-deepseek');
  fireEvent.click(screen.getByRole('button', { name: '连接检查' }));
  await screen.findByText(/已保存的模型不在当前清单/);
  expect(screen.getByText('当前模型尚未验证。')).toBeInTheDocument();
  const count = backendSetup.mock.calls.length;
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'offered' } });
  expect(backendSetup).toHaveBeenCalledTimes(count);
  fireEvent.click(screen.getByRole('radio', { name: 'Codex' }));
  expect(screen.getByRole('combobox')).toHaveValue('saved-codex');
  expect(screen.queryByRole('option', { name: 'offered' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('radio', { name: 'DeepSeek' }));
  expect(screen.getByRole('combobox')).toHaveValue('offered');
  fireEvent.change(screen.getByRole('combobox'), { target: { value: '' } });
  fireEvent.click(screen.getByRole('radio', { name: 'Codex' }));
  fireEvent.click(screen.getByRole('radio', { name: 'DeepSeek' }));
  expect(screen.getByRole('combobox')).toHaveValue('');
});

it('discards a late response after backend changes', async () => {
  let resolve!: (value: ReaderHostResult<BackendSetupResult>) => void;
  const backendSetup = vi.fn(() => new Promise<ReaderHostResult<BackendSetupResult>>(done => { resolve = done; }));
  render(<BackendSetupPanel host={{ backendSetup } as unknown as ReaderHost} />);
  fireEvent.click(screen.getByRole('button', { name: '连接检查' }));
  fireEvent.click(screen.getByRole('radio', { name: 'DeepSeek' }));
  await act(async () => resolve(readerSuccess({ backend: 'codex', runtimePath: '/old', status: 'installed', message: 'old' })));
  expect(screen.getByRole('radio', { name: 'DeepSeek' })).toBeChecked();
  expect(screen.getByRole('combobox')).toHaveValue('');
  expect(backendSetup).toHaveBeenCalledOnce();
});

it('retries a catalog independently of inference and retains default entry', async () => {
  const backendSetup = vi.fn(async (action: string) => readerSuccess({
    backend: 'codex', runtimePath: '/runtime', status: action === 'prepare' ? 'installed' : 'success',
    message: 'OK', checkedModel: 'default', catalogStatus: action === 'models' ? 'loaded' : 'failed',
    catalogMessage: '连接已通过，模型清单加载失败', models: action === 'models' ? ['real'] : [],
  }));
  render(<BackendSetupPanel host={{ backendSetup } as unknown as ReaderHost} />);
  fireEvent.click(screen.getByRole('button', { name: '连接检查' }));
  fireEvent.click(await screen.findByRole('button', { name: '重试模型清单' }));
  await screen.findByRole('option', { name: 'real' });
  expect(backendSetup.mock.calls.map(call => call[0])).toEqual(['prepare', 'check', 'models']);
  expect(screen.getByRole('combobox')).toHaveValue('');
});

it('saves and applies backend settings with getRandomValues-only crypto over HTTP', async () => {
  vi.stubGlobal('crypto', { getRandomValues: (bytes: Uint8Array) => {
    for (let i = 0; i < bytes.length; i++) bytes[i] = 0x42 + i;
    return bytes;
  } });
  const onSaved = vi.fn();
  const saveBackendConfiguration = vi.fn(async () => readerSuccess(empty));
  render(<BackendSetupPanel host={{ saveBackendConfiguration } as unknown as ReaderHost} onSaved={onSaved} />);
  fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));
  await waitFor(() => expect(saveBackendConfiguration).toHaveBeenCalledOnce());
  expect(saveBackendConfiguration).toHaveBeenCalledWith(expect.objectContaining({
    requestId: expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i),
  }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith(empty));
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
