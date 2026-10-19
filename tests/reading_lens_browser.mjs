import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const base = `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT || 8874}`;
const output = process.env.FOCUS_BROWSER_OUTPUT || '/tmp/focus-reader-redesign/shots/step4';
fs.mkdirSync(output, { recursive: true });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const windowValue = async () => (await (await page.request.get(`${base}/reader/window`)).json()).value;
const progress = value => ({ current: value.navigationCurrent, revision: value.readingRevision, records: value.readingProgress });
const selected = async () => Number(await page.locator('.reading-lens-group[data-state=focus]').getAttribute('data-lens-index'));
const scrollToGroup = async index => page.evaluate(index => {
  const pane = document.querySelector('.focus-stream');
  pane.dispatchEvent(new WheelEvent('wheel', { bubbles: true, deltaY: -1 }));
  const group = document.querySelector(`[data-lens-index="${index}"]`);
  pane.scrollTo({ top: pane.scrollTop + group.getBoundingClientRect().top - pane.getBoundingClientRect().top - pane.clientHeight * .32 + 40, behavior: 'instant' });
}, index);
try {
  await page.goto(`${base}/reading`);
  await page.getByRole('button', { name: '进入正文', exact: true }).click();
  await page.waitForSelector('.reading-lens-group[data-state=focus]');
  for (let i = 2; i <= 5; i++) {
    await page.getByRole('button', { name: '继续', exact: true }).click();
    await page.waitForFunction(i => document.querySelector('.reading-lens-group[data-state=focus]')?.dataset.lensIndex === String(i), i);
  }
  await page.waitForTimeout(1000);
  if (await page.locator('.reader-left-drawer').getAttribute('data-open') === 'true') await page.getByRole('button', { name: '关闭阅读侧栏' }).click();
  const before = progress(await windowValue());
  await page.evaluate(() => {
    window.lensCommits = [];
    new MutationObserver(records => {
      for (const record of records) if (record.attributeName === 'data-lens-active') window.lensCommits.push(record.target.getAttribute('data-lens-active'));
    }).observe(document.querySelector('.reading-lens'), { attributes: true });
  });
  await scrollToGroup(1); await page.waitForTimeout(220);
  assert.equal(await selected(), 1);
  await scrollToGroup(2); await page.waitForTimeout(55);
  await scrollToGroup(3); await page.waitForTimeout(220);
  assert.equal(await selected(), 3);
  await scrollToGroup(2); await page.waitForTimeout(220);
  assert.equal(await selected(), 2);
  const commits = await page.evaluate(() => window.lensCommits);
  assert.equal(commits.length, 3, JSON.stringify(commits));
  assert.equal(new Set(commits).size, 3);
  const beforeHover = await page.locator('.reading-lens').getAttribute('data-lens-active');
  await page.locator('.reading-lens-group').first().dispatchEvent('mouseover');
  await page.mouse.move(550, 160);
  await page.waitForTimeout(200);
  assert.equal(await page.locator('.reading-lens').getAttribute('data-lens-active'), beforeHover);
  assert.equal((await page.evaluate(() => window.lensCommits)).length, 3);
  assert.deepEqual(progress(await windowValue()), before);
  assert.match(await page.getByRole('button', { name: '当前阅读位置' }).innerText(), /回看 2 · 进度 5\/9/);
  assert.equal(await page.locator('.reading-lens').getAttribute('data-review'), 'true');
  await page.waitForTimeout(420);
  const inkStates = await page.evaluate(() => ['focus', 'near', 'far'].map(state => {
    const group = document.querySelector(`.reading-lens-group[data-state="${state}"]`);
    return { group: getComputedStyle(group).color, text: getComputedStyle(group.querySelector('.focus-markdown')).color, opacity: getComputedStyle(group).opacity };
  }));
  assert.equal(new Set(inkStates.map(state => state.text)).size, 3);
  inkStates.forEach(state => { assert.equal(state.group, state.text); assert.equal(state.opacity, '1'); });
  const geometry = await page.evaluate(() => {
    const lens = document.querySelector('.reading-lens').getBoundingClientRect();
    const group = document.querySelector('.reading-lens-group[data-state=focus]').getBoundingClientRect();
    return [group.left - lens.left, lens.right - group.right, group.top - lens.top, lens.bottom - group.bottom];
  });
  geometry.forEach((value, index) => assert.ok(Math.abs(value - (index < 2 ? 30 : 18)) < 1, JSON.stringify(geometry)));
  for (const width of [1440, 1024, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await scrollToGroup(2);
    for (const theme of ['light', 'dark']) {
      await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
      await page.waitForTimeout(450);
      await page.screenshot({ path: `${output}/${width}-${theme}.png` });
    }
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: '回到进度', exact: true }).click();
  assert.equal(await selected(), 5);
  assert.deepEqual(progress(await windowValue()), before);
  await page.waitForTimeout(750);
  await scrollToGroup(2); await page.waitForTimeout(220);
  // Viewing old text is purely visual: Continue still advances the Host frontier to 6.
  await page.getByRole('button', { name: '继续', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('.reading-lens-group[data-state=focus]')?.dataset.lensIndex === '6');
  await page.waitForTimeout(1000);
  assert.equal(await selected(), 6);
  assert.equal((await windowValue()).navigationCurrent.index, 6);
  const landingError = await page.evaluate(() => {
    const pane = document.querySelector('.focus-stream');
    return document.querySelector('.reading-lens-group[data-state=focus]').getBoundingClientRect().top - pane.getBoundingClientRect().top - Math.max(24, pane.clientHeight * .1);
  });
  assert.ok(Math.abs(landingError) < 2, `start-line error: ${landingError}`);
  for (const mode of ['user', 'system']) {
    await page.evaluate(mode => { document.documentElement.dataset.reducedMotion = String(mode === 'user'); }, mode);
    await page.emulateMedia({ reducedMotion: mode === 'system' ? 'reduce' : 'no-preference' });
    assert.equal(await page.locator('.reading-lens').evaluate(el => getComputedStyle(el).transitionDuration), '0s');
    await page.screenshot({ path: `${output}/reduced-${mode}.png` });
  }
  assert.deepEqual(errors, []);
  console.log('PASS: 3 dwell stops = 3 commits; skipped transient paragraph; hover unchanged; Host progress unchanged during review; Continue opens/focuses 6; exact lens geometry; reduced motion; 8 screenshots.');
} finally { await browser.close(); }
