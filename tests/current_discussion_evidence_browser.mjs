import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.FOCUS_BROWSER_URL;
assert.ok(base, 'Set FOCUS_BROWSER_URL to the isolated PDF evidence Host.');
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 950 }, reducedMotion: 'reduce' });
page.setDefaultTimeout(30000);
const navigation = page.getByRole('group', { name: '阅读方式', exact: true });
const conversation = page.getByLabel('文章对话', { exact: true });
const source = page.getByLabel('文章原文', { exact: true });
const original = page.getByRole('button', { name: '原文', exact: true });
const chinese = page.getByRole('button', { name: '中文', exact: true });
const chatTab = navigation.getByRole('button', { name: '对话', exact: true });
const readingTab = navigation.getByRole('button', { name: '精读', exact: true });
const referencedParagraph = source.locator('[data-source-line="266"]');
const originalLink = page.getByRole('link', { name: '打开原件 ↗' });
const answer = name => conversation.locator('[data-role="assistant"]').filter({ hasText: name });
const composer = page.getByRole('textbox', { name: '输入消息' });
const send = page.getByRole('button', { name: '发送', exact: true });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let instance;
page.on('request', request => { instance ||= request.headers()['x-focus-instance']; });

async function host(path, data) {
  const response = await page.request.fetch(new URL(path, base).href, {
    method: data ? 'POST' : 'GET',
    data,
    headers: { 'X-FOCUS-Instance': instance },
  });
  const body = await response.json();
  assert.equal(body.ok, true, JSON.stringify(body));
  return body.value;
}

const snapshot = () => host('/reader/window');
async function readingProgress() {
  const view = await snapshot();
  const sources = await host('/library/sources');
  const { progress } = sources.find(source => source.sourceId === view.source.sourceId);
  return {
    cursor: view.navigationCurrent?.chunkId,
    plan: view.navigationCurrent?.planId,
    readingRevision: view.readingRevision,
    completed: progress.completed,
  };
}

async function ask(name, expectedCitations) {
  await composer.fill(name);
  const [response] = await Promise.all([
    page.waitForResponse(response => response.url().endsWith('/reader/messages') && response.request().method() === 'POST'),
    send.click(),
  ]);
  const result = await response.json();
  assert.equal(result.ok, true, JSON.stringify(result));
  await answer(name).waitFor();
  await page.waitForFunction(({ name, count }) => Array.from(document.querySelectorAll('[data-role="assistant"]'))
    .some(message => message.textContent.includes(name) && message.querySelectorAll('button[data-citation]').length === count),
  { name, count: expectedCitations });
}

async function atFocus(locator) {
  assert.equal(await locator.evaluate(node => node === document.activeElement), true);
}

const citation = (message, number) => message.getByRole('button', { name: String(number), exact: true });
const numberedReturn = (number, location = referencedParagraph) => location.getByRole('button', { name: `返回回答证据 ${number}`, exact: true });
const scrollTop = () => source.evaluate(pane => pane.scrollTop);

async function selectAnswer(message) {
  await message.locator('p').first().click({ position: { x: 3, y: 6 } });
  await page.waitForFunction(node => node.dataset.selected === 'true', await message.elementHandle());
}

async function browseToStart() {
  const point = await source.evaluate(pane => {
    const bounds = pane.getBoundingClientRect();
    return { x: bounds.left + bounds.width / 2, y: bounds.top + bounds.height / 2, distance: pane.scrollHeight };
  });
  await page.mouse.move(point.x, point.y);
  await page.mouse.wheel(0, -point.distance);
  await page.waitForFunction(() => document.querySelector('[aria-label="文章原文"]').scrollTop < 20);
}

async function assertLocated(button, quote) {
  const id = typeof button === 'string' ? button : await button.getAttribute('data-citation');
  const marked = source.locator(`mark.is-active[data-evidence-ids~="${id}"]`);
  await marked.first().waitFor();
  assert.equal((await marked.allTextContents()).join(''), quote);
  await page.waitForFunction(id => {
    const pane = document.querySelector('[aria-label="文章原文"]');
    const { top, bottom } = pane.getBoundingClientRect();
    return [...pane.querySelectorAll(`mark.is-active[data-evidence-ids~="${id}"]`)].every(node => {
      const rect = node.getBoundingClientRect();
      return rect.top >= top && rect.bottom <= bottom;
    });
  }, id);
  assert.equal(await page.getByLabel('原文证据', { exact: true }).count(), 0);
  assert.equal(await page.getByRole('dialog', { name: '选择回答' }).count(), 0);
  assert.equal(await page.getByRole('button', { name: /返回阅读位置|回到刚才位置/ }).count(), 0);
}

