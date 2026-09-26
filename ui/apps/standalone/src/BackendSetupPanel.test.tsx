// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readerSuccess, type BackendSetupResult, type ReaderHostResult, type ReaderHost } from "@focus/reader-contracts";
import { BackendSetupPanel } from "./BackendSetupPanel";

afterEach(cleanup);

it("saves the selected configuration without applying it", async () => {
  const saveBackendConfiguration = vi.fn(async () => readerSuccess({ status: "empty" as const, source: { sourceId: "", title: "", topicId: null },
    current: null, history: [], conversation: [] }));
  const refreshBackendConfiguration = vi.fn();
  const host = { saveBackendConfiguration, refreshBackendConfiguration } as unknown as ReaderHost;
  render(<BackendSetupPanel host={host} effective="codex" />);
  fireEvent.click(screen.getByRole("radio", { name: "DeepSeek" }));
  fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
  await act(async () => {});
  expect(saveBackendConfiguration).toHaveBeenCalledWith(expect.objectContaining({ backend: "deepseek", model: "deepseek-v4-flash" }));
  expect(refreshBackendConfiguration).not.toHaveBeenCalled();
  expect(screen.getByText(/当前生效：Codex/)).toBeInTheDocument();
});

it("discards a late success after the selected configuration changes without activating a backend", async () => {
  let resolve!: (value: ReaderHostResult<BackendSetupResult>) => void;
  const backendSetup = vi.fn(() => new Promise<ReaderHostResult<BackendSetupResult>>(done => { resolve = done; }));
  const selectBackend = vi.fn();
  const host = { backendSetup, selectBackend } as unknown as ReaderHost;
  render(<BackendSetupPanel host={host} effective="codex" />);
  fireEvent.click(screen.getByRole("button", { name: "连通性检查" }));
  expect(screen.getByRole("status")).toHaveTextContent("检查中");
  fireEvent.click(screen.getByRole("radio", { name: "DeepSeek" }));
  await act(async () => resolve(readerSuccess({ backend: "codex", runtimePath: "/codex", status: "success", message: "旧配置成功" })));
  expect(screen.getByRole("status")).toHaveTextContent("未检查");
  expect(screen.queryByText("旧配置成功")).not.toBeInTheDocument();
  expect(selectBackend).not.toHaveBeenCalled();
});
