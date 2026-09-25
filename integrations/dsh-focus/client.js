window.__ModuleLoader__.load({
  id: '@focus/dsh-native',
  factory(require) {
    const React = require('react')
    const h = React.createElement
    const PANEL_ID = 'focus-library'

    function FocusLibraryPanel() {
      return h('main', {
        'data-focus-native-panel': '',
        style: {
          boxSizing: 'border-box',
          height: '100%',
          overflow: 'auto',
          padding: 'calc(var(--dsh-frame-top-clearance, 48px) + 24px) 32px 32px',
        },
      },
      h('p', { style: { margin: '0 0 8px', opacity: 0.65, fontSize: 13 } }, 'FOCUS · Stage 2D'),
      h('h1', { style: { margin: '0 0 12px', fontSize: 28 } }, '知识库'),
      h('p', { style: { margin: 0, maxWidth: 680, lineHeight: 1.7 } },
        '这是不绑定聊天 Session 的 FOCUS 原生入口。打开本页不会创建 AI attempt 或 DSH Session。'))
    }

    function FocusLibraryIcon({ size = 18, active = false }) {
      return h('svg', {
        viewBox: '0 0 24 24', width: size, height: size,
        'aria-hidden': true, fill: 'none', stroke: 'currentColor', strokeWidth: 1.8,
        style: { opacity: active ? 1 : 0.72 },
      },
      h('path', { d: 'M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5z' }),
      h('path', { d: 'M20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5z' }))
    }

    return {
      inject: ['slots', 'layout'],
      apply(ctx) {
        ctx.slots.inject('main', () => ctx.slots.register({
          name: 'main', key: PANEL_ID, label: 'FOCUS 知识库',
        }, FocusLibraryPanel))
        ctx.slots.inject('sidebar.panellist', () => ctx.slots.register({
          name: 'sidebar.panellist', id: PANEL_ID, order: 12, label: 'FOCUS 知识库',
        }, FocusLibraryIcon))
      },
    }
  },
})
