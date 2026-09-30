// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readerSuccess, type BackendSetupResult, type ReaderHostResult, type ReaderHost } from "@focus/reader-contracts";
import { BackendSetupPanel } from "./BackendSetupPanel";

afterEach(cleanup);
const empty = { status: "empty" as const, source: { sourceId: "", title: "", topicId: null }, current: null, history: [], conversation: [] };

it("checks without applying, then saves and applies only on explicit confirmation", async () => {
  const backendSetup = vi.fn(async (action: string, input: { backend: string }) => readerSuccess({
    backend: input.backend, runtimePath: "/private/runtime", status: action === "prepare" ? "installed" : "success", message: "OK",
  }));
  const saveBackendConfiguration = vi.fn(async () => readerSuccess(empty));
  const refreshBackendConfiguration = vi.fn(async () => readerSuccess(empty));
  const host = { backendSetup, saveBackendConfiguration, refreshBackendConfiguration } as unknown as ReaderHost;
  render(<BackendSetupPanel host={host} />);
  fireEvent.click(screen.getByRole("radio", { name: "DeepSeek" }));
  fireEvent.change(screen.getByRole("combobox", { name: "模型" }), { target: { value: "deepseek-flash" } });
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "连接检查" }));
  await screen.findByText("连接检查通过；点击保存设置后启用。");
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
  expect(refreshBackendConfiguration).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
  await waitFor(() => expect(refreshBackendConfiguration).toHaveBeenCalledOnce());
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
  fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
  expect(await screen.findByRole("status")).toHaveTextContent("后端设置已保存并应用；外观未保存");
});
