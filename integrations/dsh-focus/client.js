window.__ModuleLoader__.load({
  id: '@focus/dsh-native',
  factory(require) {
    const React = require('react')
    const h = React.createElement
    const PANEL_ID = 'focus-library'
    let mountedFocus
    let mountedRemoteError = ''
    let currentSource = 'Fixture-paper'
    let currentStatus = null

    const method = (name, parameters = []) => ({
      id: `@focus/dsh-native#focus/${name}`,
      service: 'focusService', namespace: 'focus', method: name,
      invocation: { kind: 'direct' },
      parameters: parameters.map(parameter => ({
        name: parameter, wire: parameter, source: 'json',
        codec: {
          mode: 'strict',
          typeSymbol: `@focus/dsh-native#${name}:${parameter}`,
          create: () => ({
            parse(value) {
              const expected = parameter === 'hold' ? 'boolean' : 'string'
              if (typeof value !== expected) throw new TypeError(`${parameter} must be ${expected}`)
              return value
            },
          }),
        },
      })),
      result: { mode: 'src-json' },
    })
    const remoteContribution = {
      package: '@focus/dsh-native',
      descriptors: [
        method('listSources'), method('status', ['sourceId']),
        method('regenerate', ['sourceId', 'requestId', 'hold']), method('cancel', ['attemptId']),
        method('liveRegenerate', ['sourceId', 'requestId']),
        method('open', ['sourceId']),
      ],
    }

    function unwrap(result) {
      if (result?.ok) return result.value
      throw new Error(result?.error?.message ?? 'DSH Remote 调用失败')
    }

    function FocusLibraryPanel() {
      const focus = mountedFocus

      function show(error = '') {
        const statusNode = window.document.querySelector('[data-focus-run-status]')
        if (statusNode) statusNode.textContent = error || `状态：${currentStatus?.runStatus ?? '加载中'}；清理：${currentStatus?.dshAttempt?.cleanupStatus ?? '无活动 attempt'}`
      }

      async function refresh() {
        try { currentStatus = unwrap(await focus.status(currentSource)); show() }
        catch (failure) { show(String(failure)) }
      }

      async function regenerate(hold = false) {
        try {
          const requestId = `dsh-${Date.now()}`
          await focus.regenerate(currentSource, requestId, hold).then(unwrap)
          await refresh()
        } catch (failure) { show(String(failure)) }
      }

      async function cancel() {
        try {
          await focus.cancel(currentStatus?.dshAttempt?.attemptId).then(unwrap)
          await refresh()
        } catch (failure) { show(String(failure)) }
      }

      async function liveRegenerate() {
        try {
          const requestId = `dsh-live-${Date.now()}`
          await focus.liveRegenerate(currentSource, requestId).then(unwrap)
          await refresh()
        } catch (failure) { show(String(failure)) }
      }

      async function openBlog() {
        try {
          const target = window.document.querySelector('[data-focus-blog-document]')
          if (target) target.innerHTML = unwrap(await focus.open(currentSource)).document
        } catch (failure) { show(String(failure)) }
      }

      const button = { marginRight: 8, padding: '7px 12px' }
      return h('main', {
        'data-focus-native-panel': '',
        style: { boxSizing: 'border-box', height: '100%', overflow: 'auto', padding: 'calc(var(--dsh-frame-top-clearance, 48px) + 24px) 32px 32px' },
      },
      h('p', { style: { margin: '0 0 8px', opacity: 0.65, fontSize: 13 } }, 'FOCUS · Stage 2D'),
      h('h1', { style: { margin: '0 0 12px', fontSize: 28 } }, '知识库'),
      h('p', null, '原生入口通过 DSH Remote 驱动受管理 Python worker；业务状态由共享 BlogApplication 持久化。'),
      h('p', null, '公开样例：Fixture Paper'),
      h('p', { 'data-focus-run-status': '', role: mountedRemoteError ? 'alert' : undefined }, mountedRemoteError || `状态：${currentStatus?.runStatus ?? '加载中'}；清理：${currentStatus?.dshAttempt?.cleanupStatus ?? '无活动 attempt'}`),
      h('div', { style: { margin: '16px 0' } },
        h('button', { style: button, onClick: () => regenerate(false) }, '重新生成'),
        h('button', { style: button, onClick: () => regenerate(true) }, '开始取消演练'),
        h('button', { style: button, onClick: liveRegenerate }, '真实受限 AI'),
        h('button', { style: button, onClick: cancel }, '取消'),
        h('button', { style: button, onClick: openBlog }, '打开博客'),
        h('button', { style: button, onClick: () => refresh() }, '刷新状态')),
      h('section', { 'data-focus-blog-document': '', style: { borderTop: '1px solid currentColor', paddingTop: 20 } }))
    }

    function FocusLibraryIcon({ size = 18, active = false }) {
      return h('svg', { viewBox: '0 0 24 24', width: size, height: size, 'aria-hidden': true, fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, style: { opacity: active ? 1 : 0.72 } },
        h('path', { d: 'M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5z' }),
        h('path', { d: 'M20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5z' }))
    }

    return {
      inject: ['slots', 'layout', 'remote'],
      async apply(ctx) {
        let disposeRemote = async () => {}
        let remoteError = ''
        try { disposeRemote = await ctx.remote.$mount(remoteContribution) }
        catch (failure) { remoteError = String(failure) }
        mountedRemoteError = remoteError
        const disposePanel = ctx.inject(['remote.focus'], focusCtx => {
          mountedFocus = focusCtx.remote.focus
          focusCtx.slots.inject('main', () => focusCtx.slots.register({ name: 'main', key: PANEL_ID, label: 'FOCUS 知识库' }, FocusLibraryPanel))
          focusCtx.slots.inject('sidebar.panellist', () => focusCtx.slots.register({ name: 'sidebar.panellist', id: PANEL_ID, order: 12, label: 'FOCUS 知识库' }, FocusLibraryIcon))
        })
        return async () => { await disposePanel(); await disposeRemote() }
      },
    }
  },
})
