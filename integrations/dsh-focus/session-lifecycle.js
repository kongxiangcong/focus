/**
 * Track only the cleanup side of a FOCUS-owned attempt Session.
 * Business completion remains authoritative even when DSH archival fails.
 */
export function createSessionArchiveTracker(archiveSession) {
  const pending = new Map()

  async function archive(sessionId, businessStatus) {
    try {
      await archiveSession(sessionId, { stopActivity: true })
      pending.delete(sessionId)
      return { businessStatus, cleanupStatus: 'archived', sessionId }
    } catch (error) {
      pending.set(sessionId, businessStatus)
      return {
        businessStatus,
        cleanupStatus: 'pending',
        sessionId,
        cleanupError: error instanceof Error ? error.message : String(error),
      }
    }
  }

  async function retryPending() {
    return Promise.all([...pending].map(([sessionId, businessStatus]) =>
      archive(sessionId, businessStatus)))
  }

  return {
    archive,
    retryPending,
    get pendingSessionIds() { return [...pending.keys()] },
  }
}
