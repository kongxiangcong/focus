import { describe, expect, it, vi } from 'vitest'
import { createSessionArchiveTracker } from '../integrations/dsh-focus/session-lifecycle.js'

describe('FOCUS DSH Session cleanup state', () => {
  it('keeps business success while exposing an archive failure and retries it', async () => {
    const archiveSession = vi.fn()
      .mockRejectedValueOnce(new Error('archive unavailable'))
      .mockResolvedValueOnce(undefined)
    const tracker = createSessionArchiveTracker(archiveSession)

    await expect(tracker.archive('focus-attempt-1', 'succeeded')).resolves.toEqual({
      businessStatus: 'succeeded',
      cleanupStatus: 'pending',
      sessionId: 'focus-attempt-1',
      cleanupError: 'archive unavailable',
    })
    expect(tracker.pendingSessionIds).toEqual(['focus-attempt-1'])

    await expect(tracker.retryPending()).resolves.toEqual([{
      businessStatus: 'succeeded',
      cleanupStatus: 'archived',
      sessionId: 'focus-attempt-1',
    }])
    expect(tracker.pendingSessionIds).toEqual([])
    expect(archiveSession).toHaveBeenNthCalledWith(1, 'focus-attempt-1', { stopActivity: true })
    expect(archiveSession).toHaveBeenNthCalledWith(2, 'focus-attempt-1', { stopActivity: true })
  })
})
