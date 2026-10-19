import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const baseUrl = `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT || '8765'}`;
const output = process.env.FOCUS_BROWSER_OUTPUT || '/tmp';
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE || undefined,
  channel: process.env.FOCUS_CHROMIUM_EXECUTABLE ? undefined : (process.env.FOCUS_BROWSER_CHANNEL || undefined),
  args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--no-zygote'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
page.setDefaultTimeout(10000);
const errors = [], posts = [], results = [];
page.on('pageerror', e => errors.push(e.message));
page.on('request', r => { if (r.method() === 'POST') posts.push(r.url()); });
const api = async () => (await (await page.request.get(`${baseUrl}/reader/window`)).json()).value;
const reader = page.locator('.focus-reader'), stream = page.locator('.focus-stream');
const drawer = page.locator('.reader-left-drawer'), gallery = page.locator('.reader-figure-scroll');
const materials = page.getByRole('complementary', { name: '阅读资料' });
const chunk = async i => page.waitForFunction(n => document.querySelector('.focus-output[data-current-output="true"]')?.textContent.includes(`Section ${n}`), i);
const next = async i => { await page.getByRole('button', { name: '继续', exact: true }).click(); await chunk(i); };
const top = () => stream.evaluate(el => el.scrollTop);
const stable = async before => { await page.waitForTimeout(120); assert.ok(Math.abs(await top() - before) < 2, `text scroll moved: ${before} -> ${await top()}`); };
const tab = name => drawer.getByRole('button', { name, exact: true });
try {
  await page.goto(`${baseUrl}/reading`);
  await page.waitForSelector('.workspace-app'); await page.waitForTimeout(400);
  { const enter = page.getByRole('button', { name: '进入正文', exact: true }); if (await enter.count()) await enter.click(); }
  await chunk(1);
  await page.waitForFunction(() => document.querySelector('.reader-figure-scroll img')?.naturalWidth > 0);
  // A chunk with figures opens the left drawer directly on the image tab.
  assert.ok(await drawer.isVisible());
  assert.equal(await gallery.locator('figure').count(), 5);
  assert.equal(await stream.locator('img').count(), 0);
  assert.equal(await tab('图片').getAttribute('aria-pressed'), 'true');

  // The drawer is an overlay: it never reflows the reading column.
  const openWidth = (await stream.boundingBox()).width;
  await page.getByRole('button', { name: '关闭阅读侧栏', exact: true }).click();
  await page.waitForTimeout(250);
  assert.equal(await drawer.isVisible(), false);
  const closedWidth = (await stream.boundingBox()).width;
  assert.equal(Math.round(openWidth), Math.round(closedWidth));
  await page.getByRole('button', { name: '资料', exact: true }).click();
  await page.waitForTimeout(250);
  assert.ok(await drawer.isVisible());
  results.push('figure chunk opens the left drawer; overlay does not reflow the text column');

  // Four material types share the drawer.
  await tab('笔记').click();
  assert.ok(await materials.getByText(/^笔记/).first().isVisible());
  await tab('进度').click();
  assert.ok(await materials.getByText(/^阅读记录/).first().isVisible());
  await tab('讨论').click();
  assert.ok(await materials.getByRole('region', { name: '历史讨论' }).isVisible());
  await tab('图片').click();
  results.push('drawer tabs 图片 / 笔记 / 进度 / 讨论 from one overlay');

  const nav = page.getByRole('navigation', { name: '图片目录' });
  assert.equal(await nav.getByRole('button').count(), 5);
  let position = await top();
  await nav.getByRole('button', { name: /图 5/ }).click();
  await page.waitForTimeout(200);
  assert.ok(await gallery.evaluate(el => el.scrollTop) > 0);
  await stable(position);
  const before = JSON.stringify({ source: (await api()).source, position: (await api()).navigationCurrent?.chunkId });
  const beforePosts = posts.length;

  // Zoom keeps top-layer, natural size and focus restoration.
  await nav.getByRole('button', { name: '图 1', exact: true }).click();
  const zoom = page.getByRole('button', { name: '放大图 1', exact: true });
  await zoom.click();
  const modal = page.getByRole('dialog', { name: '图片放大' });
  assert.equal(await modal.evaluate(el => el.matches(':modal')), true);
  await modal.getByRole('button', { name: '原尺寸查看', exact: true }).click();
  assert.ok(await page.locator('.reader-image-viewport').evaluate(el => el.scrollWidth > el.clientWidth));
  await page.keyboard.press('Escape');
  assert.equal(await modal.isVisible(), false);
  assert.equal(await zoom.evaluate(el => el === document.activeElement), true);
  await zoom.click();
  await modal.getByRole('button', { name: '关闭放大', exact: true }).click();
  assert.equal(await zoom.evaluate(el => el === document.activeElement), true);
  assert.equal(JSON.stringify({ source: (await api()).source, position: (await api()).navigationCurrent?.chunkId }), before);
  assert.equal(posts.length, beforePosts);
  results.push('figure selection, zoom top layer, natural size and Close/Escape focus restore do not move the Cursor');

  // Language switch updates captions without a second gallery or a translation request.
  await stream.getByRole('button', { name: '查看原文', exact: true }).click();
  assert.ok((await gallery.innerText()).includes('Figure 1. Full architecture caption'));
  assert.equal(await gallery.locator('figure').count(), 5);
  await stream.getByRole('button', { name: '查看译文', exact: true }).click();
  assert.ok((await gallery.innerText()).includes('图 1：完整架构图注'));
  assert.equal(posts.length, beforePosts);
  results.push('language captions come from the same gallery without another request');

  await next(2);
  assert.equal(await gallery.locator('figure').count(), 5);
  assert.equal(await reader.getAttribute('data-side-open'), 'true');
  await next(3);
  assert.equal(await reader.getAttribute('data-side-open'), 'false');
  results.push('chunks with their own figures keep the catalogue; a chunk without figures closes the drawer');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(200);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await page.getByRole('button', { name: '资料', exact: true }).click();
  await page.waitForTimeout(250);
  assert.ok(await drawer.isVisible());
  const directory = page.getByRole('navigation', { name: '图片目录' });
  assert.equal(await directory.getByRole('button').count(), 5);
  const ys = await directory.getByRole('button').evaluateAll(els => els.map(el => el.getBoundingClientRect().y));
  assert.ok(ys.every(y => Math.abs(y - ys[0]) < 1));
  await page.screenshot({ path: `${output}/focus-figures-narrow.png` });
  await page.keyboard.press('Escape');
  assert.equal(await reader.getAttribute('data-side-open'), 'false');
  assert.ok((await page.getByRole('button', { name: '继续', exact: true }).boundingBox()).y < 844);
  results.push('390px drawer, horizontal figure navigation, no page overflow, Escape and Continue reachable');

  assert.deepEqual(errors, []);
  fs.writeFileSync(`${output}/focus-figures-browser-results.json`, JSON.stringify({ results, errors }, null, 2));
  console.log(JSON.stringify({ results, errors }));
} catch (error) {
  await page.screenshot({ path: `${output}/focus-figures-failure.png` });
  console.error(error); throw error;
} finally { await browser.close(); }
