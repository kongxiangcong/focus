import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE,
  args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const base = `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}`;
const page = await browser.newPage({ viewport: { width: 1440, height: 844 }, reducedMotion: 'reduce' });
page.setDefaultTimeout(12000);
const modes = page.getByRole('group', { name: '阅读方式' });
const body = page.getByLabel('文章原文', { exact: true });
const manage = page.getByRole('button', { name: '管理来源', exact: true });
const dialog = page.getByRole('dialog').filter({ has: page.getByRole('heading', { name: '管理来源', exact: true }) });
const notes = page.getByRole('button', { name: '笔记', exact: true });

async function snapshot() {
  const binding = await (await page.request.get(`${base}/reader/workspace`)).json();
  const headers = { 'X-FOCUS-Instance': binding.value.workspace.instanceId };
  const result = await (await page.request.get(`${base}/reader/window`, { headers })).json();
  assert.ok(result.ok, JSON.stringify(result));
  return result.value;
}

async function chat() {
  const tab = modes.getByRole('button', { name: '对话', exact: true });
  await tab.waitFor();
  if (await tab.getAttribute('aria-pressed') !== 'true') await tab.click();
}

async function openRounds(numbers, selected) {
  await manage.click();
  const rounds = dialog.getByRole('list', { name: '阅读版本' });
  await rounds.getByText(`第 ${numbers.at(-1)} 轮`, { exact: true }).waitFor();
  assert.deepEqual(await rounds.locator('strong').allTextContents(), numbers.map(number => `第 ${number} 轮`));
  assert.equal(await rounds.locator('[aria-current="true"] strong').textContent(), `第 ${selected} 轮`);
  return rounds;
}

async function switchRound(rounds, to) {
  await rounds.getByRole('button', { name: `切换到第 ${to} 轮` }).click();
  await dialog.waitFor({ state: 'hidden' });
  await chat();
}

async function reread() {
  await page.getByRole('button', { name: '重新阅读', exact: true }).click();
  await page.getByRole('button', { name: '确认重新阅读', exact: true }).click();
}

async function editWholeNote(previous, content) {
  await notes.click();
  await page.locator('article').filter({ hasText: previous }).getByRole('button', { name: '编辑', exact: true }).click();
  await page.getByRole('textbox', { name: '笔记内容' }).fill(content);
  await page.getByRole('button', { name: '保存笔记', exact: true }).click();
  await page.getByText(content, { exact: true }).waitFor();
  await page.getByRole('button', { name: '关闭笔记', exact: true }).click();
}

const conversation = page.getByLabel('文章对话', { exact: true });
const secondAnswer = conversation.locator('[data-role="assistant"]').filter({ hasText: '第二轮的问题。' });
const roundOneTime = rounds => rounds.getByRole('listitem').first().locator('time');

try {
  await page.goto(`${base}/reading`);
  await chat();
  await body.getByText('阅读段落 17 用来核对阅读位置。', { exact: true }).waitFor();
  const first = await snapshot();
  await reread();
  await page.getByRole('main', { name: '阅读与对话', exact: true })
    .getByText('重读段落 1 用来核对阅读位置。', { exact: true }).waitFor();
  await chat();
  await body.getByText('重读段落 17 用来核对阅读位置。', { exact: true }).waitFor();
  const second = await snapshot();
  assert.equal(second.readingVersion, 2);
  assert.equal(second.navigationCurrent.chunkId, 'chunk-001');
  assert.notEqual(first.discussionId, second.discussionId);

  await editWholeNote('待复现', '已复现');
  await modes.getByRole('button', { name: '精读', exact: true }).click();
  await page.getByRole('button', { name: /继续/ }).click();
  await chat();
  await page.getByRole('textbox', { name: '输入消息' }).fill('第二轮的问题');
  await page.getByRole('button', { name: '发送', exact: true }).click();
  await secondAnswer.getByRole('button', { name: '1', exact: true }).waitFor();
  const secondSaved = await snapshot();
  assert.equal(secondSaved.navigationCurrent.chunkId, 'chunk-002');
  assert.ok(secondSaved.readingProgress.length);

  let rounds = await openRounds([1, 2], 2);
  assert.equal(await roundOneTime(rounds).count(), 1);
  const monday = await roundOneTime(rounds).getAttribute('datetime');
  await switchRound(rounds, 1);
  await body.getByText('阅读段落 17 用来核对阅读位置。', { exact: true }).waitFor();
  let view = await snapshot();
  assert.equal(view.discussionId, first.discussionId);
  assert.equal(view.navigationCurrent.chunkId, first.navigationCurrent.chunkId);
  assert.deepEqual(view.sourceNotes.map(note => note.content), ['待复现']);

  await editWholeNote('待复现', '周五补写的整篇笔记');
  await reread();
  await page.getByRole('main', { name: '阅读与对话', exact: true })
    .getByText('第三轮段落 1 用来核对阅读位置。', { exact: true }).waitFor();
  await chat();
  await body.getByText('第三轮段落 17 用来核对阅读位置。', { exact: true }).waitFor();
  view = await snapshot();
  assert.equal(view.readingVersion, 3);
  assert.equal(view.navigationCurrent.chunkId, 'chunk-001');
  assert.deepEqual(view.readingProgress, []);
  assert.deepEqual(view.conversation, []);
  assert.deepEqual(view.sourceNotes.map(note => note.content), ['周五补写的整篇笔记']);

  rounds = await openRounds([1, 2, 3], 3);
  assert.equal(await rounds.locator('time').count(), 1);
  assert.ok(Date.parse(await roundOneTime(rounds).getAttribute('datetime')) > Date.parse(monday));
  await switchRound(rounds, 2);
  await page.reload();
  await chat();
  await body.getByText('重读段落 17 用来核对阅读位置。', { exact: true }).waitFor();
  await secondAnswer.getByRole('button', { name: '1', exact: true }).click();
  await body.getByRole('button', { name: '返回回答证据 1', exact: true }).waitFor();
  view = await snapshot();
  assert.equal(view.discussionId, second.discussionId);
  assert.equal(view.navigationCurrent.chunkId, secondSaved.navigationCurrent.chunkId);
  assert.deepEqual(view.readingProgress, secondSaved.readingProgress);
  assert.deepEqual(view.sourceNotes.map(note => note.content), ['已复现']);
  console.log('PASS Workbench reread from round one, replace its backup time, and return to round two with progress and evidence');
} catch (error) {
  console.error((await page.locator('body').innerText()).slice(0, 1800));
  throw error;
} finally {
  await browser.close();
}
