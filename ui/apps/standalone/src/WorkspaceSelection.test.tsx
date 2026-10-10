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

it.each(['import', 'create'] as const)('opens a %s workspace when crypto.randomUUID is unavailable on HTTP', async mode => {
  const opened = vi.fn();
  const withoutRandomUUID = { getRandomValues: (array: Uint8Array) => {
    for (let i = 0; i < array.length; i++) array[i] = i + 1;
    return array;
  } };
  vi.stubGlobal('crypto', withoutRandomUUID);
  const next = { ...status, bound: true, workspace: { path: '/tmp/reader', workspaceId: 'ws', instanceId: 'instance' }, operationId: 'accepted' };
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, value: next }) });
  vi.stubGlobal('fetch', fetcher);
  render(<WorkspaceSelection status={status} onOpened={opened} />);
  if (mode === 'create') fireEvent.click(screen.getByRole('radio', { name: '新建工作区' }));
  fireEvent.change(screen.getByLabelText(mode === 'create' ? '父目录' : '工作区目录'), { target: { value: '/tmp/reader' } });
  fireEvent.click(screen.getByRole('button', { name: '进入工作台' }));
  await waitFor(() => expect(opened).toHaveBeenCalledWith(next));
  const request = JSON.parse(fetcher.mock.calls[0][1].body);
  expect(request).toEqual(expect.objectContaining({ mode, requestId: expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i) }));
  expect(screen.queryByText('正在打开…')).not.toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
