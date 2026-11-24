import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const base = `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}`;
const page = await browser.newPage({ viewport: { width: 1440, height: 844 }, reducedMotion: 'reduce' });
page.setDefaultTimeout(8000);
page.on('pageerror', error => console.error(error));
const modes = page.getByRole('group', { name: '阅读方式' });
const body = page.getByLabel('文章原文', { exact: true });
const chinese = page.getByRole('button', { name: '中文', exact: true });
const original = page.getByRole('button', { name: '原文', exact: true });
const conversation = modes.getByRole('button', { name: '对话', exact: true });

async function workspaceHeaders() {
  const binding = await (await page.request.get(`${base}/reader/workspace`)).json();
  return { 'X-FOCUS-Instance': binding.value.workspace.instanceId };
}

async function readingProgress() {
  const snapshot = await (await page.request.get(`${base}/reader/window`, { headers: await workspaceHeaders() })).json();
  assert.ok(snapshot.ok, JSON.stringify(snapshot));
  const { navigationCurrent, readingProgress, readingRevision } = snapshot.value;
  return { chunk: navigationCurrent.chunkId, read: readingProgress.length, readingRevision };
}

async function readAt(text) {
  const passage = body.getByText(text, { exact: true });
  await passage.scrollIntoViewIfNeeded();
  const move = await passage.evaluate(node => {
    const pane = node.closest('[aria-label="文章原文"]');
    const view = pane.getBoundingClientRect();
    const paragraph = node.getBoundingClientRect();
    const y = view.top + pane.clientHeight * .32;
    return { x: paragraph.left + paragraph.width / 2, y, delta: paragraph.top + paragraph.height / 2 - y };
  });
  await page.mouse.move(move.x, move.y);
  await page.mouse.wheel(0, move.delta);
  await atReadingLine(text);
}

async function atReadingLine(text) {
  try { await page.waitForFunction(value => {
    const pane = document.querySelector('[aria-label="文章原文"]');
    const line = pane.getBoundingClientRect().top + pane.clientHeight * .32;
    return [...pane.querySelectorAll('p')].some(node => node.textContent === value &&
      node.getBoundingClientRect().top <= line && node.getBoundingClientRect().bottom > line);
  }, text); } catch (error) {
    console.error(await body.evaluate((pane, value) => {
      const view = pane.getBoundingClientRect();
      const line = view.top + pane.clientHeight * .32;
      const paragraphs = [...pane.querySelectorAll('p')];
      return { line, scroll: pane.scrollTop,
        actual: paragraphs.find(node => node.getBoundingClientRect().bottom > line)?.textContent,
        expected: paragraphs.find(node => node.textContent === value)?.getBoundingClientRect().toJSON() };
    }, text));
    throw error;
  }
}

async function inBodyViewport(locator) {
  await locator.waitFor();
  assert.ok(await locator.evaluate(node => {
    const bounds = node.getBoundingClientRect();
    const viewport = node.closest('[aria-label="文章原文"]').getBoundingClientRect();
    return bounds.top >= viewport.top && bounds.bottom <= viewport.bottom;
  }));
}

