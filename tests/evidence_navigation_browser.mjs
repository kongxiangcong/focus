import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const base = `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT || '8765'}`;
const answerLabel = process.env.FOCUS_EVIDENCE_ANSWER || '证据跳转验收';
const sourceA = process.env.FOCUS_EVIDENCE_SOURCE || 'Evaluating Emerging CXL-enabled Memory Pooling for HPC Systems-paper';
const sourceB = process.env.FOCUS_EVIDENCE_COMPARE || 'Evaluating Emerging CXL-enabled Memory Pooling for HPC Systems-2-paper';
const firstQuote = 'using the same emulated memory pool. The application is also executed';
const thirdQuote = 'a scalable high-bandwidth system';
const fourthQuote = 'The performance of seven scientific applications';
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE,
  ignoreDefaultArgs: ['--hide-scrollbars'],
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

const pane = page => page.getByLabel('文章原文', { exact: true });
const card = page => page.getByLabel('原文证据', { exact: true });
const citations = page => page.locator('.source-message[data-role="assistant"]').filter({ hasText: answerLabel }).last().locator('button[data-citation]');
const top = page => pane(page).evaluate(node => node.scrollTop);
const frames = page => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
const pageAt = (page, number) => pane(page).locator(`[data-pdf-page="${number}"]`);
const switches = page => page.getByRole('group', { name: '阅读方式', exact: true });
const progress = view => [view.navigationCurrent?.planId, view.navigationCurrent?.chunkId, view.readingRevision, view.readingProgress.length];

async function open({ blocked = [], touch = false, configure } = {}) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 950 }, hasTouch: touch });
  page.setDefaultTimeout(15000);
  const errors = [];
  let instance;
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { instance ||= request.headers()['x-focus-instance']; });
  await page.addInitScript(numbers => {
    localStorage.setItem('focus.readingMode', 'chat');
    // Gate PDF.js page replies while keeping the real Host download and PDF parser.
    const NativeWorker = window.Worker;
    const held = new Map();
    window.heldPdfPages = held;
    window.Worker = class extends NativeWorker {
      requests = new Map();
      constructor(...args) {
        super(...args);
        this.addEventListener('message', event => {
          const reply = event.data;
          const page = this.requests.get(reply.callbackId);
          if (!page || !reply.callback) return;
          this.requests.delete(reply.callbackId);
          event.stopImmediatePropagation();
          held.set(page, fail => {
            held.delete(page);
            const data = fail ? { ...reply, callback: 2, reason: { name: 'Error', message: 'Delayed page failed' } } : reply;
            this.dispatchEvent(new MessageEvent('message', { data }));
          });
        }, { capture: true });
      }
      postMessage(message, ...args) {
        const number = message.data?.pageIndex + 1;
        if (message.action === 'GetPage' && numbers.includes(number)) this.requests.set(message.callbackId, number);
        super.postMessage(message, ...args);
      }
    };
  }, blocked);
  await configure?.(page);
  await page.goto(`${base}/reading`);
  await pane(page).waitFor();
  async function host(path) {
    assert.ok(instance);
    const response = await page.request.get(`${base}${path}`, { headers: { 'X-FOCUS-Instance': instance } });
    const result = await response.json();
    assert.ok(result.ok, JSON.stringify(result));
    return result.value;
  }
  return { page, errors, host, snapshot: () => host('/reader/window'), instance: () => instance };
}

async function prepareAnswer() {
  const { page, snapshot, instance } = await open();
  await switches(page).getByRole('button', { name: '精读', exact: true }).click();
  await page.waitForFunction(() => {
    const panel = document.querySelector('[aria-label="精读"].reading-mode-panel');
    return panel && !panel.querySelector('.reading-preparation');
  });
  const view = await snapshot();
  assert.ok(view.navigationCurrent, 'the fixture has a ready close-reading plan');
  if (!view.readingStarted) {
    const { sourceId, planId, chunkId } = view.navigationCurrent;
    const response = await page.request.post(`${base}/reader/continue`, {
      headers: { 'X-FOCUS-Instance': instance() },
      data: { requestId: randomUUID(), beginBody: true, receipt: { sourceId, planId, chunkId, readingRevision: view.readingRevision } },
    });
    const result = await response.json();
    assert.ok(result.ok, JSON.stringify(result));
  }
  const reading = page.locator('.focus-stream .focus-reading').first();
  await reading.waitFor();
  if (!(await snapshot()).readingProgress.length) {
    await Promise.all([
      page.waitForResponse(response => response.url() === `${base}/reader/continue` && response.ok()),
      page.getByRole('button', { name: '继续', exact: true }).click(),
    ]);
  }
  await switches(page).getByRole('button', { name: '对话', exact: true }).click();
  if (!(await citations(page).count())) {
    await page.getByRole('textbox', { name: '输入消息' }).fill(answerLabel);
    await page.getByRole('button', { name: '发送', exact: true }).click();
  }
  await citations(page).nth(3).waitFor();
  assert.ok((await snapshot()).readingProgress.length > 0, 'navigation is checked with saved reading progress');
  await page.close();
}

