import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

describe('FOCUS DSH native entry', () => {
  it('registers a root panel and sidebar entry without touching a Session service', () => {
    const source = readFileSync(resolve('integrations/dsh-focus/client.js'), 'utf8')
    let plugin: { inject: string[]; apply(ctx: unknown): void } | undefined
    const load = vi.fn((registration: { factory(require: (id: string) => unknown): unknown }) => {
      plugin = registration.factory((id) => {
        if (id !== 'react') throw new Error(`unexpected browser dependency: ${id}`)
        return { createElement: vi.fn() }
      }) as typeof plugin
    })
    const evaluate = new Function('window', source)
    evaluate({ __ModuleLoader__: { load } })

    const entries: Array<{ options: Record<string, unknown>; component: unknown }> = []
    const ctx = {
      slots: {
        inject: (_name: string, register: () => unknown) => register(),
        register: (options: Record<string, unknown>, component: unknown) => {
          entries.push({ options, component })
          return () => undefined
        },
      },
      layout: {},
      get sessions(): never {
        throw new Error('opening the FOCUS panel must not access Sessions')
      },
    }
    expect(plugin?.inject).toEqual(['slots', 'layout'])
    plugin?.apply(ctx)
    expect(entries.map(entry => entry.options)).toEqual([
      { name: 'main', key: 'focus-library', label: 'FOCUS 知识库' },
      { name: 'sidebar.panellist', id: 'focus-library', order: 12, label: 'FOCUS 知识库' },
    ])
  })
})
