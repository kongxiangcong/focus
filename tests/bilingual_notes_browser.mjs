import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const base = `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}`;
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
page.setDefaultTimeout(8000);
const modes = page.getByRole('group', { name: '阅读方式' });
const mode = name => modes.getByRole('button', { name, exact: true }).click();
const body = page.getByLabel('文章原文', { exact: true });
const languages = page.getByRole('group', { name: '正文语言' });
async function language(name) {
  await languages.getByRole('button', { name, exact: true }).click();
  await languages.getByRole('button', { name, exact: true, pressed: true }).waitFor();
}
const startNote = page.getByRole('button', { name: '记笔记', exact: true });
const drawer = page.getByRole('complementary', { name: '来源笔记' });
const content = drawer.getByRole('textbox', { name: '笔记内容' });
async function close() {
  await drawer.getByRole('button', { name: '关闭笔记', exact: true }).click();
  await drawer.waitFor({ state: 'hidden' });
}
const group = n => page.locator('[data-reading-group]').filter({ has: page.locator(`[data-chunk-key$="chunk-00${n}"]`) });
const notes = n => group(n).getByRole('region', { name: '小段笔记' });
const mark = (surface, kind = 'shared-note') =>
  surface.locator(`.reader-anno--${kind}`).evaluateAll(nodes => nodes.map(node => node.textContent).join(''));
const chunkNotes = n => body.getByRole('button', { name: new RegExp(`第 ${n} 段小段笔记`) });

async function expectMarks(surface, text, kind = 'shared-note') {
  await surface.locator(`.reader-anno--${kind}`).first().waitFor({ state: text ? 'attached' : 'detached' });
  assert.equal(await mark(surface, kind), text);
}

async function readingWindow() {
  const binding = await (await page.request.get(`${base}/reader/workspace`)).json();
  const headers = { 'X-FOCUS-Instance': binding.value.workspace.instanceId };
  const snapshot = await (await page.request.get(`${base}/reader/window`, { headers })).json();
  assert.ok(snapshot.ok, JSON.stringify(snapshot));
  return snapshot.value;
}

async function selectAcross(first, second) {
  await body.locator('strong').evaluate((strong, { first, second }) => {
    const paragraphs = [...strong.closest('[aria-label="文章原文"]').querySelectorAll('p')];
    const end = paragraphs.find(p => p.textContent.includes(second));
    const text = end.lastChild;
    const range = document.createRange();
    range.setStart(strong.firstChild, strong.textContent.indexOf(first));
    range.setEnd(text, text.textContent.indexOf(second) + second.length);
    window.getSelection().removeAllRanges();
    window.getSelection().addRange(range);
  }, { first, second });
  await startNote.click();
}

async function save(text) {
  await content.fill(text);
  await drawer.getByRole('button', { name: '保存笔记' }).click();
  await drawer.getByText(text, { exact: true }).waitFor();
  assert.equal(await drawer.getByText(text, { exact: true }).count(), 1);
}

try {
  await page.goto(`${base}/reading`);
  await mode('对话');
  await body.getByRole('heading', { name: '双语笔记' }).waitFor();
  const before = await readingWindow();
  await selectAcross('重复', '接着');
  await close();
  assert.equal(await mark(body), '');
  assert.equal((await readingWindow()).sourceNotes.length, 0);
  await selectAcross('重复', '接着');
  await save('这是一条跨段笔记');
  await close();
  await expectMarks(body, '重复😀接着');
  assert.equal((await readingWindow()).sourceNotes.length, 1);
  await page.reload();
  await expectMarks(body, '重复😀接着');

  await language('原文');
  await body.getByRole('heading', { name: 'Shared notes' }).waitFor();
  assert.equal(await mark(body), '');
  await chunkNotes(1).click();
  await drawer.getByText('这是一条跨段笔记', { exact: true }).waitFor();
  await close();
  await chunkNotes(2).click();
  await drawer.getByRole('button', { name: '编辑', exact: true }).click();
  await save('从原文修改的跨段笔记');
  await close();
  await language('中文');
  await expectMarks(body, '重复😀接着');
  await chunkNotes(2).click();
  await drawer.getByText('从原文修改的跨段笔记', { exact: true }).waitFor();
  await close();

  await mode('精读');
  await notes(1).getByText('从原文修改的跨段笔记', { exact: true }).waitFor();
  await notes(2).getByText('从原文修改的跨段笔记', { exact: true }).waitFor();
  assert.equal(await mark(group(1)), '重复😀');
  assert.equal(await mark(group(2)), '接着');
  await group(1).getByRole('button', { name: '查看原文' }).click();
  await group(2).getByRole('button', { name: '查看原文' }).click();
  assert.equal(await mark(group(1)), '');
  assert.equal(await mark(group(2)), '');
  assert.equal(await mark(group(1), 'hl'), 'repeat😀');
  await notes(2).getByRole('button', { name: '删除', exact: true }).click();
  await notes(1).getByText('从原文修改的跨段笔记', { exact: true }).waitFor({ state: 'detached' });
  await group(1).getByRole('button', { name: '查看译文' }).click();
  await group(2).getByRole('button', { name: '查看译文' }).click();
  assert.equal(await mark(group(1)), '');
  assert.equal(await mark(group(2)), '');
  await mode('对话');
  assert.equal(await mark(body), '');
  await language('原文');
  assert.equal(await chunkNotes(1).count(), 0);
  assert.equal(await chunkNotes(2).count(), 0);
  assert.equal(await mark(body, 'hl'), 'repeat😀');
  await page.getByRole('button', { name: '笔记', exact: true }).click();
  await drawer.getByRole('button', { name: '撤销删除', exact: true }).waitFor();
  assert.equal(await drawer.getByText('从原文修改的跨段笔记', { exact: true }).count(), 0);
  assert.equal(await drawer.getByRole('button', { name: '编辑', exact: true }).count(), 0);
  await close();

  await selectAcross('repeat', 'Then');
  await save('在原文选中文字');
  await close();
  await expectMarks(body, 'repeat😀\nThen');
  await expectMarks(body, 'repeat😀', 'hl');
  await language('中文');
  assert.equal(await mark(body), '');
  await chunkNotes(1).press('Enter');
  await drawer.getByText('在原文选中文字', { exact: true }).waitFor();
  await close();
  await mode('精读');
  await notes(1).getByText('在原文选中文字', { exact: true }).waitFor();
  await notes(2).getByText('在原文选中文字', { exact: true }).waitFor();
  assert.equal(await mark(group(1)), '');
  assert.equal(await mark(group(2)), '');
  await group(1).getByRole('button', { name: '查看原文' }).click();
  await group(2).getByRole('button', { name: '查看原文' }).click();
  assert.equal(await mark(group(1)), 'repeat😀');
  assert.equal(await mark(group(2)), 'Then');
  await notes(1).getByRole('button', { name: '删除', exact: true }).click();
  await notes(2).getByText('在原文选中文字', { exact: true }).waitFor({ state: 'detached' });
  assert.equal(await mark(group(1), 'hl'), 'repeat😀');
  const after = await readingWindow();
  assert.equal(after.navigationCurrent.chunkId, before.navigationCurrent.chunkId);
  assert.deepEqual(after.readingProgress, before.readingProgress);
  console.log('PASS bilingual Workbench selections, exact marks, shared editing and independent highlight');
} finally {
  await browser.close();
}
