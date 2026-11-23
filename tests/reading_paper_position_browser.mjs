import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const base = `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}`;
const browser = await chromium.launch({ headless: true,
  executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE, args: ['--no-sandbox'] });

async function openPaper(configure) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 950 }, reducedMotion: 'reduce' });
  page.setDefaultTimeout(12000);
  const pane = page.getByLabel('文章原文', { exact: true });
  const pdf = page.getByRole('button', { name: '原版 PDF', exact: true });
  const translation = page.getByRole('button', { name: '中文译文', exact: true });
  await configure?.(page);
  await page.goto(`${base}/reading`);
  const modes = page.getByRole('group', { name: '阅读方式' });
  await modes.getByRole('button', { name: '对话', exact: true }).click();
  await translation.waitFor();
  return { page, pane, pdf, translation };
}

async function readingProgress(page) {
  const binding = await (await page.request.get(`${base}/reader/workspace`)).json();
  const headers = { 'X-FOCUS-Instance': binding.value.workspace.instanceId };
  const snapshot = await (await page.request.get(`${base}/reader/window`, { headers })).json();
  assert.ok(snapshot.ok, JSON.stringify(snapshot));
  const { navigationCurrent, readingProgress, readingRevision } = snapshot.value;
  return { source: navigationCurrent.sourceId, plan: navigationCurrent.planId, chunk: navigationCurrent.chunkId,
    read: readingProgress.length, readingRevision };
}

async function placeAtReadingLine(page, pane, node, y = .5) {
  await node.waitFor();
  const point = await node.evaluate((el, fraction) => {
    const pane = el.closest('[aria-label="文章原文"]');
    const viewport = pane.getBoundingClientRect();
    const node = el.getBoundingClientRect();
    const readingLine = viewport.top + pane.clientHeight * .32;
    return { x: node.left + node.width * .4, y: readingLine,
      distance: Math.round(node.top + node.height * fraction - readingLine), start: pane.scrollTop };
  }, y);
  await page.mouse.move(point.x, point.y);
  await page.mouse.wheel(0, point.distance);
  await page.waitForFunction(({ start, distance }) => Math.abs(
    document.querySelector('[aria-label="文章原文"]').scrollTop - start - distance) <= 2, point);
  return pane.evaluate(el => el.scrollTop);
}

async function waitAtReadingLine(page, text) {
  await page.waitForFunction(value => {
    const pane = document.querySelector('[aria-label="文章原文"]');
    const line = pane.getBoundingClientRect().top + pane.clientHeight * .32;
    return [...pane.querySelectorAll('[data-translation-chunk]')].some(node => node.textContent.startsWith(value) &&
      node.getBoundingClientRect().top <= line && node.getBoundingClientRect().bottom >= line);
  }, text);
}

async function waitAtPosition(page, expected) {
  await page.waitForFunction(top => Math.abs(document.querySelector('[aria-label="文章原文"]').scrollTop - top) <= 2, expected);
}

async function delayNextPdf(page) {
  const requested = Promise.withResolvers();
  const release = Promise.withResolvers();
  await page.route('**/library/sources/*/original?*', async route => {
    requested.resolve();
    await release.promise;
    await route.continue();
  }, { times: 1 });
  return { requested: requested.promise, release: release.resolve };
}

