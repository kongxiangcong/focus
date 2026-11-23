import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const gesture = process.env.FOCUS_BROWSER_FINISH_GESTURE;
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE,
  ignoreDefaultArgs: gesture === 'scrollbar' ? ['--hide-scrollbars'] : [],
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const mode = process.env.FOCUS_BROWSER_FINISH_CASE;
const short = mode === 'short';
assert.ok(short || mode === 'long');
const total = short ? 1 : 3;
const base = `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT || '8765'}`;
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, hasTouch: gesture === 'touch' });
page.setDefaultTimeout(8000);
const snapshot = async () => (await (await page.request.get(`${base}/reader/window`)).json()).value;
const stream = page.locator('.focus-stream');
const lastBody = stream.locator(`[data-lens-index="${total}"] .focus-reading > .focus-markdown`).last();
const finish = page.getByRole('button', { name: '读完', exact: true });
const requests = [];
page.on('request', request => {
  if (request.url() === `${base}/reader/finish`) requests.push(request.postDataJSON());
});
await page.route('**/reader/workspace', route => route.fulfill({ json: { ok: true, value: { bound: true } } }));
await page.addInitScript(() => localStorage.setItem('focus.readingMode', 'chunks'));

function progress(view) {
  return [view.readingRevision, view.navigationCurrent?.chunkId, view.readingProgress.length];
}

async function battery(completed) {
  await page.getByRole('link', { name: '知识库', exact: true }).click();
  const bar = page.getByRole('progressbar', { name: /精读进度$/ });
  await bar.waitFor();
  assert.equal(await bar.getAttribute('aria-valuenow'), String(completed));
  assert.equal(await bar.getAttribute('aria-valuemax'), String(total));
  assert.equal(await bar.getAttribute('data-level'), completed ? 'full' : 'empty');
  await page.getByRole('button', { name: completed ? /已读完\s*1/ : /阅读中\s*1/ }).waitFor();
}

async function scrollPastBodyEnd() {
  const box = await stream.boundingBox();
  const x = Math.round(box.x + box.width / 2);
  const y = Math.round(box.y + box.height / 2);
  if (gesture === 'touch') {
    const input = await page.context().newCDPSession(page);
    await input.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y, id: 1 }] });
    for (const distance of [30, 75, 120]) {
      await input.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y - distance, id: 1 }] });
      await page.waitForTimeout(30);
    }
    await input.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  } else if (gesture === 'scrollbar') {
    const thumb = await stream.evaluate(pane => {
      const box = pane.getBoundingClientRect();
      const gutter = box.width - pane.clientWidth - pane.clientLeft;
      return { x: box.right - gutter / 2, y: box.top + (pane.scrollTop + pane.clientHeight / 2) * pane.clientHeight / pane.scrollHeight, gutter };
    });
    assert.ok(thumb.gutter > 3, 'native scrollbar has a hit target');
    await page.mouse.move(thumb.x, thumb.y);
    await page.mouse.down();
    await page.waitForTimeout(300);
    await page.mouse.move(thumb.x, thumb.y + 20, { steps: 4 });
    await page.mouse.up();
  } else {
    await page.mouse.move(x, y);
    await page.mouse.wheel(0, 70);
  }
}

try {
  await page.goto(`${base}/reading`);
  const enterBody = page.getByRole('button', { name: '进入正文', exact: true });
  const firstChunk = stream.locator('[data-lens-index="1"] .focus-reading').first();
  await enterBody.or(firstChunk).first().waitFor();
  if (await enterBody.isVisible()) await enterBody.click();
  await firstChunk.waitFor();
  if (short) {
    const before = progress(await snapshot());
    await battery(0);
    await page.getByRole('link', { name: '阅读', exact: true }).click();
    await finish.waitFor({ timeout: 5000 });
    assert.deepEqual(progress(await snapshot()), before);
    assert.equal(await page.locator('.mist-reading-actions').getByRole('button', { name: '读完', exact: true }).count(), 0);
    if (gesture === 'touch') await finish.tap();
    else await finish.press('Enter');
  } else {
    for (let index = 2; index <= total; index++) {
      await page.getByRole('button', { name: '继续', exact: true }).click();
      await stream.locator(`[data-lens-index="${index}"] .focus-reading`).waitFor();
    }
    await lastBody.waitFor();
    await page.waitForTimeout(650);
    const before = progress(await snapshot());
    assert.equal(await finish.count(), 0);

    const moveNearBoundary = async (distance) => lastBody.evaluate((body, gap) => {
      const pane = body.closest('.focus-stream');
      const bottom = pane.getBoundingClientRect().top + pane.clientTop + pane.clientHeight;
      pane.scrollTop += body.getBoundingClientRect().bottom - bottom - gap;
    }, distance);
    await moveNearBoundary(-20);
    await page.waitForTimeout(250);
    assert.deepEqual(progress(await snapshot()), before);
    assert.equal(requests.length, 0);

    // Switch language, layout, view and route without consuming the active Cursor.
    await lastBody.locator('..').getByRole('button', { name: '查看原文' }).click();
    await page.setViewportSize({ width: 1100, height: 940 });
    await lastBody.locator('..').getByRole('button', { name: '查看译文' }).click();
    await page.getByRole('button', { name: '全屏', exact: true }).click();
    await page.keyboard.press('Escape');
    const modes = page.getByRole('group', { name: '阅读方式' });
    await modes.getByRole('button', { name: '对话', exact: true }).click();
    assert.equal(await finish.count(), 0);
    await modes.getByRole('button', { name: '精读', exact: true }).click();
    await page.getByRole('link', { name: '知识库', exact: true }).click();
    await page.getByRole('link', { name: '阅读', exact: true }).click();
    await page.waitForTimeout(750);
    assert.deepEqual(progress(await snapshot()), before);

    // Stay above the final paragraph, then cross its end with actual browser input.
    await moveNearBoundary(35);
    await page.waitForTimeout(100);
    await scrollPastBodyEnd();
  }
  await page.locator('.focus-finished').waitFor({ timeout: 5000 });
  const completed = await snapshot();
  assert.equal(completed.status, 'completed');
  assert.equal(completed.readingProgress.length, total);
  assert.equal(requests.length, 1);
  await battery(total);
  await page.reload();
  await page.locator('[role="progressbar"][data-level="full"]').waitFor();
  await page.getByRole('link', { name: '阅读', exact: true }).click();
  await stream.locator('.focus-reading').last().waitFor();
  assert.equal(await stream.locator('.focus-reading').count(), total);
  assert.equal((await snapshot()).status, 'completed');
  assert.equal(requests.length, 1);
  console.log(`PASS ${mode} final chunk through the workbench, Host, and library${gesture ? ` (${gesture})` : ''}`);
} catch (error) {
  console.error((await page.locator('body').innerText()).slice(0, 1800));
  throw error;
} finally {
  await browser.close();
}
