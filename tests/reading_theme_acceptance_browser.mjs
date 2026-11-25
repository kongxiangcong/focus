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

async function fixture(targetCompleted) {
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
    for (let completed = read; completed < targetCompleted; completed++) {
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

async function checkMidBattery(theme) {
  const { page, host } = await open(theme);
  try {
    const { source, readingProgress } = await host('/reader/window');
    assert.equal(readingProgress.length, 2);
    await page.getByRole('link', { name: '知识库', exact: true }).click();
    const row = page.getByRole('listitem').and(page.locator(`[data-source-id=${JSON.stringify(source.sourceId)}]`));
    const progress = row.getByRole('progressbar');
    await fullyVisible(progress);
    assert.match(await progress.getAttribute('aria-valuetext'), /2\/4 段 \(50%\)/);
    const fill = progress.locator('.library-battery__fill');
    const fillWidth = await fill.evaluate(node => node.getBoundingClientRect().width / node.offsetWidth);
    assert.ok(Math.abs(fillWidth - .5) < .02, `the mid battery should show 50%, measured ${fillWidth}`);
    const measure = async state => {
      assert.equal(await fill.evaluate(node => getComputedStyle(node).borderTopWidth), '1px');
      return {
        boundary: minimum(await contrast(fill, 'border-top-color', 'parent'), 3, `${theme} ${state} mid battery boundary against its track`),
        ...(theme === 'dark' ? {} : { interior: minimum(await contrast(fill, 'border-top-color'), 3, `${theme} ${state} amber fill against its border`) }),
      };
    };
    await page.mouse.move(1, 1);
    const resting = await measure('resting');
    await row.hover();
    const hover = await measure('hovered');
    await row.locator('h3').click();
    assert.equal(await row.getAttribute('data-selected'), 'true');
    const selected = await measure('selected');
    if (theme !== 'dark') assert.notDeepEqual(selected.boundary.background, hover.boundary.background);
    return { theme, resting, hover, selected };
  } finally {
    await page.close();
  }
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

async function checkStatus(status, glyph, tone) {
  await fullyVisible(status);
  const icon = status.locator(':scope > [aria-hidden="true"]');
  assert.equal(await icon.innerText(), glyph);
  assert.ok(await icon.isVisible());
  await status.evaluate((node, tone) => {
    const style = getComputedStyle(node);
    const reference = document.createElement('span');
    reference.style.color = `var(--reader-${tone}-line)`;
    node.append(reference);
    const border = getComputedStyle(reference).color;
    reference.remove();
    if (style.borderTopWidth !== '1px' || style.borderTopColor !== border) {
      throw new Error(`Expected a 1px ${tone} border, got ${style.borderTopWidth} ${style.borderTopColor}`);
    }
  }, tone);
  return minimum(await contrast(status), 4.5, `${tone} status`);
}

async function checkSourceEvidence(pane, id, translated = false) {
  const evidence = pane.locator(translated
    ? `[data-evidence-block~="${id}"].is-active`
    : `mark[data-evidence-ids~="${id}"].is-active`);
  const target = evidence.first();
  await target.waitFor();
  await motionSettled(target);
  const marker = pane.getByRole('button', { name: '返回回答证据 4', exact: true }).first();
  await marker.waitFor();
  if (translated) {
    await pane.page().waitForFunction(id => {
      const pane = document.querySelector('[aria-label="文章原文"]');
      const group = pane.querySelector(`[data-evidence-block~="${id}"].is-active`);
      const y = group?.getBoundingClientRect().top;
      const bounds = pane.getBoundingClientRect();
      return y >= bounds.top && y < bounds.bottom && getComputedStyle(group).boxShadow !== 'none';
    }, id);
  } else {
    assert.equal((await evidence.allTextContents()).join(''), quote);
    await fullyVisible(target);
  }
  return {
    number: minimum(await contrast(marker), 4.5, 'source evidence return number'),
    quote: minimum(await contrast(target), 4.5, 'source evidence text'),
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
  const fullscreen = page.getByRole('button', { name: '对话全屏', exact: true });
  const exit = page.getByRole('button', { name: '关闭全屏模式', exact: true });
  const mobileOriginal = page.getByRole('button', { name: '查看正文', exact: true });
  const mobileReturn = page.getByRole('button', { name: '返回对话', exact: true });
  const original = page.getByRole('button', { name: '原文', exact: true });
  const translation = page.getByRole('button', { name: '中文', exact: true });
  const originalLink = page.getByRole('link', { name: '打开原件 ↗', exact: true });
  const returnNumber = source.getByRole('button', { name: '返回回答证据 4', exact: true }).first();
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
    const evidenceId = await answer.getAttribute('data-citation');
    if (await mobileOriginal.isVisible()) await take(mobileOriginal);
    await take(original);
    if (await mobileReturn.isVisible()) await take(mobileReturn);
    await take(answer);
    await checkSourceEvidence(source, evidenceId);
    await take(exit);
    result.contrast.source = await checkSourceEvidence(source, evidenceId);
    assert.deepEqual(await progress(host), before, 'evidence navigation and exiting fullscreen must preserve progress');
    assert.equal(await original.getAttribute('aria-pressed'), 'true');
    assert.ok((await originalLink.getAttribute('href')).endsWith('#page=8'));
    if (kind === 'desktop' && width === 1440 || theme === 'green' && kind === 'app-reduced' || theme === 'blue' && hasTouch) {
      await save('source');
    }

    if (theme === 'blue' && appReducedMotion) {
      await take(mobileReturn);
      await take(fullscreen);
      await take(answer);
      await checkSourceEvidence(source, evidenceId);
      await source.press('Home');
      await page.waitForFunction(() => document.querySelector('[aria-label="文章原文"]').scrollTop === 0);
      await take(exit);
      assert.equal(await source.evaluate(node => node.scrollTop), 0, 'exiting fullscreen must respect manual browsing');
      await take(mobileReturn);
      await take(answer);
      await checkSourceEvidence(source, evidenceId);
    }
    await take(returnNumber);
    assert.ok(await answer.evaluate(node => node === document.activeElement), 'the source marker returns to citation 4');
    if (await mobileOriginal.isVisible()) await take(mobileOriginal);
    await take(translation);
    if (await mobileReturn.isVisible()) await take(mobileReturn);
    await take(answer);
    result.contrast.translation = await checkSourceEvidence(source, evidenceId, true);
    assert.equal(await translation.getAttribute('aria-pressed'), 'true');
    if (theme === 'dark' && hasTouch) await save('translation');
    await take(returnNumber);
    assert.ok(await answer.evaluate(node => node === document.activeElement), 'the translation marker returns to citation 4');
    assert.deepEqual(await progress(host), before);

    await composer.focus();
    result.sse = await reconnect(page);
    assert.ok(await composer.evaluate(node => node === document.activeElement), 'the fresh SSE snapshot preserves the current focus');
    assert.equal(await page.getByLabel('原文证据', { exact: true }).count(), 0);
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
    await page.evaluate(() => document.fonts.ready);
    await page.getByLabel('界面密度', { exact: true }).selectOption('comfortable');
    const saved = page.getByRole('status').filter({ hasText: '已自动保存' });
    result.contrast.success = await checkStatus(saved, '✓', 'success');
    if (theme === 'red' && width === 1440 || theme === 'dark' && hasTouch) await save('settings');
    const preview = page.getByLabel('界面配色预览');
    result.contrast.previewSuccess = await checkStatus(preview.locator('[data-workspace-status="success"]'), '✓', 'success');
    result.contrast.previewError = await checkStatus(preview.locator('[data-workspace-status="danger"]'), '!', 'danger');
    const revertStorage = await page.evaluateHandle(() => {
      const save = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key, value) {
        if (key === 'focus.density') throw new DOMException('Read only', 'SecurityError');
        return save.call(this, key, value);
      };
      return () => { Storage.prototype.setItem = save; };
    });
    await page.getByLabel('界面密度', { exact: true }).selectOption('compact');
    result.contrast.storageError = await checkStatus(page.getByRole('alert').filter({ hasText: '外观保存失败' }), '!', 'danger');
    await revertStorage.evaluate(revert => revert());
    await revertStorage.dispose();

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
  await fixture(2);
  const midBattery = [];
  for (const theme of themes) {
    if (!process.env.FOCUS_THEME_CASE || process.env.FOCUS_THEME_CASE.startsWith(theme)) {
      midBattery.push(await checkMidBattery(theme));
    }
  }
  await fixture(3);
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
  const results = { chromium: browser.version(), midBattery, rows, failures };
  if (artifacts) await writeFile(join(artifacts, 'results.json'), JSON.stringify(results, null, 2) + '\n');
  assert.equal(failures.length, 0, 'All formal Host theme combinations must pass');
  console.log(`PASS ${rows.length} formal Host theme combinations on Chromium ${results.chromium}`);
} finally {
  await browser.close();
}