try {
  const { page, pane, pdf, translation } = await openPaper();
  const before = await readingProgress(page);
  assert.equal(before.chunk, 'chunk-002');
  assert.equal(before.read, 1);
  const tablePage = pane.locator('[data-pdf-page="2"]');
  await placeAtReadingLine(page, pane, tablePage, .38);
  await pane.getByLabel('原版 PDF 第 2 页').waitFor();
  const continuation = tablePage.locator('[data-source-line="4"]');
  await continuation.waitFor();
  assert.ok(await continuation.evaluate(node => {
    const bounds = node.getBoundingClientRect();
    const view = node.closest('[aria-label="文章原文"]').getBoundingClientRect();
    return bounds.top < view.bottom && bounds.bottom > view.top;
  }), 'a different mapped paragraph is visible on the same page as the unmapped table');
  await translation.press('Enter');
  await pane.getByText('实验方法，第 1 段。', { exact: true }).waitFor();
  assert.equal(await pane.evaluate(el => el.scrollTop), 0,
    'a table without a mapped block opens an unvisited translation at its start');
  console.log('PASS first manual switch from an unmapped PDF table starts the translation at its beginning');

  const methodText = pane.getByText('实验方法，第 10 段。', { exact: true });
  const methodScroll = await placeAtReadingLine(page, pane, methodText);
  await pdf.press('Enter');
  const methodBox = pane.locator('[data-pdf-page="1"] [data-source-line="4"]');
  await methodBox.waitFor();
  await page.waitForFunction(() => {
    const pane = document.querySelector('[aria-label="文章原文"]');
    const block = pane.querySelector('[data-pdf-page="1"] [data-source-line="4"]');
    const line = pane.getBoundingClientRect().top + pane.clientHeight * .32;
    return block.getBoundingClientRect().top <= line && block.getBoundingClientRect().bottom >= line;
  });

  const tableScroll = await placeAtReadingLine(page, pane, tablePage, .38);
  await translation.press('Enter');
  await methodText.waitFor();
  await waitAtPosition(page, methodScroll);
  await waitAtReadingLine(page, '实验方法');

  const unmappedText = pane.getByText('实现细节，第 10 段。', { exact: true });
  await placeAtReadingLine(page, pane, unmappedText);
  await pdf.press('Enter');
  await tablePage.waitFor();
  await waitAtPosition(page, tableScroll);
  await placeAtReadingLine(page, pane, methodBox);
  await translation.press('Enter');
  await methodText.waitFor();
  await waitAtReadingLine(page, '实验方法');
  assert.deepEqual(await readingProgress(page), before);

  await pdf.press('Enter');
  const continuedPosition = await placeAtReadingLine(page, pane, continuation);
  assert.equal(await continuation.getAttribute('data-block-id'), await methodBox.getAttribute('data-block-id'));
  await translation.press('Enter');
  await waitAtReadingLine(page, '实验方法');
  await pdf.press('Enter');
  await continuation.waitFor();
  await waitAtPosition(page, continuedPosition);
  await translation.press('Enter');
  await methodText.waitFor();
  console.log('PASS a block placed on two PDF pages returns to the specific page it was read from');

  await placeAtReadingLine(page, pane, unmappedText);
  const loading = await delayNextPdf(page);
  try {
    await pdf.press('Enter');
    await pane.getByText('加载原版 PDF…').waitFor();
    await loading.requested;
    await translation.press('Enter');
  } finally {
    loading.release();
  }
  await unmappedText.waitFor();
  await pdf.press('Enter');
  await methodBox.waitFor();
  await waitAtPosition(page, continuedPosition);
  assert.deepEqual(await readingProgress(page), before);
  await page.close();
  console.log('PASS mapped content takes priority and unmapped content restores both views’ previous positions');

  let firstPdf;
  const fresh = await openPaper(async page => { firstPdf = await delayNextPdf(page); });
  try {
    await firstPdf.requested;
    await fresh.translation.press('Enter');
    await placeAtReadingLine(fresh.page, fresh.pane, fresh.pane.getByText('实现细节，第 10 段。', { exact: true }));
    await fresh.pdf.press('Enter');
  } finally {
    firstPdf.release();
  }
  await fresh.pane.getByLabel('原版 PDF 第 1 页').waitFor();
  assert.equal(await fresh.pane.evaluate(el => el.scrollTop), 0,
    'an unmapped translation opens a PDF that has yet to render at the beginning');
  assert.deepEqual(await readingProgress(fresh.page), before);
  console.log('PASS first manual switch from an unmapped translation starts the PDF at its beginning; Reading Cursor and progress unchanged');
} finally {
  await browser.close();
}
