import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const output = process.env.FOCUS_BROWSER_OUTPUT || 'tmp/focus-reader-redesign/shots/step3';
fs.mkdirSync(output, { recursive: true });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
const url = `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT || 8873}/reading`;
const sample = locator => locator.evaluate(el => {
  const css = getComputedStyle(el);
  return { opacity: Number(css.opacity), transform: css.transform, visibility: css.visibility, height: el.getBoundingClientRect().height, animation: css.animationName };
});
const drawer = page.locator('.reader-left-drawer');
const toggle = page.getByRole('button', { name: '资料', exact: true });
try {
  await page.goto(url);
  await page.getByRole('button', { name: '进入正文', exact: true }).click();
  await page.waitForSelector('.focus-output[data-fresh=true]');
  await page.waitForFunction(()=>document.querySelector('.focus-output[data-fresh=true]')?.dataset.entered === 'true');
  assert.equal(await page.locator('.focus-output[data-fresh=true]').first().getAttribute('data-entered'), 'true');
  if (await drawer.getAttribute('data-open') === 'true') await drawer.getByRole('button', { name: '关闭阅读侧栏' }).click();
  await page.waitForTimeout(250);
  const width = await page.locator('.focus-content').evaluate(el => el.getBoundingClientRect().width);
  // ADR 0028: single-row pill and borderless function-row geometry.
  const dockGeometry = await page.locator('.focus-composer').evaluate(form => {
    const textarea = form.querySelector('#focus-question').getBoundingClientRect();
    const send = form.querySelector('.focus-composer__send').getBoundingClientRect();
    return {
      height: form.getBoundingClientRect().height,
      radius: getComputedStyle(form).borderTopLeftRadius,
      centerDelta: Math.abs((send.top + send.bottom) / 2 - (textarea.top + textarea.bottom) / 2),
      sendLeft: send.left, textareaRight: textarea.right,
      ghostBorders: [...document.querySelectorAll('.mist-reading-actions button:not(.focus-reader__continue)')]
        .map(button => getComputedStyle(button).borderTopWidth),
    };
  });
  assert.ok(Math.abs(dockGeometry.height - 52) <= 1, JSON.stringify(dockGeometry));
  assert.equal(dockGeometry.radius, '26px');
  assert.ok(dockGeometry.centerDelta <= 1, JSON.stringify(dockGeometry));
  assert.ok(dockGeometry.sendLeft >= dockGeometry.textareaRight - 1, JSON.stringify(dockGeometry));
  assert.ok(dockGeometry.ghostBorders.every(border => border === '0px'), JSON.stringify(dockGeometry));

  // DOM clicks avoid Playwright's stability waiting, exercising genuine mid-frame reversals.
  for (let i = 0; i < 3; i++) {
    const { opening, reversing } = await toggle.evaluate(el => new Promise((resolve, reject) => {
      const pane = document.querySelector('.reader-left-drawer');
      const read = () => { const css = getComputedStyle(pane); return { opacity:Number(css.opacity), transform:css.transform, visibility:css.visibility }; };
      const started = performance.now(); el.click();
      function frame() {
        const opening = read();
        if (opening.opacity > 0 && opening.opacity < 1) {
          pane.querySelector('.reader-side-close').click(); resolve({opening, reversing:read()});
        } else if (performance.now()-started > 2000) reject(new Error('No intermediate drawer frame: '+JSON.stringify(opening)));
        else requestAnimationFrame(frame);
      }
      requestAnimationFrame(frame);
    }));
    assert.ok(opening.opacity > 0 && opening.opacity < 1, JSON.stringify(opening));
    assert.equal(reversing.visibility, 'visible');
    assert.ok(Math.abs(opening.opacity - reversing.opacity) < .35);
    assert.equal(await page.locator('.focus-content').evaluate(el => el.getBoundingClientRect().width), width);
    await page.waitForTimeout(40);
  }
  await page.waitForTimeout(250);
  assert.equal(await drawer.getAttribute('data-open'), 'false');
  assert.equal((await sample(drawer)).visibility, 'hidden');
  await toggle.click();
  await page.waitForTimeout(280);
  assert.equal((await sample(drawer)).opacity, 1);
  assert.equal(await page.locator('.focus-content').evaluate(el => el.getBoundingClientRect().width), width);
  await drawer.getByRole('button', { name: '关闭阅读侧栏' }).click();
  const editor = page.getByRole('textbox', { name: '输入问题或阅读需求' });
  await editor.fill('动效测试保留的草稿');
  const disclosure = page.locator('.mist-reading-actions .mist-composer-toggle');
  const disclosureLeft = await disclosure.evaluate(el => el.getBoundingClientRect().left);
  await page.getByRole('button', { name: '收起', exact: true }).click();
  await page.waitForTimeout(280);
  assert.equal((await sample(page.locator('.focus-composer-collapse'))).height, 0);
  assert.ok(Math.abs(await disclosure.evaluate(el => el.getBoundingClientRect().left) - disclosureLeft) <= 1, 'collapse must not move the disclosure');
  await page.getByRole('button', { name: '提问', exact: true }).click();
  await page.waitForTimeout(280);
  assert.equal(await editor.inputValue(), '动效测试保留的草稿');
  assert.ok(Math.abs(await disclosure.evaluate(el => el.getBoundingClientRect().left) - disclosureLeft) <= 1, 'expand must not move the disclosure');
  await page.getByRole('button', { name: '当前阅读位置' }).click();
  await page.waitForTimeout(280);
  await page.locator('.focus-dialog').getByRole('button', { name: '关闭', exact: true }).click();
  const dialogExit = await sample(page.locator('.focus-dialog'));
  assert.ok(dialogExit.opacity > 0, 'dialog must retain its exit frame');
  await page.waitForTimeout(220);
  await page.reload();
  await page.waitForSelector('.focus-output');
  assert.equal(await page.locator('.focus-output[data-fresh=true]').count(), 0);
  assert.equal((await sample(page.locator('.focus-output').first())).animation, 'none');
  // User preference is saved through the actual settings UI and survives reload.
  await page.getByRole('link', { name: '设置', exact: true }).click();
  await page.getByRole('checkbox', { name: '低动态', exact: true }).check();
  await page.getByRole('button', { name: '保存外观', exact: true }).click();
  await page.getByRole('link', { name: '阅读', exact: true }).click();
  await page.reload();
  assert.equal(await page.locator('html').getAttribute('data-reduced-motion'), 'true');
  for (const mode of ['user', 'system']) {
    if (mode === 'system') {
      await page.evaluate(() => { localStorage.setItem('focus.reducedMotion', 'false'); });
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.reload();
    }
    await page.waitForSelector('.focus-output');
    if (await drawer.getAttribute('data-open') === 'true') await drawer.getByRole('button', { name: '关闭阅读侧栏' }).click();
    await page.waitForTimeout(160);
    await toggle.evaluate(el => el.click());
    await page.waitForTimeout(35);
    assert.equal((await sample(drawer)).transform, 'none');
    await page.getByRole('button', { name: '当前阅读位置' }).click();
    assert.equal((await sample(page.locator('.focus-dialog'))).transform, 'none');
    await page.locator('.focus-dialog').getByRole('button', { name: '关闭', exact: true }).click();
    await page.waitForTimeout(160);
    await page.getByRole('button', { name: '继续', exact: true }).click();
    await page.waitForSelector('.focus-output[data-fresh=true]');
    assert.equal((await sample(page.locator('.focus-output').last())).transform, 'none');
    if (process.env.FOCUS_BROWSER_CAPTURE !== '0') await page.screenshot({ path: `${output}/reduced-${mode}.png` });
  }
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const theme of ['light', 'dark']) {
      await page.evaluate(value => { document.documentElement.dataset.theme = value; }, theme);
      await page.waitForTimeout(300);
      if (process.env.FOCUS_BROWSER_CAPTURE !== '0') await page.screenshot({ path: `${output}/${width}-${theme}.png` });
    }
  }
  assert.deepEqual(errors, []);
  console.log('PASS: 3 drawer reversals, stable body width, composer draft/height, dialog exit, restored history, user/system reduced motion, dock geometry, optional captures.');
} finally { await browser.close(); }
