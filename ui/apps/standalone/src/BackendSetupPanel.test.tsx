// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readerSuccess, type BackendConfigurationState, type BackendSetupResult, type ReaderHostResult, type ReaderHost } from "@focus/reader-contracts";
import { BackendSetupPanel } from "./BackendSetupPanel";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const empty = { status: "empty" as const, source: { sourceId: "", title: "", topicId: null }, current: null, history: [], conversation: [] };
const config: BackendConfigurationState = {
  busy: false, pending: false, refreshBlocked: false, saved: null, effective: null,
  backends: ["one", "two"].map(id => ({ id, label: id, available: true, defaultModel: null,
    capabilities: { modelDiscovery: "acp-config-option" } })),
  preferences: { two: { model: "saved-two", credentialFile: "/machine/credentials" } },
};
function response(backend: string, extra: Partial<BackendSetupResult> = {}) {
  return readerSuccess<BackendSetupResult>({ backend, runtimePath: null, status: "success", message: "OK", ...extra });
}
const checkButton = () => screen.getByRole("button", { name: "连接检查" });
const modelSelect = () => screen.getByRole("combobox", { name: "模型" });

it("loads the selected backend automatically and checks and saves the chosen model with one button", async () => {
  const backendSetup = vi.fn<NonNullable<ReaderHost["backendSetup"]>>(async (action, input) => response(input.backend,
    action === "models" ? { catalogStatus: "loaded", models: [input.backend + "-model"] } : { checkedModel: input.model }));
  const saveBackendConfiguration = vi.fn(async () => readerSuccess(empty));
  const onSaved = vi.fn();
  render(<BackendSetupPanel host={{ backendSetup, saveBackendConfiguration } as unknown as ReaderHost} configuration={config} onSaved={onSaved} />);
  expect(screen.getAllByRole("button")).toEqual([checkButton()]);
  expect(checkButton()).toBeDisabled();
  fireEvent.click(screen.getByRole("radio", { name: "one" }));
  await screen.findByRole("option", { name: "one-model" });
  fireEvent.click(screen.getByRole("radio", { name: "two" }));
  await screen.findByRole("option", { name: "two-model" });
  expect(modelSelect()).toHaveValue("saved-two");
  expect(screen.queryByRole("option", { name: "one-model" })).toBeNull();
  fireEvent.change(modelSelect(), { target: { value: "two-model" } });
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
  fireEvent.click(checkButton());
  expect(await screen.findByRole("status")).toHaveTextContent("连接检查通过（two-model），已保存并应用");
  expect(backendSetup.mock.calls.map(([action]) => action)).toEqual(["models", "models", "check"]);
  expect(backendSetup.mock.calls.at(-1)?.[1]).toMatchObject({ backend: "two", model: "two-model" });
  expect(saveBackendConfiguration).toHaveBeenCalledWith(expect.objectContaining({
    backend: "two", model: "two-model", credentialFile: "/machine/credentials", requestId: expect.any(String),
  }));
  expect(onSaved).toHaveBeenCalledWith(empty);
});

it("preselects a sole backend, retries its catalog on focus, and keeps a failed check out of saved settings", async () => {
  let first = true;
  const backendSetup = vi.fn<NonNullable<ReaderHost["backendSetup"]>>(async (action, { backend }) => {
    if (action === "check") return response(backend, { status: "failed", message: "凭据无效" });
    if (first) { first = false; return response(backend, { catalogStatus: "failed", message: "读取超时" }); }
    return response(backend, { catalogStatus: "loaded", models: ["listed"] });
  });
  const saveBackendConfiguration = vi.fn();
  render(<BackendSetupPanel host={{ backendSetup, saveBackendConfiguration } as unknown as ReaderHost}
    configuration={{ ...config, backends: config.backends!.slice(0, 1) }} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("读取超时");
  fireEvent.focus(modelSelect());
  await screen.findByRole("option", { name: "listed" });
  fireEvent.change(modelSelect(), { target: { value: "listed" } });
  fireEvent.click(checkButton());
  expect(await screen.findByRole("alert")).toHaveTextContent("凭据无效");
  expect(modelSelect()).toHaveValue("listed");
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
});

it("discards an in-flight check after unmount or an external configuration change", async () => {
  let resolve!: (value: ReaderHostResult<BackendSetupResult>) => void;
  const backendSetup = vi.fn(() => new Promise<ReaderHostResult<BackendSetupResult>>(done => { resolve = done; }));
  const saveBackendConfiguration = vi.fn();
  const host = { backendSetup, saveBackendConfiguration } as unknown as ReaderHost;
  const view = render(<BackendSetupPanel host={host} />);
  fireEvent.click(checkButton());
  view.rerender(<BackendSetupPanel host={host} configuration={{ ...config, backends: undefined, operationId: "other",
    saved: { backend: "deepseek", model: "external", runtimePath: null, credentialFile: null } }} />);
  await act(async () => resolve(response("codex")));
  expect(modelSelect()).toHaveValue("external");
  fireEvent.click(checkButton());
  view.unmount();
  await act(async () => resolve(response("deepseek")));
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
});

it("rechecks an already applied model without resetting the host session", async () => {
  const saved = { backend: "two", model: "saved-two", credentialFile: "/machine/credentials", runtimePath: null };
  const backendSetup = vi.fn<NonNullable<ReaderHost["backendSetup"]>>(async (action, input) =>
    response(input.backend, action === "models" ? { catalogStatus: "loaded", models: ["saved-two"] } : { checkedModel: input.model }));
  const saveBackendConfiguration = vi.fn();
  render(<BackendSetupPanel host={{ backendSetup, saveBackendConfiguration } as unknown as ReaderHost}
    configuration={{ ...config, saved, effective: saved }} />);
  await waitFor(() => expect(checkButton()).toBeEnabled());
  fireEvent.click(checkButton());
  expect(await screen.findByRole("status")).toHaveTextContent("连接检查通过（saved-two）");
  expect(saveBackendConfiguration).not.toHaveBeenCalled();
});
