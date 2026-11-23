import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.FOCUS_BROWSER_URL;
assert.ok(base, 'Start tests/pdf_evidence_browser.py with tests/chunk_discussion_evidence_scenario.json and set FOCUS_BROWSER_URL.');
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 950 }, reducedMotion: 'reduce' });
page.setDefaultTimeout(12000);
const nav = page.getByRole('group', { name: '阅读方式', exact: true });
const closeReading = nav.getByRole('button', { name: '精读', exact: true });
const chat = nav.getByRole('button', { name: '对话', exact: true });
const stream = page.getByRole('main', { name: '阅读与对话', exact: true });
const conversation = page.getByLabel('文章对话', { exact: true });
const source = page.getByLabel('文章原文', { exact: true });
const evidenceCard = page.getByLabel('原文证据', { exact: true });
const chunk = number => stream.locator(`[data-chunk-key$="/chunk-00${number}"]`).last();
const capsule = (section, count) => section.getByRole('button', { name: `对话证据 · ${count} 条`, exact: true });
const answer = name => conversation.locator('[data-role="assistant"]').filter({ hasText: name });
const citation = (name, number) => answer(name).getByRole('button', { name: String(number), exact: true });
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
  const { progress } = sources.find(item => item.sourceId === view.source.sourceId);
  return {
    cursor: view.navigationCurrent?.chunkId,
    plan: view.navigationCurrent?.planId,
    readingRevision: view.readingRevision,
    completed: progress.completed,
  };
}

async function enterSecondChunk() {
  await closeReading.click();
  await page.waitForFunction(async instanceId => {
    const response = await fetch('/reader/window', { headers: { 'X-FOCUS-Instance': instanceId } });
    return (await response.json()).value?.navigationCurrent?.index === 1;
  }, instance, { polling: 250 });
  const view = await snapshot();
  if (!view.readingStarted) {
    const { sourceId, planId, chunkId } = view.navigationCurrent;
    await host('/reader/continue', { requestId: randomUUID(), beginBody: true,
      receipt: { sourceId, planId, chunkId, readingRevision: view.readingRevision } });
  }
  await chunk(1).waitFor();
  await page.getByRole('button', { name: '继续', exact: true }).click();
  await chunk(2).waitFor();
}

async function ask(name, count) {
  await chat.click();
  await page.getByRole('textbox', { name: '输入消息' }).fill(name);
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await answer(name).locator('button[data-citation]').nth(count - 1).waitFor({ state: 'attached' });
  const window = await snapshot();
  const message = window.conversation.find(item => item.role === 'assistant' && item.content.startsWith(name));
  assert.equal(message?.evidence?.length, count);
  return { window, message };
}

async function openCapsule(count) {
  await closeReading.click();
  const disclosure = capsule(chunk(2), count);
  await disclosure.waitFor();
  if (await disclosure.getAttribute('aria-expanded') === 'false') await disclosure.click();
  const list = chunk(2).getByRole('list').filter({ has: page.getByRole('button', { name: /^证据 / }) });
  assert.equal(await list.getByRole('listitem').count(), count);
  return list;
}

async function followEvidence(list, name, number, quote) {
  await list.getByRole('button', { name: `证据 ${number} ${quote}`, exact: true }).click();
  const target = citation(name, number);
  await target.waitFor({ state: 'visible' });
  await page.waitForFunction(() => document.activeElement?.getAttribute('data-answer-target') === 'true');
  assert.equal(await target.evaluate(node => document.activeElement === node), true);
  assert.equal(await chat.getAttribute('aria-pressed'), 'true');
  assert.equal(await evidenceCard.count(), 0);
  await target.click();
  await evidenceCard.getByText(quote, { exact: true }).waitFor();
  await source.locator('[data-pdf-page="4"] [data-active="true"]').first().waitFor();
}

try {
  await page.goto(new URL('/reading', base).href);
  await enterSecondChunk();
  const b = '精读证据四条引文';
  const newAnswer = '新讨论单条引文';
  const quote3 = 'using the same emulated memory pool. The application is also executed';
  const quote4 = 'scheduling constraints required to maintain performance';
  const { window: original, message } = await ask(b, 4);
  const [one, two, three, four] = message.evidence;
  assert.deepEqual(message.evidence.map(item => item.displayNumber), [1, 2, 3, 4]);
  assert.deepEqual(three.blockIds.map(id => id.split(':').at(-1)).sort(), ['3-10', '3-13']);
  assert.deepEqual(four.blockIds, three.blockIds.filter(id => id.endsWith('3-13')));
  assert.ok(original.navigationCurrent.blockIds.includes(three.blockIds[0]));
  assert.ok(original.navigationCurrent.blockIds.includes(three.blockIds[1]));
  for (const outside of [one, two]) {
    assert.ok(outside.blockIds.length);
    assert.ok(outside.blockIds.every(id => !original.navigationCurrent.blockIds.includes(id)));
  }
  const before = await readingProgress();
  assert.equal(before.cursor, 'chunk-002');
  assert.equal(before.completed, 1);
  await followEvidence(await openCapsule(2), b, 3, quote3);
  await followEvidence(await openCapsule(2), b, 4, quote4);
  assert.deepEqual(await readingProgress(), before);

  await page.getByRole('button', { name: '重新阅读', exact: true }).click();
  const [reset] = await Promise.all([
    page.waitForResponse(response => response.url().endsWith('/reset-reading')),
    page.getByRole('button', { name: '确认重新阅读', exact: true }).click(),
  ]);
  assert.equal((await reset.json()).ok, true);
  await answer(b).waitFor({ state: 'detached' });
  await enterSecondChunk();
  const fresh = await snapshot();
  assert.notEqual(fresh.discussionId, original.discussionId);
  assert.ok(fresh.discussions.some(item => item.discussionId === original.discussionId));
  assert.deepEqual(fresh.conversation, []);
  assert.equal(await stream.getByRole('button', { name: /^对话证据/ }).count(), 0);

  await ask(newAnswer, 1);
  const afterReset = await readingProgress();
  assert.equal(afterReset.cursor, 'chunk-002');
  assert.equal(afterReset.completed, 1);
  await followEvidence(await openCapsule(1), newAnswer, 1, quote4);
  assert.deepEqual(await readingProgress(), afterReset);

  const otherAnswer = '同编号另一回答';
  await ask(otherAnswer, 1);
  const bothAnswers = await openCapsule(2);
  await bothAnswers.getByRole('button', { name: `证据 1 ${quote4}`, exact: true }).waitFor();
  await followEvidence(bothAnswers, otherAnswer, 1, quote3);
  assert.deepEqual(await readingProgress(), afterReset);

  const discussionHistory = page.getByRole('combobox', { name: '对话记录', exact: true });
  await discussionHistory.selectOption(original.discussionId);
  await citation(b, 4).waitFor();
  const archive = await snapshot();
  assert.deepEqual(archive.conversation.find(item => item.messageId === message.messageId), message);
  await discussionHistory.selectOption(fresh.discussionId);
  await answer(otherAnswer).waitFor({ state: 'visible' });
  assert.deepEqual(await readingProgress(), afterReset);
  assert.deepEqual(errors, []);
  console.log('PASS chunk evidence counts and numbered navigation in the current discussion, old answers archived, and unchanged reading progress');
} catch (error) {
  console.error((await page.locator('body').innerText()).slice(-1500));
  throw error;
} finally {
  await browser.close();
}
