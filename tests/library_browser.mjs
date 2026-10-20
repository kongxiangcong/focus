// Run against an isolated standalone Vite/preview server (not a user's FOCUS service):
// FOCUS_TEST_URL=http://127.0.0.1:5281 FOCUS_PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs node tests/library_browser.mjs
// All ReaderHost HTTP responses are synthetic. No Python fixture, real workspace, screenshots or new dependencies.
import assert from 'node:assert/strict';
import fs from 'node:fs';
const { chromium } = await import(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const output = process.env.FOCUS_BROWSER_OUTPUT || '/tmp/focus-library-redesign/browser';
const url = process.env.FOCUS_TEST_URL || `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT || 5281}`;
const results = [];
const source = (id, title, completed, topicIds = ['architecture']) => ({ sourceId: id, title, kind: 'paper', format: 'PDF', parseStatus: 'ready', error: null, noteCount: 2, topicIds, readingStatus: completed === 4 ? 'completed' : completed ? 'reading' : 'ready', progress: { completed, total: 4, planId: 'plan-001', chunkId: completed === 4 ? null : 'chunk-002' } });
const initialSources = [source('a-paper', 'Alpha Paper', 1), source('b-paper', 'Beta Paper', 0), source('c-paper', 'Gamma Paper', 4), source('unfiled-paper', 'Unfiled Paper', 0, [])];
const emptyWindow = { status: 'empty', current: null, history: [], conversation: [], source: { sourceId: '', title: '', topicId: null }, sessionId: 'library-browser' };
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE });
async function fixture({ empty = false, offline = false, width = 1440, theme = 'light', reduced = false, systemReduced = false } = {}) {
  const context = await browser.newContext({ viewport: { width, height: 1000 }, reducedMotion: systemReduced ? 'reduce' : 'no-preference' });
  await context.addInitScript(({ theme, reduced }) => { localStorage.setItem('focus.theme', theme); localStorage.setItem('focus.libraryView', 'list'); localStorage.setItem('focus.reducedMotion', String(reduced)); }, { theme, reduced });
  const page = await context.newPage(); page.setDefaultTimeout(10000);
  const state = { sources: empty ? [] : structuredClone(initialSources), order: ['a-paper', 'b-paper', 'c-paper'], offline, failNext: false, reorders: [], errors: [], requests: [] };
  page.on('pageerror', error => state.errors.push(error.message));
  await page.route(/\/(reader|library)\//, async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    state.requests.push({ path, method: request.method() });
    const ok = value => route.fulfill({ json: { ok: true, value } });
    const failure = message => route.fulfill({ status: 503, json: { ok: false, error: { code: 'unavailable', message, retryable: true } } });
    if (path === '/reader/workspace') return ok({ bound: true });
    if (path === '/reader/events') return route.fulfill({ contentType: 'text/event-stream', body: `event: snapshot\ndata: ${JSON.stringify({ ok: true, value: emptyWindow })}\n\n` });
    if (path.startsWith('/reader/')) return ok(emptyWindow);
    if (path === '/library/topics') return ok([{ topicId: 'architecture', title: '架构探索', sourceIds: state.sources.length ? state.order : [] }, { topicId: 'empty-topic', title: '空专题', sourceIds: [] }]);
    if (path === '/library/sources') return state.offline ? failure('Synthetic source-list outage') : ok(state.sources);
    if (path === '/library/topics/architecture/reorder') {
      const payload = request.postDataJSON(); state.reorders.push(payload);
      if (state.failNext) { state.failNext = false; return failure('Synthetic reorder failure'); }
      state.order = [...payload.sourceIds]; return ok({});
    }
    if (/\/library\/sources\/[^/]+\/blog$/.test(path)) return ok({ sourceId: path.split('/')[3], generated: false, methodVersion: 'fixture', runStatus: 'idle', artifacts: { reading_blog: { status: 'pending', updatedAt: null }, value_analysis: { status: 'pending', updatedAt: null }, html: { status: 'pending', updatedAt: null } }, valueAnalysis: { applicable: null, direction: null, reason: null }, verificationLevel: 'paper_reading', warnings: [], error: null });
    if (path === '/library/inbox' || path === '/library/batches') return ok([]);
    throw new Error(`Unexpected mock request: ${request.method()} ${path}`);
  });
  await page.goto(`${url}/library`);
  // Also exercises route remount after StrictMode's initial cleanup, like upload_dialog_browser.
  await page.getByRole('link', { name: '设置', exact: true }).click();
  await page.getByRole('link', { name: '知识库', exact: true }).click();
  if (empty || offline) await page.locator('.library-empty[data-kind]').waitFor();
  else await page.locator('#source-title-a-paper').waitFor();
  return { page, state, context };
}
async function scenario(name, options, action) {
  const f = await fixture(options);
  try { await action(f); assert.deepEqual(f.state.errors, []); results.push({ name, status: 'PASS' }); console.log(`PASS: ${name}`); }
  finally { await f.context.close(); }
}
const title = (page, id) => page.locator(`#source-title-${id}`);
const row = (page, id) => page.locator(`.library-source-row[data-source-id="${id}"]`);
const panel = page => page.locator('.library-inspector');
async function orderIs(page, ids) { await page.waitForFunction(expected => JSON.stringify([...document.querySelectorAll('.library-source-row')].map(node => node.dataset.sourceId)) === JSON.stringify(expected), ids); }
async function sortable(page) { await page.waitForFunction(() => document.querySelector('.library-source-ordinal')?.getAttribute('draggable') === 'true'); }
async function focusIs(page, id) { await page.waitForFunction(expected => document.activeElement?.id === expected, id); }
async function topic(page, id = 'architecture') {
  const selector = page.getByRole('combobox', { name: '筛选专题' });
  if (await selector.isVisible()) await selector.selectOption(id);
  else await page.locator('.workspace-nav').getByRole('button', { name: id === 'architecture' ? /^架构探索/ : /^空专题/ }).click();
}
async function drag(page, from, to, beforeDrop) {
  const transfer = await page.evaluateHandle(() => new DataTransfer());
  try {
    await row(page, from).locator('.library-source-ordinal').dispatchEvent('dragstart', { dataTransfer: transfer });
    await row(page, to).dispatchEvent('dragover', { dataTransfer: transfer });
    await row(page, to).dispatchEvent('dragover', { dataTransfer: transfer });
    await beforeDrop();
    await row(page, to).dispatchEvent('drop', { dataTransfer: transfer });
    await row(page, from).locator('.library-source-ordinal').dispatchEvent('dragend', { dataTransfer: transfer });
  } finally { await transfer.dispose(); }
}
async function closed(page, id) {
  await page.waitForFunction(() => { const p = document.querySelector('.library-inspector'); return p?.getAttribute('aria-hidden') === 'true' && p.hasAttribute('inert') && getComputedStyle(p).visibility === 'hidden'; });
  assert.equal(await page.getByRole('complementary', { name: '来源详情' }).count(), 0);
  assert.equal(await page.getByRole('dialog', { name: '来源详情' }).count(), 0);
  await focusIs(page, `source-title-${id}`);
}
try {
  await scenario('details, visible-row arrows, Escape and menu focus return', {}, async ({ page, state }) => {
    await title(page, 'a-paper').focus(); await title(page, 'a-paper').press('ArrowDown'); await focusIs(page, 'source-title-b-paper');
    await title(page, 'b-paper').press('ArrowUp'); await focusIs(page, 'source-title-a-paper');
    await title(page, 'a-paper').press('Enter'); await page.getByRole('complementary', { name: '来源详情' }).waitFor();
    assert.equal(await title(page, 'a-paper').getAttribute('aria-expanded'), 'true');
    await title(page, 'a-paper').press('ArrowDown'); await panel(page).getByRole('heading', { name: 'Beta Paper', exact: true }).waitFor();
    await title(page, 'b-paper').press('Escape'); await closed(page, 'b-paper');
    await page.locator('#source-more-trigger-b-paper').click(); await page.locator('#source-more-trigger-b-paper').press('Escape');
    await focusIs(page, 'source-more-trigger-b-paper');
    await title(page, 'a-paper').click();
    await page.getByRole('searchbox', { name: '搜索材料' }).focus(); await page.getByRole('searchbox', { name: '搜索材料' }).press('Escape'); await closed(page, 'a-paper');
    await title(page, 'a-paper').click(); await page.locator('#source-more-trigger-a-paper').click();
    await page.getByRole('searchbox', { name: '搜索材料' }).focus(); await page.getByRole('searchbox', { name: '搜索材料' }).press('Escape');
    await focusIs(page, 'source-more-trigger-a-paper'); assert.equal(await panel(page).getAttribute('data-open'), 'true', 'first header Escape closes only the menu');
    await page.getByRole('searchbox', { name: '搜索材料' }).focus(); await page.getByRole('searchbox', { name: '搜索材料' }).press('Escape'); await closed(page, 'a-paper');
    assert.equal(state.requests.filter(r => r.method === 'POST').length, 0, 'inspection and selection never mutate Host');
  });
  await scenario('drag previews locally, commits once, rolls back and retries; Alt ordering', {}, async ({ page, state }) => {
    await topic(page); await orderIs(page, state.order);
    await drag(page, 'a-paper', 'b-paper', async () => { await orderIs(page, ['b-paper', 'a-paper', 'c-paper']); assert.equal(state.reorders.length, 0); });
    await orderIs(page, ['b-paper', 'a-paper', 'c-paper']);
    await sortable(page);
    assert.deepEqual(state.reorders, [{ sourceIds: ['b-paper', 'a-paper', 'c-paper'] }]);
    state.failNext = true;
    await drag(page, 'a-paper', 'c-paper', async () => { await orderIs(page, ['b-paper', 'c-paper', 'a-paper']); assert.equal(state.reorders.length, 1); });
    await page.locator('.workspace-error').filter({ hasText: 'Synthetic reorder failure' }).waitFor();
    await orderIs(page, ['b-paper', 'a-paper', 'c-paper']); assert.equal(state.reorders.length, 2);
    await page.getByRole('button', { name: '重试此操作', exact: true }).click();
    await orderIs(page, ['b-paper', 'c-paper', 'a-paper']); await sortable(page); assert.equal(state.reorders.length, 3);
    await title(page, 'a-paper').focus(); await title(page, 'a-paper').press('Alt+ArrowUp');
    await orderIs(page, ['b-paper', 'a-paper', 'c-paper']); await focusIs(page, 'source-title-a-paper'); await sortable(page); assert.equal(state.reorders.length, 4);
    await title(page, 'a-paper').press('Alt+ArrowDown'); await orderIs(page, ['b-paper', 'c-paper', 'a-paper']); await focusIs(page, 'source-title-a-paper'); assert.equal(state.reorders.length, 5);
  });
  await scenario('status/search/card sorting guards and scoped counts', {}, async ({ page, state }) => {
    await topic(page); const filters = page.getByRole('group', { name: '按状态筛选' });
    await filters.getByRole('button', { name: /^阅读中/ }).click(); await orderIs(page, ['a-paper']);
    assert.equal(await row(page, 'a-paper').locator('[draggable]').getAttribute('draggable'), 'false');
    await page.getByText('筛选时暂停排序；显示全部状态后可调整专题顺序。', { exact: true }).waitFor();
    await title(page, 'a-paper').press('Alt+ArrowDown'); assert.equal(state.reorders.length, 0);
    await filters.getByRole('button', { name: /^全部/ }).click();
    await page.getByRole('searchbox', { name: '搜索材料' }).fill('Alpha'); await orderIs(page, ['a-paper']);
    assert.equal(await row(page, 'a-paper').locator('[draggable]').getAttribute('draggable'), 'false');
    await page.getByRole('searchbox', { name: '搜索材料' }).fill(''); await page.getByRole('button', { name: '卡片显示', exact: true }).click();
    await page.getByText('切换到列表视图后可调整专题顺序', { exact: true }).waitFor(); assert.equal(await page.locator('.library-source-card').count(), 3);
    assert.equal(await page.locator('.library-source-card [draggable=true]').count(), 0); assert.equal(state.reorders.length, 0);
  });
  await scenario('empty library action', { empty: true }, async ({ page }) => { await page.locator('.library-empty[data-kind=library]').waitFor(); await page.getByRole('button', { name: '上传材料', exact: true }).click(); await page.locator('.workspace-upload[open]').waitFor(); });
  await scenario('source-list offline and reconnect', { offline: true }, async ({ page, state }) => { await page.locator('.library-empty[data-kind=offline]').waitFor(); state.offline = false; await page.getByRole('button', { name: '重新连接', exact: true }).click(); await title(page, 'a-paper').waitFor(); });
  await scenario('search, filter and Topic empty states and recovery', {}, async ({ page }) => {
    await page.getByRole('searchbox', { name: '搜索材料' }).fill('no-such-title'); await page.locator('.library-empty[data-kind=search]').waitFor(); await page.getByRole('button', { name: '清除搜索', exact: true }).click();
    await topic(page, 'empty-topic'); await page.locator('.library-empty[data-kind=topic]').waitFor(); await page.getByRole('button', { name: '查看全部材料', exact: true }).click();
    await page.getByRole('group', { name: '按状态筛选' }).getByRole('button', { name: /^阅读中/ }).click();
    await topic(page, 'empty-topic'); await page.locator('.library-empty[data-kind=filter]').waitFor(); await page.getByRole('button', { name: '显示全部状态', exact: true }).click(); await page.locator('.library-empty[data-kind=topic]').waitFor();
  });
  for (const width of [1440, 1024, 390]) for (const theme of ['light', 'dark']) {
    await scenario(`${width}px ${theme}: geometry, panel role, focus and close`, { width, theme }, async ({ page }) => {
      assert.equal(await page.locator('html').getAttribute('data-theme'), theme);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'page must not overflow horizontally');
      await title(page, 'a-paper').click(); await panel(page).waitFor();
      await page.waitForFunction(() => getComputedStyle(document.querySelector('.library-inspector')).opacity === '1');
      const geometry = await page.evaluate(() => {
        const rect = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { x: r.x, y: r.y, right: r.right, bottom: r.bottom, width: r.width, height: r.height }; };
        return { content: rect('.library-page'), list: rect('.library-source-list'), panel: rect('.library-inspector'), row: rect('.library-source-row'), role: document.querySelector('.library-inspector').getAttribute('role') };
      });
      const docked = geometry.content.width >= 1040 && width > 760;
      assert.equal(geometry.role, docked ? 'complementary' : 'dialog');
      if (docked) assert.ok(geometry.list.right <= geometry.panel.x + 1, JSON.stringify(geometry));
      else assert.equal(await panel(page).evaluate(el => el.contains(document.activeElement)), true);
      assert.ok(geometry.panel.x >= -1 && geometry.panel.right <= width + 1, JSON.stringify(geometry));
      if (width <= 760) {
        assert.equal(await panel(page).getAttribute('aria-modal'), 'true');
        assert.equal(await page.locator('.library-sources').evaluate(el => el.inert), true);
        assert.equal(await page.locator('.workspace-header').evaluate(el => el.inert), true);
        assert.ok(Math.abs(geometry.panel.y - 120) <= 1, JSON.stringify(geometry));
        const targets = await panel(page).locator('button:visible, a:visible').evaluateAll(nodes => nodes.map(el => ({ text: el.textContent, width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height })));
        assert.ok(targets.every(target => target.height >= 40 && target.width >= 40), JSON.stringify(targets));
        await panel(page).press('Tab'); assert.equal(await panel(page).evaluate(el => el.contains(document.activeElement)), true);
      }
      results.push({ name: 'geometry', width, theme, ...geometry });
      await panel(page).press('Escape'); await closed(page, 'a-paper');
      assert.equal(await page.locator('.library-sources').evaluate(el => el.inert), false);
    });
  }
  for (const mode of ['user', 'system']) await scenario(`${mode} reduced motion: no panel/progress/row displacement`, { reduced: mode === 'user', systemReduced: mode === 'system' }, async ({ page }) => {
    await title(page, 'a-paper').click();
    const transforms = await panel(page).evaluate(el => { const css = getComputedStyle(el); return { transform: css.transform, transition: css.transitionProperty }; });
    assert.equal(transforms.transform, 'none'); assert.equal(transforms.transition.includes('transform'), false);
    const durations = await page.locator('.library-progress > span').evaluateAll(nodes => nodes.map(node => getComputedStyle(node).transitionDuration));
    assert.ok(durations.length > 0 && durations.every(duration => duration === '0s'), JSON.stringify(durations));
    await panel(page).press('Escape'); await closed(page, 'a-paper'); assert.equal(await panel(page).evaluate(el => getComputedStyle(el).transform), 'none');
    await topic(page); await title(page, 'a-paper').press('Alt+ArrowDown'); await orderIs(page, ['b-paper', 'a-paper', 'c-paper']);
    const moving = await page.locator('.library-source-row').evaluateAll(rows => rows.reduce((count, row) => count + row.getAnimations().filter(animation => animation.effect?.getKeyframes().some(frame => frame.transform && frame.transform !== 'none')).length, 0));
    assert.equal(moving, 0, 'reduced-motion reorder must not create FLIP animations');
  });
  await scenario('panel reverses from an intermediate frame and finishes closed', {}, async ({ page }) => {
    await title(page, 'a-paper').click(); await panel(page).getByRole('button', { name: '关闭详情' }).click(); await closed(page, 'a-paper');
    const samples = await title(page, 'a-paper').evaluate(trigger => new Promise((resolve, reject) => {
      const pane = document.querySelector('.library-inspector'), started = performance.now(); trigger.click();
      function frame() {
        const opacity = Number(getComputedStyle(pane).opacity);
        if (opacity > .35 && opacity < .75) { pane.querySelector('[aria-label="关闭详情"]').click(); requestAnimationFrame(() => resolve({ opening: opacity, reversing: Number(getComputedStyle(pane).opacity) })); }
        else if (performance.now() - started > 2000) reject(new Error('No intermediate panel frame'));
        else requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    }));
    assert.ok(samples.opening > .35 && samples.opening < .75); assert.ok(samples.reversing > 0 && samples.reversing <= samples.opening + .02 && samples.opening - samples.reversing < .25, JSON.stringify(samples)); await closed(page, 'a-paper'); results.push({ name: 'reversal', ...samples });
  });
} finally {
  fs.mkdirSync(output, { recursive: true }); fs.writeFileSync(`${output}/library-results.json`, JSON.stringify(results, null, 2) + '\n'); await browser.close();
}