try {
  await page.goto(new URL('/reading', base).href);
  await chatTab.click();
  await original.click();
  await referencedParagraph.waitFor();
  const initial = await snapshot();
  await host('/reader/session', { sessionId: initial.sessionId });
  await conversation.locator('[data-message-id]').first().waitFor({ state: 'detached' });
  await ask('归档回答 A', 1);
  const archived = await snapshot();
  const current = await host('/reader/session', { sessionId: archived.sessionId });
  assert.notEqual(current.discussionId, archived.discussionId);
  assert.ok(current.discussions.some(item => item.discussionId === archived.discussionId));
  assert.deepEqual(current.conversation, []);
  await answer('归档回答 A').waitFor({ state: 'detached' });
  assert.equal(await source.getByRole('button', { name: /返回回答证据/ }).count(), 0);

  await readingTab.click();
  await page.locator('.focus-stream').waitFor();
  const window = await snapshot();
  if (!window.readingStarted) {
    const { sourceId, planId, chunkId } = window.navigationCurrent;
    await host('/reader/continue', { requestId: randomUUID(), beginBody: true,
      receipt: { sourceId, planId, chunkId, readingRevision: window.readingRevision } });
  }
  if (!(await readingProgress()).completed) {
    await page.getByRole('button', { name: '继续', exact: true }).click();
    await page.locator('[data-chunk-key$="/chunk-002"]').last().waitFor();
  }
  await chatTab.click();
  const before = await readingProgress();
  assert.ok(before.cursor && before.completed > 0, 'The fixture must have an active Reading Cursor and read chunks');

  await ask('当前回答 B', 4);
  const b = answer('当前回答 B');
  const b3 = citation(b, 3), b4 = citation(b, 4);
  await browseToStart();
  await b3.click();
  await assertLocated(b3, 'a scalable high-bandwidth system');
  assert.ok((await originalLink.getAttribute('href')).endsWith('#page=8'));
  assert.ok(await scrollTop() > 0);
  await numberedReturn(3).click();
  await atFocus(b3);
  const nextId = await b4.getAttribute('data-citation');
  assert.ok(await source.evaluate((pane, id) => {
    const bounds = pane.getBoundingClientRect();
    return [...pane.querySelectorAll(`[data-evidence-ids~="${id}"]`)].every(node => {
      const rect = node.getBoundingClientRect();
      return rect.top >= bounds.top && rect.bottom <= bounds.bottom;
    });
  }, nextId), 'The shorter citation is fully visible before activating it');
  const originalTop = await scrollTop();
  await b4.press('Enter');
  await assertLocated(b4, 'a scalable high-bandwidth');
  assert.equal(await scrollTop(), originalTop);
  await numberedReturn(4).click();
  await atFocus(b4);

  await page.getByRole('button', { name: '对话全屏', exact: true }).click();
  await page.getByRole('button', { name: '退出全屏', exact: true }).click();
  await numberedReturn(4).click();
  await atFocus(b4);
  await readingTab.click();
  await page.locator('.focus-stream').waitFor();
  await chatTab.click();
  await numberedReturn(4).click();
  await atFocus(b4);

  await ask('当前回答 C', 2);
  const c = answer('当前回答 C');
  await selectAnswer(c);
  await numberedReturn(1).click();
  await atFocus(citation(c, 1));
  await selectAnswer(b);
  const bReturn = referencedParagraph.getByRole('button', { name: /^返回回答证据 [34]$/ });
  const bNumber = (await bReturn.textContent()).trim();
  await bReturn.click();
  await atFocus(citation(b, bNumber));

  await citation(c, 2).click();
  await b4.click();
  await assertLocated(b4, 'a scalable high-bandwidth');
  assert.ok((await originalLink.getAttribute('href')).endsWith('#page=8'));
  await browseToStart();
  await b4.click();
  await assertLocated(b4, 'a scalable high-bandwidth');
  await page.reload();
  await chatTab.click();
  await originalLink.waitFor();
  assert.ok(await scrollTop() < 20, 'A manual bookmark survives a later citation jump and reopening');

  await chinese.click();
  await b4.click();
  const groupId = await b4.getAttribute('data-citation');
  const activeGroup = source.locator(`[data-translation-granularity="group"].is-active[data-evidence-block~="${groupId}"]`);
  await activeGroup.waitFor();
  assert.equal(await activeGroup.count(), 1);
  assert.ok(await activeGroup.locator('p').count() > 1);
  assert.ok(await activeGroup.evaluate(group => {
    const pane = group.closest('[aria-label="文章原文"]').getBoundingClientRect();
    const top = group.getBoundingClientRect().top;
    return top >= pane.top && top < pane.bottom && getComputedStyle(group).boxShadow !== 'none';
  }), 'the whole verified group is highlighted from its start');
  assert.equal(await chinese.getAttribute('aria-pressed'), 'true');
  assert.ok((await originalLink.getAttribute('href')).endsWith('#page=8'));
  await original.click();
  await assertLocated(b4, 'a scalable high-bandwidth');

  await page.setViewportSize({ width: 390, height: 844 });
  const narrowMode = page.getByRole('combobox', { name: '阅读方式' });
  if (await narrowMode.isVisible()) await narrowMode.selectOption('chat');
  const narrowCitation = citation(answer('当前回答 B'), 4);
  const narrowId = await narrowCitation.getAttribute('data-citation');
  await narrowCitation.press('Enter');
  await assertLocated(narrowId, 'a scalable high-bandwidth');
  await numberedReturn(4).click();
  await atFocus(narrowCitation);
  await page.getByRole('button', { name: '查看正文', exact: true }).click();
  await source.waitFor();
  await page.getByRole('button', { name: '返回对话', exact: true }).click();
  await conversation.waitFor();
  assert.deepEqual(await readingProgress(), before);
  assert.deepEqual(errors, []);
  console.log('PASS exact source jumps, historical translated group, selected answer return, manual bookmark, mobile navigation and unchanged Reading Cursor');
} catch (error) {
  console.error((await page.getByRole('alert').allTextContents()).join('\n'));
  console.error((await page.locator('body').innerText()).slice(-1500));
  throw error;
} finally {
  await browser.close();
}
