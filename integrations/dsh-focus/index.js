import { randomUUID } from 'node:crypto'
import { spawn } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { TypertRemoteService, Remote } from '@deepseek-ai/dsh-typert-protocol'
import { SessionId } from '@deepseek-ai/dsh-session'
import { createUserMessage } from '@deepseek-ai/dsh-llm'
import { defineTool } from '@deepseek-ai/dsh-tools'
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
  static inject = ['sessionController', 'workspaceRegistry', 'agents', 'tools']

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
    this.liveAttempts = new Map()
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
    for (const attempt of Object.values(this.attempts).filter(attempt => attempt.active)) {
      attempt.active = false
      attempt.businessStatus = 'failed'
      attempt.error = 'host_interrupted'
      await this._cleanup(attempt.attemptId, 'failed')
    }
  }

  async listSources() { return this.worker.request('listSources') }

  async status(sourceId) {
    await this.recovery
    const status = await this.worker.request('status', { sourceId })
    const sourceAttempts = Object.values(this.attempts).filter(item => item.sourceId === sourceId)
    const attempt = sourceAttempts.find(item => item.active)
    const latestAttempt = sourceAttempts.at(-1)
    if (attempt?.kind === 'dsh-live') {
      return { ...status, runStatus: 'running', error: null, dshAttempt: attempt }
    }
    if (attempt && ['completed', 'failed', 'cancelled', 'interrupted'].includes(status.runStatus)) {
      attempt.active = false
      await this._cleanup(attempt.attemptId, status.runStatus)
    }
    if (!attempt && latestAttempt?.kind === 'dsh-live') {
      return {
        ...status,
        runStatus: latestAttempt.businessStatus,
        error: latestAttempt.error ? { error_id: latestAttempt.error } : null,
        dshAttempt: latestAttempt,
      }
    }
    return { ...status, dshAttempt: attempt ?? latestAttempt ?? null }
  }

  async regenerate(sourceId, requestId, hold) {
    if (Object.values(this.attempts).some(item => item.active)) throw new Error('A FOCUS AI attempt is already active')
    const attemptId = randomUUID()
    const sessionId = `focus-${attemptId}`
    await this.ctx.sessionController.create({ cwd: this.workspace, sessionId })
    const attempt = { attemptId, sessionId, sourceId, requestId, kind: 'controlled', active: true, businessStatus: 'running', cleanupStatus: 'pending' }
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

  async liveRegenerate(sourceId, requestId) {
    const provider = process.env.FOCUS_DSH_AI_PROVIDER || 'deepseek-official'
    const model = process.env.FOCUS_DSH_AI_MODEL || 'deepseek-v4-flash'
    const credentialName = provider === 'deepseek-official' ? 'DEEPSEEK_API_KEY'
      : provider === 'anthropic' ? 'ANTHROPIC_API_KEY' : undefined
    if (!credentialName || !process.env[credentialName]) {
      throw new Error(`No supported credential is configured for ${provider}`)
    }
    if (Object.values(this.attempts).some(item => item.active)) throw new Error('A FOCUS AI attempt is already active')
    const context = await this.worker.request('liveContext', { sourceId })
    const attemptId = randomUUID()
    const sessionId = `focus-${attemptId}`
    const submitted = Promise.withResolvers()
    let submittedOnce = false
    const textOutput = {
      schema: {
        type: 'object', additionalProperties: false,
        properties: { text: { type: 'string', required: true } },
      },
      render: (_args, value) => [{ type: 'text', text: value.text }],
    }
    let handle
    try {
      handle = await this.ctx.agents.create({
        sessionId: SessionId(sessionId),
        meta: { cwd: this.workspace },
        agentOptions: {
          provider,
          model,
        },
        setup: agentCtx => {
        // Mask every inherited/global tool, then add exactly three scope-local tools.
        agentCtx.tools.restrict({ allow: [] })
        agentCtx.tools.register(defineTool({
          name: 'focus_read_bundle',
          description: 'Read the selected public Paper Source bundle. This is the only source-reading capability.',
          parameters: {}, output: textOutput,
          async execute() {
            return { text: `${context.bundle}\n\nAvailable images: ${context.images.join(', ') || '(none)'}` }
          },
        }))
        agentCtx.tools.register(defineTool({
          name: 'focus_read_method',
          description: 'Read the FOCUS Reading Blog method. This is the only method-resource capability.',
          parameters: {}, output: textOutput,
          async execute() { return { text: context.method } },
        }))
        agentCtx.tools.register(defineTool({
          name: 'focus_submit_candidate',
          description: 'Submit one Reading Blog candidate and its evidence map to FOCUS validation. This does not publish directly.',
          parameters: {
            blog: { type: 'string', required: true, description: 'Complete Chinese blog.md candidate.' },
            evidenceMap: { type: 'string', required: true, description: 'Complete evidence/evidence-map.md candidate.' },
          },
          output: {
            schema: {
              type: 'object', additionalProperties: false,
              properties: { accepted: { type: 'boolean', required: true } },
            },
            render: (_args, value) => [{ type: 'text', text: value.accepted ? 'Candidate received for validation.' : 'Candidate rejected.' }],
          },
          async execute(args, exec) {
            if (submittedOnce) throw new Error('a candidate was already submitted')
            submittedOnce = true
            submitted.resolve({
              'blog.md': args.blog,
              'evidence/evidence-map.md': args.evidenceMap,
            })
            exec.concludeTurn()
            return { accepted: true }
          },
        }))
        },
      })
    } catch (error) {
      await this.archives.archive(sessionId, 'failed')
      throw error
    }

    const attempt = {
      attemptId, sessionId, sourceId, requestId, kind: 'dsh-live', active: true,
      businessStatus: 'running', cleanupStatus: 'pending',
      runtime: {
        provider: handle.agent.options.provider,
        model: handle.agent.options.model,
        authentication: `${credentialName} environment credential reference`,
      },
    }
    this.attempts[attemptId] = attempt
    const live = { handle, cancelled: false, disposed: false, stage: 'model' }
    this.liveAttempts.set(attemptId, live)
    try {
      const toolNames = this.ctx.tools.schemas(handle.agent).map(tool => tool.name).sort()
      const denial = await this.ctx.tools.execute({
        callId: `focus-denied-${attemptId}`, name: 'bash', arguments: { command: 'echo forbidden' },
        agent: handle.agent, signal: new AbortController().signal,
      })
      attempt.permissions = {
        tools: toolNames,
        deniedProbe: { tool: 'bash', rejected: denial.isError === true, code: denial.error?.info?.code ?? 'UNKNOWN_TOOL' },
      }
      if (toolNames.join(',') !== 'focus_read_bundle,focus_read_method,focus_submit_candidate' || !denial.isError) {
        throw new Error('restricted DSH tool preflight failed')
      }
      this._saveState()
    } catch (error) {
      await this._disposeLive(attemptId, live)
      await this.archives.archive(sessionId, 'failed')
      delete this.attempts[attemptId]
      throw error
    }

    void this._runLiveAttempt(attempt, live, submitted)
    return { accepted: true, attempt }
  }

  async _runLiveAttempt(attempt, live, submitted) {
    try {
      live.handle.agent.followup(createUserMessage({
        content: [{ type: 'text', text: [
          'Write one Chinese Reading Blog for the selected public paper.',
          'You must call focus_read_bundle and focus_read_method before writing.',
          'Then call focus_submit_candidate exactly once with a complete blog and evidence map.',
          'The blog must follow the method headings, exceed 3000 Chinese characters, use only grounded claims,',
          'include the available Figure 1 as ![Figure 1](assets/image-001.png), and end with a references section.',
          'Do not attempt shell, network, arbitrary filesystem access, or publication.',
        ].join(' ') }],
        source: { kind: 'user' },
      }))
      const candidate = await Promise.race([
        submitted.promise,
        live.handle.agent.whenIdle().then(() => { throw new Error('model finished without submitting a candidate') }),
        new Promise((_, reject) => setTimeout(() => reject(new Error('live model candidate timed out')), 180_000)),
      ])
      if (live.cancelled) throw new Error('live attempt cancelled')
      await live.handle.agent.whenIdle()
      live.stage = 'worker'
      await this.worker.request('regenerateLive', {
        sourceId: attempt.sourceId, requestId: attempt.requestId, attemptId: attempt.attemptId, files: candidate,
      })
      let status
      const deadline = Date.now() + 60_000
      do {
        status = await this.worker.request('status', { sourceId: attempt.sourceId })
        if (['completed', 'failed', 'cancelled'].includes(status.runStatus)) break
        await new Promise(resolveWait => setTimeout(resolveWait, 100))
      } while (Date.now() < deadline)
      if (!status || !['completed', 'failed', 'cancelled'].includes(status.runStatus)) throw new Error('FOCUS candidate validation timed out')
      attempt.businessStatus = status.runStatus
      attempt.validation = {
        readingBlog: status.artifacts?.reading_blog?.status,
        html: status.artifacts?.html?.status,
        warnings: status.warnings ?? [],
      }
      if (status.runStatus !== 'completed') throw new Error(status.error?.error_id ?? 'candidate_validation_failed')
    } catch (error) {
      if (!live.cancelled) {
        attempt.businessStatus = 'failed'
        attempt.error = error?.code ?? error?.name ?? 'live_runtime_failed'
      }
    } finally {
      await this._disposeLive(attempt.attemptId, live)
      attempt.active = false
      await this._cleanup(attempt.attemptId, attempt.businessStatus ?? 'failed')
    }
  }

  async _disposeLive(attemptId, live) {
    if (live.disposed) return
    live.disposed = true
    try { await live.handle.dispose() } finally { this.liveAttempts.delete(attemptId) }
  }

  async cancel(attemptId) {
    const attempt = this.attempts[attemptId]
    if (!attempt || !attempt.active) throw new Error('FOCUS attempt is not active')
    const live = this.liveAttempts.get(attemptId)
    if (live) {
      live.cancelled = true
      live.handle.agent.cancel({ kind: 'user' })
      if (live.stage === 'worker') {
        try { await this.worker.request('cancel', { sourceId: attempt.sourceId, attemptId }) } catch {}
      }
      await this._disposeLive(attemptId, live)
      attempt.active = false
      attempt.businessStatus = 'cancelled'
      await this._cleanup(attemptId, 'cancelled')
      return { sourceId: attempt.sourceId, runStatus: 'cancelled', stopRequested: true, dshAttempt: attempt }
    }
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

for (const name of ['listSources', 'status', 'regenerate', 'liveRegenerate', 'cancel', 'open']) exposeRemote(name)

export default FocusService
