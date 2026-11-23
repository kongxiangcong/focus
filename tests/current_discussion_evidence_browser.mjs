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
page.setDefaultTimeout(12000);
const navigation = page.getByRole('group', { name: '阅读方式', exact: true });
const conversation = page.getByLabel('文章对话', { exact: true });
const source = page.getByLabel('文章原文', { exact: true });
const pdf = page.getByRole('button', { name: '原版 PDF', exact: true });
const translation = page.getByRole('button', { name: '中文译文', exact: true });
const chatTab = navigation.getByRole('button', { name: '对话', exact: true });
const readingTab = navigation.getByRole('button', { name: '精读', exact: true });
const sourceMarker = page.getByRole('button', { name: /返回相关回答|查看 \d+ 条相关回答/ });
const pdfBlock = source.locator('[data-pdf-page="8"] .paper-region').filter({ has: sourceMarker }).first();
const translatedBlock = source.locator('[data-translation-chunk]').filter({ has: sourceMarker }).last();
const evidenceCard = page.getByLabel('原文证据', { exact: true });
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
  await send.click();
  const result = answer(name);
  await result.waitFor();
  await page.waitForFunction(({ name, count }) => Array.from(document.querySelectorAll('[data-role="assistant"]'))
    .some(message => message.textContent.includes(name) && message.querySelectorAll('button[data-citation]').length === count),
  { name, count: expectedCitations });
}

async function atFocus(locator) {
  assert.equal(await locator.evaluate(node => node === document.activeElement), true);
}

try {
  await page.goto(new URL('/reading', base).href);
  await chatTab.click();
  await source.locator('[data-pdf-page="8"]').waitFor();
  await ask('归档回答 A', 1);
  const archived = await snapshot();
  const current = await host('/reader/session', { sessionId: archived.sessionId });
  assert.notEqual(current.discussionId, archived.discussionId);
  assert.ok(current.discussions.some(item => item.discussionId === archived.discussionId));
  assert.deepEqual(current.conversation, []);
  await answer('归档回答 A').waitFor({ state: 'detached' });
  assert.equal(await source.locator('.source-evidence-markers').count(), 0);
  await translation.click();
  await source.locator('[data-translation-chunk]').first().waitFor();
  assert.equal(await source.locator('.source-evidence-markers').count(), 0);
  await pdf.click();

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
  for (const [view, block] of [[pdf, pdfBlock], [translation, translatedBlock]]) {
    await view.click();
    await block.getByRole('button', { name: '返回相关回答', exact: true }).click();
    await atFocus(b);
    for (const number of ['3', '4']) await b.getByRole('button', { name: number, exact: true }).waitFor();
  }

  const citation = (message, number) => message.getByRole('button', { name: number, exact: true });
  const numberedReturn = (block, number) => block.getByRole('button', { name: `返回回答证据 ${number}`, exact: true });
  const b4 = citation(b, '4');
  const returnToB4 = async block => {
    await numberedReturn(block, '4').click();
    await atFocus(b4);
  };
  await pdf.click();
  const b3 = citation(b, '3');
  await b3.click();
  await evidenceCard.getByText('a scalable high-bandwidth system', { exact: true }).waitFor();
  await numberedReturn(pdfBlock, '3').click();
  await atFocus(b3);
  await b4.click();
  await evidenceCard.getByText('a scalable high-bandwidth', { exact: true }).waitFor();
  await source.press('Home');
  await page.waitForFunction(() => document.querySelector('[aria-label="文章原文"]').scrollTop < 20);
  await returnToB4(pdfBlock);

  await translation.click();
  await returnToB4(translatedBlock);
  await page.getByRole('button', { name: '对话全屏', exact: true }).click();
  await page.getByRole('button', { name: '退出全屏', exact: true }).click();
  await returnToB4(translatedBlock);

  await readingTab.click();
  await page.locator('.focus-stream').waitFor();
  await chatTab.click();
  await returnToB4(translatedBlock);

  await ask('当前回答 C', 2);
  const c = answer('当前回答 C');
  const chooser = page.getByRole('dialog', { name: '选择回答' });
  for (const [view, block, selected] of [[pdf, pdfBlock, b], [translation, translatedBlock, c]]) {
    await view.click();
    await block.getByRole('button', { name: '查看 2 条相关回答', exact: true }).click();
    const choiceB = chooser.getByRole('button', { name: /当前回答 B/ });
    const choiceC = chooser.getByRole('button', { name: /当前回答 C/ });
    assert.equal(await chooser.getByRole('listitem').count(), 2);
    assert.equal(await choiceB.count(), 1);
    assert.equal(await choiceC.count(), 1);
    await (selected === b ? choiceB : choiceC).click();
    await atFocus(selected);
  }

  // Keep the PDF request pending until a real reading key cancels the new jump.
  const originalPdf = /\/library\/sources\/[^/]+\/original\?pdfHash=/;
  let releaseRequest;
  const released = new Promise(resolve => { releaseRequest = resolve; });
  const delay = async route => {
    await released;
    await route.continue().catch(() => {}); // A discarded PDF worker may close its request while waiting.
  };
  await page.route(originalPdf, delay);
  try {
    await Promise.all([page.waitForRequest(originalPdf), pdf.click()]);
    await citation(c, '2').click();
    await source.press('Home');
  } finally {
    releaseRequest();
  }
  await source.locator('[data-pdf-page="1"] .paper-text span').first().waitFor({ state: 'attached' });
  await page.unrouteAll({ behavior: 'wait' });
  await evidenceCard.waitFor({ state: 'hidden' });
  await returnToB4(pdfBlock);

  await translation.click();
  const translationBefore = await source.evaluate(pane => pane.scrollTop);
  await citation(b, '2').click();
  await evidenceCard.getByRole('button', { name: /译块位置暂不可用/ }).waitFor();
  assert.equal(await source.evaluate(pane => pane.scrollTop), translationBefore);
  await returnToB4(translatedBlock);

  const c1 = citation(c, '1');
  await c1.click();
  await evidenceCard.getByText('high-bandwidth system', { exact: true }).waitFor();
  assert.equal(await numberedReturn(translatedBlock, '4').count(), 0);
  await numberedReturn(translatedBlock, '1').click();
  await atFocus(c1);

  assert.deepEqual(await readingProgress(), before);
  assert.deepEqual(errors, []);
  console.log('PASS current discussion markers, durable exact return, and unchanged Reading Cursor and read count');
} catch (error) {
  console.error((await page.locator('body').innerText()).slice(-1500));
  throw error;
} finally {
  await browser.close();
}
