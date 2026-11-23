/**
 * Build @focus/standalone, then serve an isolated Batch B workspace with
 * tests/pdf_evidence_browser.py. FOCUS_BROWSER_URL selects that Host.
 * FOCUS_THEME_ARTIFACTS optionally saves the browser screenshots and measurements.
 * FOCUS_THEME_CASE optionally selects a theme or a single theme-width-layout combination.
 */
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { join } from 'node:path';

const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.FOCUS_BROWSER_URL;
const artifacts = process.env.FOCUS_THEME_ARTIFACTS;
const question = '当前回答 B';
const quote = 'a scalable high-bandwidth';
assert.ok(base, 'Set FOCUS_BROWSER_URL to the isolated PDF evidence Host.');

const browser = await chromium.launch({
  headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

async function open(theme = 'blue', options = {}, appReducedMotion = false) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, ...options });
  page.setDefaultTimeout(25000);
  await page.addInitScript(({ theme, appReducedMotion }) => {
    localStorage.setItem('focus.theme', theme === 'dark' ? 'dark' : 'light');
    localStorage.setItem('focus.accent', theme === 'dark' ? 'red' : theme);
    localStorage.setItem('focus.readingMode', 'chat');
    localStorage.setItem('focus.reducedMotion', String(appReducedMotion));
    window.themeEvents = { open: 0, error: 0, snapshot: 0 };
    const NativeEventSource = window.EventSource;
    const connections = new Set();
    window.EventSource = class extends EventTarget {
      constructor(...args) {
        super();
        this.args = args;
        this.connect();
        connections.add(this);
      }
      connect() {
        this.native = new NativeEventSource(...this.args);
        for (const name of ['open', 'snapshot', 'text', 'workspace-changed']) {
          this.native.addEventListener(name, event => {
            if (name in window.themeEvents) window.themeEvents[name]++;
            this.dispatchEvent(event instanceof MessageEvent
              ? new MessageEvent(name, { data: event.data, lastEventId: event.lastEventId })
              : new Event(name));
          });
        }
        this.native.onerror = event => this.onerror?.(event);
      }
      close() {
        this.native.close();
        connections.delete(this);
      }
    };
    window.reconnectThemeEvents = () => {
      for (const stream of connections) {
        stream.native.close();
        window.themeEvents.error++;
        stream.onerror?.(new Event('error'));
        stream.connect();
      }
    };
  }, { theme, appReducedMotion });
  let instance;
  page.on('request', request => { instance ||= request.headers()['x-focus-instance']; });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error' && /content security policy/i.test(message.text())) errors.push(message.text());
  });
  try {
    const response = await page.goto(new URL('/reading', base).href);
    assert.ok(response.ok());
    assert.match(response.headers()['content-security-policy'], /default-src 'self'/);
    await page.getByLabel('文章对话', { exact: true }).waitFor();
  } catch (error) {
    await page.close();
    throw error;
  }

  const host = async (path, data) => {
    assert.ok(instance);
    const response = await page.request.fetch(new URL(path, base).href, {
      method: data ? 'POST' : 'GET',
      headers: { 'X-FOCUS-Instance': instance },
      data,
    });
    const result = await response.json();
    assert.ok(result.ok, JSON.stringify(result));
    return result.value;
  };
  return { page, host, errors };
}

function mode(page, name) {
  return page.getByRole('group', { name: '阅读方式', exact: true }).getByRole('button', { name, exact: true });
}

function citation(page) {
  return page.getByLabel('文章对话', { exact: true })
    .locator('[data-role="assistant"]').filter({ hasText: question }).last()
    .getByRole('button', { name: '4', exact: true });
}

function battery(page) {
  return page.getByRole('progressbar', { name: /精读进度$/ }).filter({ visible: true }).first();
}

async function fixture() {
  const { page, host } = await open();
  try {
    await mode(page, '精读').click();
    const window = await host('/reader/window');
    assert.ok(window.navigationCurrent, 'the fixture needs a ready reading plan');
    if (!window.readingStarted) {
      const { sourceId, planId, chunkId } = window.navigationCurrent;
      await host('/reader/continue', { requestId: randomUUID(), beginBody: true,
        receipt: { sourceId, planId, chunkId, readingRevision: window.readingRevision } });
    }
    await page.locator('.focus-stream .focus-reading').first().waitFor();
    const read = (await host('/reader/window')).readingProgress.length;
    for (let completed = read; completed < 3; completed++) {
      const receipt = page.waitForResponse(response => response.url().endsWith('/reader/continue') && response.ok());
      await page.getByRole('button', { name: '继续', exact: true }).click();
      assert.ok((await (await receipt).json()).ok);
      await page.locator(`[data-chunk-key$="/chunk-00${completed + 2}"]`).last().waitFor();
    }

    await mode(page, '对话').click();
    if (!(await citation(page).count())) {
      await page.getByRole('textbox', { name: '输入消息' }).fill(question);
      await page.getByRole('button', { name: '发送', exact: true }).click();
    }
    await citation(page).waitFor({ timeout: 40000 });
  } finally {
    await page.close();
  }
}