async function waitForHeldPage(page, number) {
  await page.waitForFunction(number => window.heldPdfPages.has(number), number);
}

async function release(page, number, fail = false) {
  await page.evaluate(([number, fail]) => window.heldPdfPages.get(number)(fail), [number, fail]);
  await frames(page);
}

async function firstPage(page) {
  await pageAt(page, 1).waitFor();
  await pane(page).focus();
  await page.keyboard.press('Home');
  await pageAt(page, 1).locator('.paper-text span').first().waitFor({ state: 'attached' });
  await page.waitForFunction(() => document.querySelector('[aria-label="文章原文"]').scrollTop === 0);
}

async function latestWins(fail) {
  const { page, errors, snapshot } = await open({ blocked: [7, 8] });
  await firstPage(page);
  const before = progress(await snapshot());
  const initial = await top(page);
  await citations(page).nth(2).click();
  await waitForHeldPage(page, 8);
  assert.equal(await top(page), initial, 'waiting for evidence ③ keeps the current page in view');
  assert.equal(await card(page).count(), 0);
  await citations(page).nth(3).click();
  await waitForHeldPage(page, 7);
  await release(page, 7);
  await card(page).getByText(fourthQuote, { exact: true }).waitFor();
  await pageAt(page, 7).locator('.paper-text span').first().waitFor({ state: 'attached' });
  const landed = await top(page);
  assert.ok(landed > initial + 1000);
  await release(page, 8, fail);
  assert.equal(await top(page), landed);
  assert.equal(await card(page).getByText(thirdQuote, { exact: true }).count(), 0);
  assert.equal(await card(page).getByText(fourthQuote, { exact: true }).count(), 1);
  assert.equal(await page.getByRole('alert').filter({ hasText: /此页渲染失败|版面位置暂不可用/ }).count(), 0);
  assert.deepEqual(progress(await snapshot()), before);
  assert.deepEqual(errors, []);
  await page.close();
}

async function browse(page, gesture) {
  const box = await pane(page).boundingBox();
  const x = Math.round(box.x + box.width / 2), y = Math.round(box.y + box.height / 2);
  const initial = await top(page);
  if (gesture === 'wheel') {
    await page.mouse.move(x, y);
    await page.mouse.wheel(0, 280);
  } else if (gesture === 'touch') {
    const input = await page.context().newCDPSession(page);
    await input.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y, id: 1 }] });
    for (const offset of [40, 110, 180]) {
      await input.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y - offset, id: 1 }] });
    }
    await input.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  } else if (gesture === 'scrollbar') {
    const thumb = await pane(page).evaluate(node => {
      const box = node.getBoundingClientRect();
      const gap = box.width - node.clientWidth - node.clientLeft;
      return { x: box.right - gap / 2, y: box.top + node.clientHeight ** 2 / (2 * node.scrollHeight), gap };
    });
    assert.ok(thumb.gap > 3, 'native scrollbar has a hit target');
    await page.mouse.move(thumb.x, thumb.y);
    await page.mouse.down();
    await page.mouse.move(thumb.x, thumb.y + 35, { steps: 4 });
    await page.mouse.up();
  } else {
    await pane(page).focus();
    await page.keyboard.press('PageDown');
  }
  await page.waitForFunction(initial => document.querySelector('[aria-label="文章原文"]').scrollTop > initial + 30, initial);
  // Let native scrolling finish before measuring the location it chose.
  await page.waitForFunction(() => {
    const pane = document.querySelector('[aria-label="文章原文"]');
    if (pane.scrollTop !== window.lastTestScroll?.top) window.lastTestScroll = { top: pane.scrollTop, since: performance.now() };
    return performance.now() - window.lastTestScroll.since > 100;
  });
}

