import { afterEach, describe, expect, it } from 'vitest'
import { Context } from '@deepseek-ai/cordis'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { SessionId } from '@deepseek-ai/dsh-session'
import SessionStore from '@deepseek-ai/dsh-session'
import JsonlSessionPersistence from '@deepseek-ai/dsh-session-persistence-jsonl'

describe('FOCUS stage 2D session deletion capability probe', () => {
  const contexts: Context[] = []
  const roots: string[] = []

  afterEach(async () => {
    await Promise.allSettled(contexts.map(async context => { await context.fiber.dispose() }))
    await Promise.all(roots.map(async root => { await rm(root, { recursive: true, force: true }) }))
  })

  it('retains a terminated materialized session and exposes no public delete operation', async () => {
    const root = await mkdtemp(join(tmpdir(), 'focus-stage2d-delete-probe-'))
    roots.push(root)

    const materializingContext = new Context()
    contexts.push(materializingContext)
    await materializingContext.plugin(SessionStore)
    await materializingContext.plugin(JsonlSessionPersistence, { root, compression: 'none' })

    const session = materializingContext.sessions.create(SessionId('focus-stage2d-probe-session'))
    const handle = await materializingContext.sessionPersistence.create(session.header)
    await handle.flush()
    await handle.close()
    await materializingContext.fiber.dispose()

    const reopenedContext = new Context()
    contexts.push(reopenedContext)
    await reopenedContext.plugin(SessionStore)
    await reopenedContext.plugin(JsonlSessionPersistence, { root, compression: 'none' })

    expect(await reopenedContext.sessionPersistence.stat(session.id)).toBeDefined()
    expect((await reopenedContext.sessionPersistence.list()).map(row => row.header.id)).toContain(session.id)
    expect('delete' in reopenedContext.sessionPersistence).toBe(false)
  })
})