async function contrast(locator, property = 'color', against = 'own', pseudo = null) {
  return locator.evaluate((element, { property, against, pseudo }) => {
    const pixel = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
    function rgba(value) {
      pixel.clearRect(0, 0, 1, 1);
      pixel.fillStyle = value;
      pixel.fillRect(0, 0, 1, 1);
      return [...pixel.getImageData(0, 0, 1, 1).data];
    }
    function composite(top, bottom) {
      return top.slice(0, 3).map((value, index) => value * top[3] / 255 + bottom[index] * (1 - top[3] / 255));
    }
    function luminance(color) {
      return color.map(value => value / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4)
        .reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
    }
    const ancestors = [];
    for (let ancestor = against === 'parent' ? element.parentElement : element; ancestor; ancestor = ancestor.parentElement) {
      ancestors.unshift(ancestor);
    }
    let background = [255, 255, 255];
    for (const ancestor of ancestors) {
      background = composite(rgba(getComputedStyle(ancestor).backgroundColor), background);
      if (against === 'paper' && ancestor.matches('[data-pdf-page]')) {
        const canvas = ancestor.querySelector('canvas');
        const rect = canvas.getBoundingClientRect();
        const target = element.getBoundingClientRect();
        // The midpoint of the upper edge of the rotated paragraph is on the page itself.
        const x = Math.floor((target.left + target.width / 2 - rect.left) * canvas.width / rect.width);
        const y = Math.floor((target.top - rect.top) * canvas.height / rect.height);
        background = composite([...canvas.getContext('2d').getImageData(x, y, 1, 1).data], background);
      }
    }
    const foreground = composite(rgba(getComputedStyle(element, pseudo).getPropertyValue(property)), background);
    const [dark, light] = [luminance(foreground), luminance(background)].sort((a, b) => a - b);
    return { foreground, background, ratio: (light + .05) / (dark + .05) };
  }, { property, against, pseudo });
}

function minimum(measurement, ratio, component) {
  assert.ok(measurement.ratio >= ratio, `${component}: ${measurement.ratio.toFixed(3)} < ${ratio}`);
  return measurement;
}

async function motionSettled(locator) {
  await locator.evaluate(async node => {
    await new Promise(resolve => requestAnimationFrame(resolve));
    await Promise.allSettled(node.getAnimations().map(animation => animation.finished));
  });
}

async function fullyVisible(locator) {
  await locator.waitFor();
  const rect = await locator.boundingBox();
  const { width, height } = locator.page().viewportSize();
  assert.ok(rect.x >= -1 && rect.y >= -1 && rect.x + rect.width <= width + 1 && rect.y + rect.height <= height + 1,
    `${locator} is clipped by the viewport: ${JSON.stringify(rect)}`);
}

async function hitTarget(locator) {
  await fullyVisible(locator);
  assert.ok(await locator.evaluate(element => {
    const rect = element.getBoundingClientRect();
    return element.contains(document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2));
  }), `${locator} is covered at its center`);
}

async function screenshot(page, name) {
  if (artifacts && name) await page.screenshot({ path: join(artifacts, name) });
}

async function progress(host) {
  const { source, navigationCurrent, readingRevision, readingProgress } = await host('/reader/window');
  const sources = await host('/library/sources');
  const library = sources.find(item => item.sourceId === source.sourceId).progress;
  assert.equal(readingProgress.length, 3);
  assert.equal(library.completed, 3);
  assert.equal(library.total, 4);
  assert.equal(navigationCurrent.chunkId, 'chunk-004');
  return { cursor: navigationCurrent, readingRevision, completed: library.completed, total: library.total };
}