async function manualCancels(method) {
  const { page, errors, snapshot } = await open({ blocked: [8], touch: method === 'touch' });
  await firstPage(page);
  const before = progress(await snapshot());
  await citations(page).nth(2).click();
  await waitForHeldPage(page, 8);
  if (method === 'translation') {
    await page.getByRole('button', { name: '中文译文', exact: true }).click();
  } else if (method === 'tab') {
    await switches(page).getByRole('button', { name: '精读', exact: true }).click();
    await pane(page).waitFor({ state: 'hidden' });
  } else {
    await browse(page, method);
  }
  const position = method === 'tab' ? 0 : await top(page);
  await release(page, 8, true);
  if (method === 'tab') {
    await switches(page).getByRole('button', { name: '对话', exact: true }).click();
    await pane(page).waitFor();
  }
  if (method === 'translation') assert.equal(await page.getByRole('button', { name: '中文译文', exact: true }).getAttribute('aria-pressed'), 'true');
  assert.equal(await top(page), position);
  assert.equal(await card(page).count(), 0);
  assert.equal(await page.getByRole('alert').filter({ hasText: '此页渲染失败' }).count(), 0);
  assert.deepEqual(progress(await snapshot()), before);
  assert.deepEqual(errors, []);
  await page.close();
}

async function mobileCancels() {
  const { page, errors, snapshot } = await open({ blocked: [8] });
  const before = progress(await snapshot());
  await firstPage(page);
  await page.setViewportSize({ width: 720, height: 900 });
  await pane(page).waitFor({ state: 'hidden' });
  await citations(page).nth(2).click();
  await waitForHeldPage(page, 8);
  await page.getByRole('button', { name: '返回对话', exact: true }).click();
  await pane(page).waitFor({ state: 'hidden' });
  await release(page, 8);
  await page.getByRole('button', { name: '查看原文', exact: true }).click();
  await pane(page).waitFor();
  assert.equal(await top(page), 0);
  assert.equal(await card(page).count(), 0);
  assert.deepEqual(progress(await snapshot()), before);
  assert.deepEqual(errors, []);
  await page.close();
}

async function sourceRoundTrip(asset, fail = false) {
  const stale = `第一轮 A 的迟到${asset}`;
  let received, resume, finished, routeError;
  const arrived = new Promise(resolve => { received = resolve; });
  const hold = new Promise(resolve => { resume = resolve; });
  const delivered = new Promise(resolve => { finished = resolve; });
  const { page, errors, snapshot } = await open({
    async configure(page) {
      await page.route(url => decodeURIComponent(url.pathname) === `/library/sources/${sourceA}/${asset}`, async route => {
        try {
          const response = await route.fetch();
          received();
          await hold;
          if (fail) await route.abort('failed');
          else if (asset === 'original') await route.fulfill({ response });
          else {
            const body = await response.json();
            if (asset === 'opening') Object.assign(body.value, { status: 'ready', guide: stale });
            else {
              delete body.value.pdf;
              Object.assign(body.value, { markdown: stale, lineCount: 1 });
            }
            await route.fulfill({ status: response.status(), json: body });
          }
        } catch (error) {
          routeError = error;
          received();
        } finally {
          finished();
        }
      }, { times: 1 });
    },
  });
  const before = progress(await snapshot());
  await arrived;
  async function choose(source) {
    await page.getByRole('link', { name: '知识库', exact: true }).click();
    await page.locator(`[data-source-id=${JSON.stringify(source)}][role="listitem"]`).getByRole('button', { name: '阅读', exact: true }).click();
    await page.waitForURL('**/reading');
    await firstPage(page);
    assert.equal((await snapshot()).source.sourceId, source);
  }
  await choose(sourceB);
  await choose(sourceA);
  await browse(page, 'wheel');
  const position = await top(page);
  resume();
  await delivered;
  assert.ifError(routeError);
  await frames(page);
  assert.equal(await top(page), position);
  assert.equal(await page.getByText(stale, { exact: true }).count(), 0);
  assert.equal(await page.getByRole('alert').filter({ hasText: /PDF 加载失败|此页渲染失败/ }).count(), 0);
  assert.equal(await card(page).count(), 0);
  const after = await snapshot();
  assert.equal(after.source.sourceId, sourceA);
  assert.deepEqual(progress(after), before);
  assert.deepEqual(errors, []);
  await page.close();
}

