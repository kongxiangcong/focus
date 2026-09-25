import { randomUUID } from 'node:crypto'
import { spawn } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { TypertRemoteService, Remote } from '@deepseek-ai/dsh-typert-protocol'
import { createSessionArchiveTracker } from './session-lifecycle.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const remoteInitializers = []

export class FocusWorker {
  constructor({ python, focusRoot, workspace }) {
    this.nextId = 1
    this.pending = new Map()
    this.buffer = ''
    this.closed = false
    this.process = spawn(python, ['-X', 'utf8', join(HERE, 'worker.py'), '--focus-root', focusRoot, '--workspace', workspace], {
      windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    this.process.stdout.setEncoding('utf8')
    this.process.stdout.on('data', chunk => this.#receive(chunk))
    this.process.stderr.setEncoding('utf8')
    this.process.stderr.on('data', chunk => { this.lastError = (this.lastError ?? '') + chunk })
    this.process.on('exit', (code, signal) => {
      this.closed = true
      const error = new Error(`FOCUS worker exited (${code ?? signal ?? 'unknown'})`)
      for (const { reject } of this.pending.values()) reject(error)
      this.pending.clear()
    })
  }

  #receive(chunk) {
    this.buffer += chunk
    for (;;) {
      const newline = this.buffer.indexOf('\n')
      if (newline < 0) return
      const line = this.buffer.slice(0, newline)
      this.buffer = this.buffer.slice(newline + 1)
      if (!line.trim()) continue
      let message
      try { message = JSON.parse(line) } catch { continue }
      const waiter = this.pending.get(message.id)
      if (!waiter) continue
      this.pending.delete(message.id)
      if (message.ok) waiter.resolve(message.value)
      else waiter.reject(Object.assign(new Error(message.error?.message ?? 'FOCUS worker request failed'), message.error))
    }
  }

  request(method, params = {}) {
    if (this.closed) return Promise.reject(new Error('FOCUS worker is not running'))
    const id = this.nextId++
    return new Promise((resolveRequest, reject) => {
      this.pending.set(id, { resolve: resolveRequest, reject })
      this.process.stdin.write(JSON.stringify({ id, method, params }) + '\n')
    })
  }

  async close(timeout = 5000) {
    if (this.closed) return { stopped: true, forced: false }
    try { await this.request('shutdown') } catch {}
    if (this.closed) return { stopped: true, forced: false }
    const exited = await Promise.race([
      new Promise(resolveExit => this.process.once('exit', () => resolveExit(true))),
      new Promise(resolveTimeout => setTimeout(() => resolveTimeout(false), timeout)),
    ])
    if (!exited) this.process.kill()
    return { stopped: true, forced: !exited }
  }
}

export class FocusService extends TypertRemoteService {
  static inject = ['sessionController', 'workspaceRegistry']

  constructor(ctx, config = {}) {
    super(ctx, 'focusService', { namespace: 'focus' })
    for (const initializer of remoteInitializers) initializer.call(this)
    const focusRoot = resolve(config.focusRoot || process.env.FOCUS_ROOT || join(HERE, '..', '..'))
    this.workspace = resolve(config.workspace || process.env.FOCUS_DSH_WORKSPACE || join(process.env.DSH_HOME || focusRoot, 'focus-stage2d-workspace'))
    mkdirSync(this.workspace, { recursive: true })
    const python = config.python || process.env.FOCUS_PYTHON || join(focusRoot, '.venv', 'Scripts', 'python.exe')
    this.worker = new FocusWorker({ python, focusRoot, workspace: this.workspace })
    this.statePath = join(this.workspace, '.dsh-attempts.json')
    this.attempts = this._readState()
    this.archives = createSessionArchiveTracker((sessionId, options) => ctx.workspaceRegistry.archiveSession(sessionId, options))
    this.recovery = Promise.resolve().then(() => this._recoverPending())
    ctx.effect(() => async () => { await this.worker.close() }, 'focus: stop managed Python worker')
  }

  _readState() {
    try { return JSON.parse(readFileSync(this.statePath, 'utf8')) } catch { return {} }
  }

  _saveState() { writeFileSync(this.statePath, JSON.stringify(this.attempts, null, 2), 'utf8') }

  async _cleanup(attemptId, status) {
    const attempt = this.attempts[attemptId]
    if (!attempt || attempt.cleanupStatus === 'archived') return attempt
    const receipt = await this.archives.archive(attempt.sessionId, status)
    Object.assign(attempt, receipt)
    this._saveState()
    return attempt
  }

  async _recoverPending() {
    for (const attempt of Object.values(this.attempts)) {
      if (!attempt.active && attempt.cleanupStatus === 'pending') {
        await this._cleanup(attempt.attemptId, attempt.businessStatus ?? 'interrupted')
      }
    }
    const active = Object.values(this.attempts).filter(attempt => attempt.active)
    if (active.length === 0) return
    for (const attempt of active) {
      const status = await this.worker.request('status', { sourceId: attempt.sourceId })
      if (!['completed', 'failed', 'cancelled', 'interrupted'].includes(status.runStatus)) continue
      attempt.active = false
      await this._cleanup(attempt.attemptId, status.runStatus)
    }
  }

  async listSources() { return this.worker.request('listSources') }

  async status(sourceId) {
    await this.recovery
    const status = await this.worker.request('status', { sourceId })
    const sourceAttempts = Object.values(this.attempts).filter(item => item.sourceId === sourceId)
    const attempt = sourceAttempts.find(item => item.active)
    if (attempt && ['completed', 'failed', 'cancelled', 'interrupted'].includes(status.runStatus)) {
      attempt.active = false
      await this._cleanup(attempt.attemptId, status.runStatus)
    }
    return { ...status, dshAttempt: attempt ?? sourceAttempts.at(-1) ?? null }
  }

  async regenerate(sourceId, requestId, hold) {
    if (Object.values(this.attempts).some(item => item.active)) throw new Error('A FOCUS AI attempt is already active')
    const attemptId = randomUUID()
    const sessionId = `focus-${attemptId}`
    await this.ctx.sessionController.create({ cwd: this.workspace, sessionId })
    const attempt = { attemptId, sessionId, sourceId, requestId, active: true, cleanupStatus: 'pending' }
    this.attempts[attemptId] = attempt
    try {
      this._saveState()
    } catch (error) {
      await this.archives.archive(sessionId, 'failed')
      delete this.attempts[attemptId]
      throw error
    }
    try {
      await this.worker.request('regenerate', { sourceId, requestId, attemptId, hold: Boolean(hold) })
      return { accepted: true, attempt }
    } catch (error) {
      attempt.active = false
      attempt.error = error instanceof Error ? error.message : String(error)
      await this._cleanup(attemptId, 'failed')
      throw error
    }
  }

  async cancel(attemptId) {
    const attempt = this.attempts[attemptId]
    if (!attempt || !attempt.active) throw new Error('FOCUS attempt is not active')
    const value = await this.worker.request('cancel', { sourceId: attempt.sourceId, attemptId })
    attempt.active = false
    await this._cleanup(attemptId, value.runStatus ?? 'cancelled')
    return { ...value, dshAttempt: attempt }
  }

  async open(sourceId) { return this.worker.request('open', { sourceId }) }
}

function exposeRemote(name) {
  Remote(FocusService.prototype[name], {
    private: false,
    static: false,
    name,
    addInitializer(initializer) { remoteInitializers.push(initializer) },
  })
}

for (const name of ['listSources', 'status', 'regenerate', 'cancel', 'open']) exposeRemote(name)

export default FocusService