async function checkBattery(page, theme) {
  const progress = battery(page);
  await fullyVisible(progress);
  assert.equal(await progress.getAttribute('aria-valuenow'), '3');
  assert.equal(await progress.getAttribute('aria-valuemax'), '4');
  assert.match(await progress.getAttribute('aria-valuetext'), /3\/4 段 \(75%\)/);
  const body = progress.locator('.library-battery__outline');
  const fill = progress.locator('.library-battery__fill');
  const fillWidth = await fill.evaluate(node => node.getBoundingClientRect().width / node.offsetWidth);
  assert.ok(Math.abs(fillWidth - .75) < .02, `the battery should show 75%, measured ${fillWidth}`);
  return {
    label: minimum(await contrast(progress.locator('small')), 4.5, 'battery label'),
    outline: minimum(await contrast(body, 'border-top-color'), 3, 'battery outline against track'),
    fillBoundary: theme === 'dark'
      ? minimum(await contrast(fill, 'background-color', 'parent'), 3, 'battery fill against track')
      : minimum(await contrast(fill, 'border-top-color', 'parent'), 3, 'green fill border against track'),
    ...(theme === 'dark' ? {} : { fillInside: minimum(await contrast(fill, 'border-top-color'), 3, 'green fill against its border') }),
  };
}

async function checkAction(control, touch) {
  const page = control.page();
  await hitTarget(control);
  await page.mouse.move(1, 1);
  await motionSettled(control);
  const action = minimum(await contrast(control), 4.5, 'primary control');
  if (touch) return { action };
  await control.hover();
  await motionSettled(control);
  const hover = minimum(await contrast(control), 4.5, 'primary control hover');
  assert.notDeepEqual(hover.background, action.background);
  return { action, hover };
}

async function checkPdf(pane, card) {
  const target = pane.locator('[data-pdf-page="8"] .paper-region[data-active="true"]').first();
  const marker = target.getByRole('button', { name: '返回回答证据 4', exact: true });
  await marker.waitFor();
  await card.getByText(quote, { exact: true }).waitFor();
  await pane.locator('[data-pdf-page="8"] .paper-text span').first().waitFor({ state: 'attached' });
  await motionSettled(card);
  await target.evaluate(node => new Promise((resolve, reject) => {
    const pane = node.closest('[aria-label="文章原文"]');
    const deadline = performance.now() + 4000;
    function inspect() {
      const rect = node.getBoundingClientRect();
      const scroll = pane.getBoundingClientRect();
      if (rect.top >= scroll.top - 1 && rect.bottom <= scroll.bottom + 1) resolve();
      else if (performance.now() >= deadline) reject(new Error(`page 8 highlight clipped: ${JSON.stringify({ rect, scroll })}`));
      else requestAnimationFrame(inspect);
    }
    inspect();
  }));
  await hitTarget(marker);
  await fullyVisible(target);
  await fullyVisible(card);
  await hitTarget(card.getByRole('button', { name: '关闭证据' }));
  return {
    frame: minimum(await contrast(target, 'outline-color', 'paper'), 3, 'PDF highlight outline against the page'),
    number: minimum(await contrast(marker), 4.5, 'PDF return number'),
    quote: minimum(await contrast(card.getByText(quote, { exact: true })), 4.5, 'evidence quote'),
  };
}

async function reconnect(page) {
  await page.waitForFunction(() => window.themeEvents.snapshot > 0);
  const before = await page.evaluate(() => ({ ...window.themeEvents }));
  await page.evaluate(() => window.reconnectThemeEvents());
  await page.waitForFunction(before => window.themeEvents.error > before.error && window.themeEvents.open > before.open && window.themeEvents.snapshot > before.snapshot, before);
  return { before, after: await page.evaluate(() => ({ ...window.themeEvents })) };
}

const themes = ['blue', 'green', 'red', 'neutral', 'dark'];
const layouts = [
  { width: 1440, kind: 'desktop' },
  { width: 1024, kind: 'desktop' },
  { width: 720, kind: 'desktop' },
  { width: 720, kind: 'touch-system-reduced', hasTouch: true, reducedMotion: 'reduce' },
  { width: 1024, kind: 'app-reduced', appReducedMotion: true },
];