async function exitFullscreen(interrupt) {
  const { page, errors, snapshot } = await open({ blocked: [8] });
  const before = progress(await snapshot());
  await firstPage(page);
  await page.getByRole('button', { name: '对话全屏', exact: true }).click();
  if (!interrupt) {
    // Exiting fullscreen from the PDF's end clamps its scroll position as the paper narrows.
    await pane(page).focus();
    await page.keyboard.press('End');
    await page.waitForFunction(() => {
      const pane = document.querySelector('[aria-label="文章原文"]');
      return pane.scrollTop >= pane.scrollHeight - pane.clientHeight - 1;
    });
  }
  await citations(page).nth(2).click();
  await waitForHeldPage(page, 8);
  const fullscreenPosition = await top(page);
  await page.getByRole('button', { name: '关闭全屏模式', exact: true }).click();
  if (interrupt) await browse(page, 'wheel');
  else {
    await frames(page);
    assert.ok(await top(page) < fullscreenPosition, 'the window layout clamps the previously saved scroll position');
  }
  const position = await top(page);
  await release(page, 8);
  if (interrupt) {
    assert.equal(await top(page), position);
    assert.equal(await card(page).count(), 0);
  } else {
    await card(page).getByText(thirdQuote, { exact: true }).waitFor();
    const visible = await pageAt(page, 8).locator('[data-active="true"]').first().evaluate(block => {
      const region = block.getBoundingClientRect();
      const view = block.closest('.source-original').getBoundingClientRect();
      return region.top >= view.top && region.bottom <= view.bottom;
    });
    assert.ok(visible, 'the cited PDF block is visible in the window layout');
  }
  assert.deepEqual(progress(await snapshot()), before);
  assert.deepEqual(errors, []);
  await page.close();
}

async function exitDuringPlacement() {
  const { page, errors, snapshot } = await open({ blocked: [8] });
  await firstPage(page);
  const before = progress(await snapshot());
  await page.getByRole('button', { name: '对话全屏', exact: true }).click();
  await pane(page).evaluate(node => {
    node.style.setProperty('--reader-duration-move', '1600ms');
    const destination = node.querySelector('[data-pdf-page="8"]');
    node.scrollTop += destination.getBoundingClientRect().top - node.getBoundingClientRect().top - node.clientHeight * .7;
  });
  await frames(page);
  const from = await top(page);
  await citations(page).nth(2).click();
  await waitForHeldPage(page, 8);
  await release(page, 8);
  await page.waitForFunction(from => document.querySelector('[aria-label="文章原文"]').scrollTop !== from, from);
  assert.equal(await card(page).count(), 0, 'the smooth placement is in flight when Escape is pressed');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '关闭全屏模式', exact: true }).waitFor({ state: 'hidden' });
  await card(page).getByText(thirdQuote, { exact: true }).waitFor();
  const visible = await pageAt(page, 8).locator('[data-active="true"]').first().evaluate(block => {
    const region = block.getBoundingClientRect();
    const view = block.closest('.source-original').getBoundingClientRect();
    return region.top >= view.top && region.bottom <= view.bottom;
  });
  assert.ok(visible, 'the existing jump retargets to the cited region in the window layout');
  await card(page).getByRole('button', { name: /^证据 3/ }).click();
  assert.ok(await citations(page).nth(2).evaluate(node => node === document.activeElement), 'the completed jump keeps its citation return');
  assert.deepEqual(progress(await snapshot()), before);
  assert.deepEqual(errors, []);
  await page.close();
}

async function chatScrollbarCancels() {
  const { page, errors, snapshot } = await open({ blocked: [8] });
  await firstPage(page);
  const chat = page.getByLabel('文章对话', { exact: true });
  for (let index = 0; index < 6; index++) {
    const question = `对话滚动测试 ${index}`;
    await page.getByRole('textbox', { name: '输入消息' }).fill(question);
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await chat.locator('[data-role="assistant"]').getByText(`${question}。`, { exact: true }).waitFor();
  }
  const before = progress(await snapshot());
  await citations(page).nth(2).click();
  await waitForHeldPage(page, 8);
  const position = await top(page);
  const thumb = await chat.evaluate(node => {
    const box = node.getBoundingClientRect();
    const gap = box.width - node.clientWidth - node.clientLeft;
    const height = node.clientHeight ** 2 / node.scrollHeight;
    const travel = node.clientHeight - height;
    const offset = travel * node.scrollTop / (node.scrollHeight - node.clientHeight);
    return { x: box.right - gap / 2, y: box.top + offset + height / 2, gap, top: node.scrollTop, delta: offset < travel / 2 ? 70 : -70 };
  });
  assert.ok(thumb.gap > 3, 'the chat has a native scrollbar hit target');
  await page.mouse.move(thumb.x, thumb.y);
  await page.mouse.down();
  await page.mouse.move(thumb.x, thumb.y + thumb.delta, { steps: 4 });
  await page.mouse.up();
  await page.waitForFunction(top => document.querySelector('[aria-label="文章对话"]').scrollTop !== top, thumb.top);
  await release(page, 8);
  assert.equal(await top(page), position);
  assert.equal(await card(page).count(), 0);
  assert.deepEqual(progress(await snapshot()), before);
  assert.deepEqual(errors, []);
  await page.close();
}

