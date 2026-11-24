import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const base = `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}`;
let currentPage;
const title = 'Single-column fixture';
const page8 = 'The eighth page contains the verified result.';
const page12 = 'The twelfth page follows the wider examples.';
const unknown = 'This appendix passage has no verified page placement.';

async function openSource(page, format) {
  const library = page.getByRole('link', { name: '知识库', exact: true });
  await library.click();
  const row = page.getByRole('listitem').filter({ has: page.getByRole('button', { name: `Single column ${format}`, exact: true }) });
  await row.getByRole('button', { name: '阅读', exact: true }).click();
  if (page.viewportSize().width === 390) {
    await page.getByRole('combobox', { name: '阅读方式', exact: true }).selectOption('chat');
    await page.getByRole('button', { name: /^查看(正文|原文)$/ }).click();
  } else {
    await page.getByRole('group', { name: '阅读方式', exact: true }).getByRole('button', { name: '对话', exact: true }).click();
  }
  const source = page.getByLabel('文章原文', { exact: true });
  await source.getByRole('heading', { name: title }).waitFor();
  return source;
}

async function checkContent(page, source) {
  const article = source.locator('article');
  const order = await article.locator('h1, h2, img, table, pre, .katex-display').evaluateAll(nodes =>
    nodes.map(node => node.getAttribute('alt') || (node.matches('h1, h2') ? node.textContent : node.tagName)));
  assert.deepEqual(order, [title, 'Results', 'Fixture figure', 'TABLE', 'PRE', 'SPAN', 'Appendix', 'References']);
  await source.getByText('Canonical bibliography entry.').waitFor();
  const figure = source.getByRole('img', { name: 'Fixture figure' });
  await figure.scrollIntoViewIfNeeded();
  await page.waitForFunction(() => [...document.images].some(image => image.alt === 'Fixture figure' && image.naturalWidth === 1));

  const paragraph = source.locator('p').filter({ hasText: page8 });
  await paragraph.scrollIntoViewIfNeeded();
  await paragraph.evaluate(node => {
    const prose = [...node.childNodes].filter(child => !(child instanceof HTMLElement && child.matches('[data-anno-ui]')));
    const range = document.createRange();
    range.setStartBefore(prose[0]);
    range.setEndAfter(prose.at(-1));
    document.getSelection().removeAllRanges();
    document.getSelection().addRange(range);
  });
  assert.equal(await page.evaluate(() => document.getSelection().toString()), page8);
  await page.getByRole('button', { name: '记笔记', exact: true }).waitFor();
  await page.getByRole('button', { name: '取消选择', exact: true }).click();
  await page.evaluate(() => document.getSelection().removeAllRanges());

  const typography = await source.evaluate(node => {
    const markdown = node.querySelector('article .focus-markdown');
    return { size: getComputedStyle(markdown).fontSize, ink: getComputedStyle(markdown).color };
  });
  for (const block of await article.locator('.focus-table, pre, .katex-display').all()) {
    await block.scrollIntoViewIfNeeded();
    const width = await block.evaluate(node => ({ scroll: node.scrollWidth, content: node.clientWidth, overflow: getComputedStyle(node).overflowX }));
    assert.ok(width.scroll > width.content, JSON.stringify(width));
    assert.match(width.overflow, /^(auto|scroll)$/);
  }
  const widths = await source.evaluate(node => [node.scrollWidth, node.clientWidth, document.documentElement.scrollWidth, innerWidth]);
  assert.equal(widths[0], widths[1], 'article does not overflow its own pane');
  assert.equal(widths[2], widths[3], 'page does not overflow viewport');
  assert.equal(await source.locator('canvas').count(), 0);
  return typography;
}

async function readAt(page, source, text) {
  const paragraph = source.getByText(text, { exact: true });
  const values = await paragraph.evaluate(node => {
    const pane = node.closest('[aria-label="文章原文"]');
    // Bring estimated off-screen layout into view before doing a real wheel scroll to the reading line.
    node.scrollIntoView({ block: 'center' });
    const rect = pane.getBoundingClientRect();
    const y = rect.top + pane.clientHeight * .32;
    return { x: rect.left + rect.width * .5, y, delta: node.getBoundingClientRect().top - y + 10 };
  });
  await page.mouse.move(values.x, values.y);
  await page.mouse.wheel(0, values.delta);
}