try {
  await page.goto(`${base}/reading`);
  await conversation.waitFor();
  if (await conversation.getAttribute('aria-pressed') !== 'true') await conversation.click();
  await body.getByRole('heading', { name: '双语位置', exact: true }).waitFor();
  assert.equal(await chinese.count(), 1);
  assert.equal(await original.count(), 1);
  assert.equal(await chinese.getAttribute('aria-pressed'), 'true');

  const before = await readingProgress();
  assert.equal(before.chunk, 'chunk-002');
  assert.equal(before.read, 1);
  const directoryToggle = page.getByRole('button', { name: '目录', exact: true });
  await directoryToggle.waitFor();
  assert.equal(await directoryToggle.getAttribute('aria-expanded'), 'true');
  const directory = page.getByRole('navigation', { name: '目录', exact: true });
  await directory.getByRole('button', { name: '1. 引言', exact: true }).waitFor();
  const methods = directory.getByRole('button', { name: '2 方法', exact: true });
  const dataSources = directory.getByRole('button', { name: '2.1 数据来源', exact: true });
  const branch = directory.getByRole('button', { name: '2 方法的子章节', exact: true });
  const currentSection = directory.locator('[aria-current="location"]');
  await readAt('阅读段落 17 用来核对阅读位置。');
  await dataSources.and(currentSection).waitFor();
  const beforeCollapse = await body.evaluate(pane => pane.scrollTop);
  await branch.press('Space');
  await dataSources.waitFor({ state: 'hidden' });
  await methods.and(currentSection).waitFor();
  assert.equal(await body.evaluate(pane => pane.scrollTop), beforeCollapse);
  await directoryToggle.press('Enter');
  await directory.waitFor({ state: 'hidden' });
  await atReadingLine('阅读段落 17 用来核对阅读位置。');
  await directoryToggle.press('Space');
  await methods.and(currentSection).waitFor();
  await atReadingLine('阅读段落 17 用来核对阅读位置。');
  await original.press('Enter');
  await atReadingLine('Reading passage 17 with context to read.');
  await directory.getByRole('button', { name: '2 Methods', exact: true }).and(currentSection).waitFor();
  assert.equal(await directory.getByRole('button', { name: '2 Methods的子章节', exact: true }).getAttribute('aria-expanded'), 'false');
  await readAt('Reading passage 23 with context to read.');
  await chinese.click();
  await atReadingLine('阅读段落 23 用来核对阅读位置。');
  await original.click();
  await atReadingLine('Reading passage 23 with context to read.');
  assert.deepEqual(await readingProgress(), before);

  await page.reload();
  await body.getByRole('heading', { name: 'Bilingual Position', exact: true }).waitFor();
  assert.equal(await original.getAttribute('aria-pressed'), 'true');
  await atReadingLine('Reading passage 23 with context to read.');
  assert.deepEqual(await readingProgress(), before);

  await chinese.click();
  const sharedText = '阅读段落 16 用来核对阅读位置。';
  await body.getByText(sharedText, { exact: true }).waitFor();
  await modes.getByRole('button', { name: '精读', exact: true }).click();
  await page.getByRole('main', { name: '阅读与对话', exact: true }).getByText(sharedText, { exact: true }).waitFor();
  assert.deepEqual(await readingProgress(), before);

  await conversation.click();
  const chat = page.getByLabel('文章对话', { exact: true });
  const message = page.getByRole('textbox', { name: '输入消息' });
  await message.fill('核对双语证据');
  await message.press('Enter');
  const citation = chat.getByRole('button', { name: '1', exact: true });
  await branch.press('Enter');
  await readAt('阅读段落 25 用来核对阅读位置。');
  const appendix = directory.getByRole('button', { name: '3 Appendix', exact: true });
  await appendix.and(currentSection).waitFor();
  await citation.press('Enter');
  const translationEvidence = body.locator('[data-evidence-block].is-active');
  await inBodyViewport(translationEvidence.getByText('阅读段落 17 用来核对阅读位置。', { exact: true }));
  await methods.and(currentSection).waitFor();
  assert.equal(await branch.getAttribute('aria-expanded'), 'false');
  assert.equal(await chinese.getAttribute('aria-pressed'), 'true');
  const evidenceId = await citation.getAttribute('data-citation');
  assert.equal(await translationEvidence.getAttribute('data-evidence-block'), evidenceId);
  await original.click();
  const exactQuote = body.locator('mark.is-active').getByText('Reading passage 17', { exact: true });
  await inBodyViewport(exactQuote);
  assert.equal(await exactQuote.getAttribute('data-evidence-ids'), evidenceId);
  await chinese.click();
  await inBodyViewport(translationEvidence.getByText('阅读段落 17 用来核对阅读位置。', { exact: true }));
  await body.getByRole('button', { name: '返回回答证据 1' }).click();
  assert.ok(await citation.evaluate(node => document.activeElement === node));
  await readAt('阅读段落 25 用来核对阅读位置。');
  await original.click();
  await atReadingLine('Reading passage 25 with context to read.');
  assert.deepEqual(await readingProgress(), before);

  await chinese.click();
  await inBodyViewport(body.getByText('附录概述。', { exact: true }));
  await appendix.press('Enter');
  const appendixHeading = body.getByRole('heading', { name: 'Appendix', exact: true });
  await inBodyViewport(appendixHeading);
  assert.ok(await appendixHeading.evaluate(node => document.activeElement === node));
  await appendix.and(currentSection).waitFor();
  assert.equal(await chinese.getAttribute('aria-pressed'), 'true');
  await page.waitForFunction(async headers => {
    const response = await fetch('/library/sources/fixture-paper/reading-bookmark', { headers });
    const result = await response.json();
    return result.ok && result.value?.line === 57;
  }, await workspaceHeaders());
  assert.deepEqual(await readingProgress(), before);

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  await mobile.goto(`${base}/reading`);
  await mobile.getByRole('group', { name: '阅读方式' }).getByRole('button', { name: '对话', exact: true }).click();
  await mobile.getByRole('button', { name: '查看正文', exact: true }).click();
  const mobileDirectoryToggle = mobile.getByRole('button', { name: '目录', exact: true });
  assert.equal(await mobileDirectoryToggle.getAttribute('aria-expanded'), 'false');
  await mobileDirectoryToggle.press('Enter');
  const mobileDirectory = mobile.getByRole('navigation', { name: '目录', exact: true });
  await mobileDirectory.getByRole('button', { name: '2.1 数据来源', exact: true }).click();
  await mobileDirectory.waitFor({ state: 'hidden' });
  await inBodyViewport(mobile.getByLabel('文章原文', { exact: true }).getByRole('heading', { name: '数据来源', exact: true }));
  assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth), 390);
  await mobile.getByRole('button', { name: '返回对话', exact: true }).click();
  await mobile.getByRole('button', { name: '文章导读', exact: false }).waitFor();
  await mobile.close();

  await page.getByRole('link', { name: '知识库', exact: true }).click();
  const chineseSource = page.getByRole('listitem').filter({ has: page.getByRole('button', { name: '中文原文示例', exact: true }) });
  await chineseSource.getByRole('button', { name: '阅读', exact: true }).click();
  await conversation.click();
  await body.getByRole('heading', { name: '中文原文示例', exact: true }).waitFor();
  assert.equal(await page.getByRole('group', { name: '正文语言', exact: true }).count(), 0);
  await directory.getByRole('button', { name: '1 原文小节 1', exact: true }).waitFor();

  await page.getByRole('link', { name: '知识库', exact: true }).click();
  const unheadedSource = page.getByRole('listitem').filter({ has: page.getByRole('button', { name: '无标题正文', exact: true }) });
  await unheadedSource.getByRole('button', { name: '阅读', exact: true }).click();
  await conversation.click();
  await body.getByText('中文原文第 1 段。', { exact: true }).waitFor();
  assert.equal(await directoryToggle.count(), 0);

  console.log('PASS bilingual position and evidence, canonical and legacy section directories, section bookmarks, desktop and mobile layout, and stable reading progress');
} catch (error) {
  console.error((await page.locator('body').innerText()).slice(0, 1800));
  throw error;
} finally {
  await browser.close();
}