async function retryFailedPage() {
  const { page, errors } = await open({ blocked: [8] });
  await firstPage(page);
  await citations(page).nth(2).click();
  await waitForHeldPage(page, 8);
  await browse(page, 'wheel');
  await release(page, 8, true);
  assert.equal(await page.getByRole('alert').filter({ hasText: '此页渲染失败' }).count(), 0);
  await pageAt(page, 8).scrollIntoViewIfNeeded();
  const alert = pageAt(page, 8).getByRole('alert').filter({ hasText: '此页渲染失败' });
  await alert.waitFor();
  const before = await top(page);
  await alert.getByRole('button', { name: '重试', exact: true }).click();
  await waitForHeldPage(page, 8);
  await release(page, 8);
  await pageAt(page, 8).locator('.paper-text span').first().waitFor({ state: 'attached' });
  assert.equal(await alert.count(), 0);
  assert.ok(Math.abs(await top(page) - before) <= 1, 'retry keeps the PDF at the page the reader chose');
  assert.deepEqual(errors, []);
  await page.close();
}

async function resetNavigation({ confirm, fail = false, releaseDuringReset = false }) {
  let resumeReset;
  const holdReset = new Promise(resolve => { resumeReset = resolve; });
  let resetCount = 0;
  const isReset = url => new URL(url).pathname.endsWith('/reset-reading');
  const { page, errors, host, snapshot } = await open({ blocked: [8], async configure(page) {
    await page.route(url => isReset(url), async route => {
      resetCount++;
      await holdReset;
      await route.continue();
    });
  } });
  const completed = async id => (await host('/library/sources')).find(source => source.sourceId === id).progress.completed;
  const returnTo = number => pane(page).getByRole('button', { name: `返回回答证据 ${number}`, exact: true }).first();
  const tab = name => switches(page).getByRole('button', { name, exact: true });
  const archivedAnswer = view => view.conversation.find(message => message.role === 'assistant' && message.content.includes(answerLabel));
  function noOldNavigation() {
    return Promise.all([
      card(page).waitFor({ state: 'hidden' }),
      returnTo(1).waitFor({ state: 'detached' }),
      returnTo(3).waitFor({ state: 'detached' }),
      page.getByText(/此页渲染失败|版面位置暂不可用|原文证据不可定位/).filter({ visible: true }).first().waitFor({ state: 'hidden' }),
    ]);
  }

  try {
    const before = await snapshot();
    const sourceId = before.source.sourceId;
    const readCount = await completed(sourceId);
    assert.ok(before.navigationCurrent?.chunkId && readCount > 0, 'there is saved close-reading progress to reset');
    const answer = archivedAnswer(before);
    assert.deepEqual(answer.evidence.slice(2).map(item => item.quote.exact), [thirdQuote, fourthQuote]);

    await firstPage(page);
    await citations(page).first().click();
    await card(page).getByText(firstQuote, { exact: true }).waitFor();
    await returnTo(1).waitFor();
    await firstPage(page);
    await citations(page).nth(2).click();
    await waitForHeldPage(page, 8);
    const latePage = await page.evaluateHandle(() => window.heldPdfPages.get(8));
    const settleLatePage = async () => {
      await latePage.evaluate((deliver, fail) => deliver(fail), fail);
      await frames(page);
    };
    await page.getByRole('button', { name: '重新阅读', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '重新阅读本篇？', exact: true });

    if (!confirm) {
      await dialog.getByRole('button', { name: '取消', exact: true }).click();
      await returnTo(1).waitFor();
      await settleLatePage();
      await card(page).getByText(thirdQuote, { exact: true }).waitFor();
      await returnTo(3).click();
      assert.equal(await citations(page).nth(2).evaluate(node => document.activeElement === node), true);
      const after = await snapshot();
      assert.equal(resetCount, 0);
      assert.equal(after.discussionId, before.discussionId);
      assert.deepEqual(progress(after), progress(before));
      assert.equal(await completed(sourceId), readCount);
    } else {
      await Promise.all([
        page.waitForRequest(request => request.method() === 'POST' && isReset(request.url())),
        dialog.getByRole('button', { name: '确认重新阅读', exact: true }).click(),
      ]);
      const waitingPosition = await top(page);
      assert.equal((await snapshot()).discussionId, before.discussionId, 'the reset request is still held');
      await noOldNavigation();
      assert.equal(await citations(page).count(), 0);
      if (releaseDuringReset) {
        await settleLatePage();
        await noOldNavigation();
        assert.equal(await top(page), waitingPosition);
        assert.equal(await page.getByRole('button', { name: '原版 PDF', exact: true }).getAttribute('aria-pressed'), 'true');
      }
      const resetResponse = page.waitForResponse(response => isReset(response.url()) && response.ok());
      resumeReset();
      await resetResponse;
      await tab('精读').waitFor();
      await page.waitForFunction(() => document.querySelector('.reading-mode-panel')?.getAttribute('aria-label') === '精读');
      await page.locator('.focus-stream').waitFor();
      const after = await snapshot();
      assert.notEqual(after.discussionId, before.discussionId);
      assert.equal(after.source.sourceId, sourceId);
      assert.notEqual(after.navigationCurrent?.planId, before.navigationCurrent.planId);
      assert.equal(after.navigationCurrent?.index, 1);
      assert.equal(after.readingProgress.length, 0);
      assert.equal(await completed(sourceId), 0);
      assert.deepEqual(after.conversation, []);

      await tab('对话').click();
      await firstPage(page);
      const freshPosition = await top(page);
      if (!releaseDuringReset) await settleLatePage();
      await noOldNavigation();
      assert.equal(await top(page), freshPosition);
      assert.equal(await citations(page).count(), 0);
      assert.equal(await pane(page).getByRole('button', { name: /返回相关回答|查看 \d+ 条相关回答/ }).count(), 0);
      const discussions = page.getByLabel('对话记录', { exact: true });
      await discussions.selectOption(before.discussionId);
      await citations(page).nth(3).waitFor();
      await noOldNavigation();
      const archived = await snapshot();
      assert.equal(archived.discussionId, before.discussionId);
      assert.equal(archivedAnswer(archived).content, answer.content);
      assert.deepEqual(archivedAnswer(archived).evidence, answer.evidence);
      assert.equal(await completed(sourceId), 0);
      await discussions.selectOption(after.discussionId);
      await citations(page).nth(3).waitFor({ state: 'detached' });
    }
    assert.deepEqual(errors, []);
  } finally {
    resumeReset();
    await page.close();
  }
}