async function verifyOriginal(page, format, expectedPage) {
  const link = page.getByRole('link', { name: '打开原件 ↗', exact: true });
  await link.waitFor();
  assert.equal(await link.count(), 1);
  assert.equal(await link.getAttribute('target'), '_blank');
  const href = new URL(await link.getAttribute('href'), base);
  assert.equal(href.hash, expectedPage ? `#page=${expectedPage}` : '');
  assert.match(href.pathname, /\/original$/);
  assert.equal(href.pathname.split('/').at(-2), {
    pdf: 'fixture-paper', html: 'fixture-html-article', markdown: 'fixture-markdown-article',
  }[format]);
  const response = await page.request.get(href.href, { timeout: 8000 });
  assert.ok(response.ok(), `${response.status()}: ${href.pathname}`);
  assert.match(response.headers()['content-type'], { pdf: /application\/pdf/, html: /text\/html/, markdown: /text\/markdown/ }[format]);
  if (format === 'html') assert.equal(await response.text(), '<h1>Saved HTML original</h1>');
}

try {
  for (const width of [1440, 390]) {
    const page = currentPage = await browser.newPage({ viewport: { width, height: 844 }, reducedMotion: 'reduce' });
    page.setDefaultTimeout(8000);
    await page.goto(`${base}/reading`);
    await page.getByRole('link', { name: '设置', exact: true }).click();
    const dark = width === 1440;
    await page.getByRole('radio', { name: dark ? '深色' : '浅色', exact: true }).check();
    await page.getByRole('slider', { name: '字号', exact: true }).press(dark ? 'End' : 'Home');
    let sourceTypography;
    for (const format of ['pdf', 'html', 'markdown']) {
      const source = await openSource(page, format);
      const typography = await checkContent(page, source);
      assert.equal(typography.size, dark ? '26px' : '16px');
      assert.equal(await page.locator('html').getAttribute('data-theme'), dark ? 'dark' : 'light');
      if (format === 'pdf') {
        const back = page.getByRole('button', { name: '返回对话', exact: true });
        if (await back.isVisible()) await back.click();
        if (width === 1440) {
          await page.getByRole('textbox', { name: '输入消息' }).fill('核对第八页');
          await page.getByRole('button', { name: '发送', exact: true }).click();
        }
        await page.getByLabel('文章对话', { exact: true }).getByRole('button', { name: '1', exact: true }).last().press('Enter');
        await page.waitForFunction(() => [...document.querySelectorAll('a')].some(a => a.textContent === '打开原件 ↗' && a.hash === '#page=8'));
        await verifyOriginal(page, 'pdf', 8);
        await readAt(page, source, page12);
        await page.waitForFunction(() => [...document.querySelectorAll('a')].some(a => a.textContent === '打开原件 ↗' && a.hash === '#page=12'));
        await verifyOriginal(page, 'pdf', 12);
        await readAt(page, source, unknown);
        await page.waitForFunction(() => [...document.querySelectorAll('a')].some(a => a.textContent === '打开原件 ↗' && !a.hash));
        await verifyOriginal(page, 'pdf');
        sourceTypography = typography;
      } else {
        assert.deepEqual(typography, sourceTypography);
        await verifyOriginal(page, format);
      }
    }
    // A compatible Host can return readable content with no available original.
    await page.route('**/library/sources/fixture-markdown-article/document', async route => {
      const response = await route.fetch();
      const body = await response.json();
      await route.fulfill({ response, json: { ...body, value: { ...body.value, original: null } } });
    });
    await page.reload();
    await openSource(page, 'markdown');
    assert.equal(await page.getByRole('link', { name: '打开原件 ↗', exact: true }).count(), 0);
    await page.close();
  }
  console.log('PASS single-column PDF, HTML and Markdown at 1440px and 390px, with current-page and original-file links');
} catch (error) {
  console.error((await currentPage?.locator('body').innerText())?.slice(0, 1800));
  throw error;
} finally { await browser.close(); }