async function run(theme, { width, kind, hasTouch, reducedMotion, appReducedMotion }) {
  const { page, host, errors } = await open(theme, { viewport: { width, height: 1000 }, hasTouch, reducedMotion }, appReducedMotion);
  const take = async (locator) => hasTouch ? locator.tap() : locator.click();
  const before = await progress(host);
  const source = page.getByLabel('文章原文', { exact: true });
  const answer = citation(page);
  const card = page.getByLabel('原文证据', { exact: true });
  const fullscreen = page.getByRole('button', { name: '对话全屏', exact: true });
  const exit = page.getByRole('button', { name: '关闭全屏模式', exact: true });
  const mobileOriginal = page.getByRole('button', { name: '查看原文', exact: true });
  const mobileReturn = page.getByRole('button', { name: '返回对话', exact: true });
  const pdf = page.getByRole('button', { name: '原版 PDF', exact: true });
  const translation = page.getByRole('button', { name: '中文译文', exact: true });
  const stem = `${theme}-${width}-${kind}`;
  const result = { theme, width, kind, contrast: {}, screenshots: [] };

  async function save(name) {
    if (!artifacts) return;
    const file = `${stem}-${name}.png`;
    await screenshot(page, file);
    result.screenshots.push(file);
  }

  try {
    assert.deepEqual(await page.locator('html').evaluate(node => [node.dataset.theme, node.dataset.accent]),
      [theme === 'dark' ? 'dark' : 'light', theme === 'dark' ? 'red' : theme]);
    if (hasTouch) assert.ok(await page.evaluate(() => matchMedia('(pointer: coarse)').matches));
    if (reducedMotion) assert.ok(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches));
    if (appReducedMotion) {
      assert.equal(await page.locator('html').getAttribute('data-reduced-motion'), 'true');
      await take(page.getByRole('button', { name: '展开导航', exact: true }));
    }
    result.layout = width === 720 || appReducedMotion ? 'single pane' : 'two panes';
    assert.equal(await mobileOriginal.isVisible(), result.layout === 'single pane');

    const composer = page.getByRole('textbox', { name: '输入消息' });
    const send = page.getByRole('button', { name: '发送', exact: true });
    await composer.fill('配色验收');
    result.contrast.send = await checkAction(send, hasTouch);
    await composer.press('Tab');
    assert.ok(await send.evaluate(node => node.matches(':focus-visible') && getComputedStyle(node).outlineWidth === '2px'));
    result.contrast.keyboardFocus = minimum(await contrast(send, 'outline-color', 'parent'), 3, 'keyboard focus outline');
    await composer.fill('');

    await hitTarget(fullscreen);
    await take(fullscreen);
    await hitTarget(exit);
    const activeTab = page.getByRole('tab', { name: '对话', selected: true });
    result.contrast.activeTab = minimum(await contrast(activeTab), 4.5, 'active reading tab text');
    result.contrast.activeTabLine = minimum(await contrast(activeTab, 'border-bottom-color'), 3, 'active reading tab underline');
    assert.deepEqual(await progress(host), before, 'entering fullscreen must preserve close-reading progress');
    // Open the citation as soon as it is available, while the PDF may still be painting.
    await take(answer);
    await checkPdf(source, card);
    await take(exit);
    result.contrast.pdf = await checkPdf(source, card);
    assert.deepEqual(await progress(host), before, 'evidence navigation and exiting fullscreen must preserve progress');
    assert.equal(await pdf.getAttribute('aria-pressed'), 'true');
    if (kind === 'desktop' && width === 1440 || theme === 'green' && kind === 'app-reduced' || theme === 'blue' && hasTouch) {
      await save('pdf');
    }

    if (theme === 'blue' && appReducedMotion) {
      await take(mobileReturn);
      await take(fullscreen);
      await take(answer);
      await checkPdf(source, card);
      await source.press('Home');
      await page.waitForFunction(() => document.querySelector('[aria-label="文章原文"]').scrollTop === 0);
      await take(exit);
      await source.locator('[data-pdf-page="1"] .paper-text span').first().waitFor({ state: 'attached' });
      assert.equal(await source.evaluate(node => node.scrollTop), 0, 'exiting fullscreen must respect manual browsing');
      await take(mobileReturn);
      await take(answer);
      await checkPdf(source, card);
    }
    const pdfReturn = source.locator('[data-pdf-page="8"]').getByRole('button', { name: '返回回答证据 4', exact: true }).first();
    await take(pdfReturn);
    assert.ok(await answer.evaluate(node => node === document.activeElement), 'the PDF marker returns to citation 4');
    if (await mobileOriginal.isVisible()) await take(mobileOriginal);
    await take(translation);
    await source.locator('[data-translation-chunk]').first().waitFor();
    if (await mobileReturn.isVisible()) await take(mobileReturn);
    await take(answer);
    const translated = source.locator('section.is-active[data-evidence-block]').first();
    const translatedReturn = translated.getByRole('button', { name: '返回回答证据 4', exact: true });
    await card.getByRole('button', { name: /证据 4.*译块定位/ }).waitFor();
    assert.equal(await translation.getAttribute('aria-pressed'), 'true');
    await motionSettled(card);
    await hitTarget(translated.locator('p').first());
    await hitTarget(translatedReturn);
    result.contrast.translation = {
      frame: minimum(await contrast(translated, 'outline-color', 'parent'), 3, 'translation highlight outline'),
      number: minimum(await contrast(translatedReturn), 4.5, 'translation return number'),
    };
    if (reducedMotion || appReducedMotion) {
      assert.equal(await card.evaluate(node => getComputedStyle(node).animationName), 'none');
    }
    if (theme === 'dark' && hasTouch) await save('translation');
    await take(translatedReturn);
    assert.ok(await answer.evaluate(node => node === document.activeElement), 'the translation marker returns to citation 4');
    assert.deepEqual(await progress(host), before);

    if (await card.isVisible()) await take(card.getByRole('button', { name: '关闭证据' }));
    await composer.focus();
    result.sse = await reconnect(page);
    assert.ok(await composer.evaluate(node => node === document.activeElement), 'the fresh SSE snapshot preserves the current focus');
    assert.equal(await card.isVisible(), false);
    assert.deepEqual(await progress(host), before, 'SSE reconnection must preserve the Reading Cursor and read count');
    result.progress = before;

    await take(page.getByRole('link', { name: '知识库', exact: true }));
    result.contrast.battery = await checkBattery(page, theme);
    if (reducedMotion || appReducedMotion) {
      assert.equal(await battery(page).locator('.library-battery__fill').evaluate(node => getComputedStyle(node).transitionDuration), '0s');
    }
    const upload = page.getByRole('button', { name: '上传', exact: true });
    result.contrast.buttonText = await checkAction(upload, hasTouch);
    if (theme === 'green' && width === 1440 || theme === 'dark' && hasTouch) await save('library');

    await take(page.getByRole('link', { name: '设置', exact: true }));
    await page.getByLabel('界面密度', { exact: true }).selectOption('comfortable');
    const saved = page.getByRole('status').filter({ hasText: '已自动保存' });
    await fullyVisible(saved);
    result.contrast.success = minimum(await contrast(saved), 4.5, 'success status');
    if (theme === 'red' && width === 1440 || theme === 'dark' && hasTouch) await save('settings');

    await page.route('**/library/sources/*/document', route => route.fulfill({
      json: { ok: false, error: { code: 'unavailable', message: '源文档加载失败', retryable: true } },
    }));
    await page.goto(new URL('/reading', base).href);
    const error = page.getByRole('alert').filter({ hasText: '源文档加载失败' });
    await fullyVisible(error);
    await hitTarget(error.getByRole('button', { name: '重试', exact: true }));
    assert.match(await error.evaluate(node => getComputedStyle(node, '::before').content), /!/);
    result.contrast.error = minimum(await contrast(error), 4.5, 'error status');
    if (theme === 'red' && width === 1440 || theme === 'dark' && hasTouch) await save('error');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), width, 'the page must not overflow horizontally');
    assert.deepEqual(await progress(host), before);
    assert.deepEqual(errors, []);
    console.log(`PASS ${stem}`);
    return result;
  } catch (error) {
    console.error(`FAIL ${stem}\n${(await page.locator('body').innerText()).slice(-1400)}`);
    if (artifacts) await screenshot(page, `failed-${stem}.png`);
    throw error;
  } finally {
    await page.close();
  }
}

try {
  if (artifacts) await mkdir(artifacts, { recursive: true });
  await fixture();
  const rows = [];
  const failures = [];
  const selected = process.env.FOCUS_THEME_CASE;
  for (const theme of themes) {
    for (const layout of layouts) {
      const name = `${theme}-${layout.width}-${layout.kind}`;
      if (selected && selected !== name && selected !== theme) continue;
      try {
        rows.push(await run(theme, layout));
      } catch (error) {
        failures.push({ name, message: error.message });
        console.error(error);
      }
    }
  }
  assert.ok(rows.length || failures.length, 'FOCUS_THEME_CASE did not match a theme or matrix entry');
  const results = { chromium: browser.version(), rows, failures };
  if (artifacts) await writeFile(join(artifacts, 'results.json'), JSON.stringify(results, null, 2) + '\n');
  assert.equal(failures.length, 0, 'All formal Host theme combinations must pass');
  console.log(`PASS ${rows.length} formal Host theme combinations on Chromium ${results.chromium}`);
} finally {
  await browser.close();
}