try {
  await prepareAnswer();
  const scenarios = {
    latest: async () => { await latestWins(false); await latestWins(true); },
    manual: async () => {
      for (const method of ['wheel', 'touch', 'scrollbar', 'keyboard', 'translation', 'tab']) await manualCancels(method);
      await mobileCancels();
    },
    fullscreen: async () => { await exitFullscreen(false); await exitFullscreen(true); },
    'fullscreen-placement': exitDuringPlacement,
    'chat-scrollbar': chatScrollbarCancels,
    'pdf-retry': retryFailedPage,
    sources: async () => {
      for (const asset of ['document', 'original', 'opening']) await sourceRoundTrip(asset);
      await sourceRoundTrip('original', true);
    },
    reset: async () => {
      await resetNavigation({ confirm: false });
      const confirmations = [
        { releaseDuringReset: true }, { fail: true, releaseDuringReset: true }, {}, { fail: true },
      ];
      for (const [index, options] of confirmations.entries()) {
        if (index) await prepareAnswer();
        await resetNavigation({ confirm: true, ...options });
      }
    },
  };
  for (const [name, scenario] of Object.entries(scenarios)) {
    if (!process.env.FOCUS_EVIDENCE_CASE || process.env.FOCUS_EVIDENCE_CASE === name) {
      await scenario();
      console.log(`PASS ${name} evidence navigation and persisted reading progress through the formal Host`);
    }
  }
} finally {
  await browser.close();
}
