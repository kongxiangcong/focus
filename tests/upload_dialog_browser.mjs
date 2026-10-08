import assert from 'node:assert/strict';
import fs from 'node:fs';
const { chromium } = await import(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const output = process.env.FOCUS_BROWSER_OUTPUT || '.scratch/upload-dialog-controls';
fs.mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE });
const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
page.setDefaultTimeout(10000);
const errors = [], staged = [], batches = [];
page.on('pageerror', error => errors.push(error.message));
const empty = { status: 'empty', current: null, history: [], conversation: [], source: { sourceId: '', title: '', topicId: null }, sessionId: 'upload-test' };
const topics = [{ topicId: 'architecture', title: '架构探索', sourceIds: [] }, { topicId: 'compiler', title: '编译', sourceIds: [] }];
// Isolated HTTP responses: verify UI and request scope without parsing or generating real content.
await page.route(/\/(reader|library)\//, async route => {
  const request = route.request(), url = new URL(request.url());
  const json = value => route.fulfill({ json: { ok: true, value } });
  if (url.pathname === '/reader/workspace') return json({ bound: true });
  if (url.pathname === '/reader/events') return route.fulfill({ contentType: 'text/event-stream', body: `event: snapshot\ndata: ${JSON.stringify({ ok: true, value: empty })}\n\n` });
  if (url.pathname.startsWith('/reader/')) return json(empty);
  if (url.pathname === '/library/topics') return json(topics);
  if (request.method() === 'POST' && url.pathname === '/library/inbox') {
    staged.push(url.searchParams.get('topic'));
    return json({ item_id: `item-${staged.length}`, file_name: url.searchParams.get('name'), status: 'awaiting_confirmation', topic_title: staged.at(-1), topic_id: null, source_id: null, document_status: 'not_started', topic_status: 'not_started' });
  }
  if (request.method() === 'POST' && url.pathname === '/library/batches') {
    batches.push(request.postDataJSON());
    return json({ batchId: `batch-${batches.length}`, topicId: null, status: 'confirmed', items: [] });
  }
  return json([]);
});
try {
  await page.goto(`${process.env.FOCUS_TEST_URL || 'http://127.0.0.1:5178'}/library`);
  // Refresh after the development StrictMode mount/cleanup cycle.
  await page.getByRole('link', { name: '设置', exact: true }).click();
  await page.getByRole('link', { name: '知识库', exact: true }).click();
  await page.getByRole('button', { name: /^架构探索/ }).waitFor();
  await page.getByRole('button', { name: '上传', exact: true }).first().click();
  const dialog = page.locator('.workspace-upload'), topic = dialog.getByRole('combobox', { name: '专题', exact: true });
  const checkbox = dialog.getByRole('checkbox', { name: '仅解析入库', exact: true });
  assert.equal(await checkbox.isChecked(), false);
  assert.equal(await dialog.locator('small, p').count(), 0);
  const box = await checkbox.boundingBox(), label = await dialog.locator('.upload-parse-only').boundingBox();
  assert.equal(box.width, 16);
  assert.ok(Math.abs(box.y + box.height / 2 - label.y - label.height / 2) < 1);
  await dialog.getByRole('button', { name: '展开已有专题' }).click();
  assert.equal(await dialog.getByRole('option').count(), 3);
  await page.screenshot({ path: `${output}/upload-desktop-options.png` });
  await dialog.getByRole('option', { name: '架构探索', exact: true }).click();
  assert.equal(await topic.inputValue(), '架构探索');
  await checkbox.check();
  await dialog.getByLabel('上传材料').setInputFiles({ name: 'parse-only.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF test') });
  await page.screenshot({ path: `${output}/upload-desktop.png` });
  await dialog.getByRole('button', { name: '仅解析入库', exact: true }).click();
  await dialog.waitFor({ state: 'hidden' });
  assert.equal(staged.at(-1), '架构探索');
  assert.equal(batches.at(-1).generateBlog, false);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '上传', exact: true }).first().click();
  assert.equal(await checkbox.isChecked(), false);
  await dialog.getByRole('button', { name: '展开已有专题' }).click();
  await topic.press('ArrowDown'); await topic.press('ArrowDown'); await topic.press('ArrowDown'); await topic.press('Enter');
  assert.equal(await topic.inputValue(), '编译');
  await topic.fill('新专题');
  await topic.press('Escape');
  assert.equal(await dialog.isVisible(), true);
  await dialog.getByRole('button', { name: '展开已有专题' }).click();
  assert.equal(await dialog.getByRole('option').count(), 3);
  await dialog.getByRole('option', { name: '不关联专题' }).click();
  const narrow = await dialog.boundingBox();
  assert.ok(narrow.x >= 0 && narrow.x + narrow.width <= 390);
  assert.equal(await dialog.evaluate(el => el.scrollWidth > el.clientWidth), false);
  await dialog.getByLabel('上传材料').setInputFiles({ name: 'with-blog.html', mimeType: 'text/html', buffer: Buffer.from('<html>test</html>') });
  await page.screenshot({ path: `${output}/upload-mobile.png` });
  await dialog.getByRole('button', { name: '开始解析并生成博客', exact: true }).click();
  await dialog.waitFor({ state: 'hidden' });
  assert.equal(staged.at(-1), null);
  assert.equal(batches.at(-1).generateBlog, true);
  assert.deepEqual(errors, []);
  console.log('PASS: desktop/mobile layout; inline checkbox; existing/new/empty topics; keyboard/Escape; parse-only/default-blog HTTP scope; no page errors');
} catch (error) {
  console.log(await page.locator('body').innerText());
  console.log(errors);
  throw error;
} finally { await browser.close(); }
