// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { WorkspaceSelection, type WorkspaceBindingStatus } from './WorkspaceSelection';

const status: WorkspaceBindingStatus = { bound: false, workspace: null, savedWorkspace: null, error: null, busy: false, generation: 'test' };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('keeps the draft when the native dialog is cancelled, then accepts a selected path', async () => {
  const fetcher = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, value: { path: null } }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, value: { path: 'D:\\阅读 文件' } }) });
  vi.stubGlobal('fetch', fetcher);
  render(<WorkspaceSelection status={status} />);
  fireEvent.change(screen.getByLabelText('工作区目录'), { target: { value: 'D:\\draft' } });
  fireEvent.click(screen.getByRole('button', { name: '选择目录' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '选择目录' })).toBeEnabled());
  expect(screen.getByLabelText('工作区目录')).toHaveValue('D:\\draft');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '选择目录' }));
  await waitFor(() => expect(screen.getByLabelText('工作区目录')).toHaveValue('D:\\阅读 文件'));
  expect(fetcher.mock.calls.every(([path]) => path === '/reader/workspace/pick')).toBe(true);
});

it('allows manual input after a picker failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('目录选择失败')));
  render(<WorkspaceSelection status={status} />);
  fireEvent.click(screen.getByRole('button', { name: '选择目录' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('目录选择失败');
  expect(screen.getByLabelText('工作区目录')).toBeEnabled();
  expect(screen.getByRole('button', { name: '进入工作台' })).toBeEnabled();
});
