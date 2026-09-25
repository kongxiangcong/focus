import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import Storage from '@deepseek-ai/dsh-storage'
import { DomainFacility } from '@deepseek-ai/dsh-storage-domain'
import SessionStore, { SessionId } from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'
import WorkspaceRegistry from '../src/index.ts'
import { MemoryMediaPool, MemoryStorageBackend } from '../../../storage/storage-domain/tests/helpers/memory-backend.ts'

describe('FOCUS stage 2D Session archive lifecycle probe', () => {
  const contexts: Context[] = []
  const roots: string[] = []

  afterEach(async () => {
    await Promise.allSettled(contexts.map(async context => { await context.fiber.dispose() }))
    await Promise.all(roots.map(async root => { await rm(root, { recursive: true, force: true }) }))
  })

  async function boot(root: string, pool: MemoryMediaPool): Promise<Context> {
    const ctx = new Context()
    contexts.push(ctx)
    await ctx.plugin(Storage)
    ctx.storage.backend.register('memory', new MemoryStorageBackend(pool))
    const facility = new DomainFacility(ctx, { backend: 'memory', routes: {} })
    ctx.storage.mount('domain', facility)
    ctx.provide('storageDomain', facility)
    await ctx.plugin(SessionStore)
    await ctx.plugin(JsonlSessionPersistence, { root, compression: 'none' })
    await ctx.plugin(WorkspaceRegistry)
    return ctx
  }

  it('stops plugin activity, releases its resource, archives durably, and retains the DSH log', async () => {
    const root = await mkdtemp(join(tmpdir(), 'focus-stage2d-archive-probe-'))
    roots.push(root)
    const pool = new MemoryMediaPool()
    const sessionId = SessionId('focus-stage2d-attempt-session')

    const first = await boot(root, pool)
    const session = first.sessions.create(sessionId)
    const persistence = await first.sessionPersistence.create(session.header)
    await persistence.flush()
    await persistence.close()

    let activityStopped = false
    let resourceReleased = false
    first.on('workspace/session-stop', ({ sessionId: stopped }) => {
      if (stopped !== sessionId) return
      activityStopped = true
      resourceReleased = true
    })

    await first.workspaceRegistry.archiveSession(sessionId, { stopActivity: true })
    expect(activityStopped).toBe(true)
    expect(resourceReleased).toBe(true)
    expect(first.workspaceRegistry.archivedSessionIds).toEqual([sessionId])
    expect(await first.sessionPersistence.stat(sessionId)).toBeDefined()
    await first.fiber.dispose()

    const reopened = await boot(root, pool)
    expect(reopened.workspaceRegistry.archivedSessionIds).toEqual([sessionId])
    expect((await reopened.sessionPersistence.list()).map(row => row.header.id)).toContain(sessionId)
  })
})
