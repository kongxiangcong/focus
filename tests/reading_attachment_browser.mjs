/** FocusReader geometry/interaction regression against `pnpm reader:dev` (port 5173).
 * Set FOCUS_PLAYWRIGHT_MODULE and FOCUS_CHROMIUM_EXECUTABLE; optional FOCUS_BROWSER_PORT/OUTPUT.
 * Uses synthetic Source anchors and a reserved workbench sidebar; no model or private workspace calls.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.FOCUS_PLAYWRIGHT_MODULE);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const browserRoot = `/@fs/${root.replaceAll('\\', '/')}`;
const tempRoot = path.join(root, 'ui/apps/standalone/tmp');
fs.mkdirSync(tempRoot, { recursive: true });
const fixture = fs.mkdtempSync(path.join(tempRoot, 'attached-notes-'));
const out = process.env.FOCUS_BROWSER_OUTPUT || '/tmp/focus-attached-notes';
fs.mkdirSync(out, { recursive: true });
const chunks = [1, 2].map(index => ({ sourceId: 'demo', planId: 'plan', chunkId: `chunk-${index}`, index, total: 3,
  bundleVersion: 'v1', sourceLines: [index * 10, index * 10 + 9], sectionPath: ['体系结构', index === 1 ? '存储与计算' : '调度与映射'],
  sourceMarkdown: Array.from({ length: 12 }, (_, i) => `段落 ${index}.${i + 1}：在阅读这一节时，重点关注数据如何在存储层次之间移动，以及计算单元如何复用数据。局部缓存减少重复传输，调度策略决定资源之间的协作方式。`).join('\n\n'),
  translation: null, images: [], relevantGlossary: [], presentationStatus: 'source-ready' }));
const notes = chunks.map((chunk, index) => ({ noteId: `note-${index + 1}`, sourceId: 'demo', revision: 1, content: index === 0
  ? '**对应第一段的笔记**\n\n' + Array.from({ length: 12 }, (_, i) => `${i + 1}. 数据复用的收益取决于局部存储容量，需要结合访存量与计算量一起判断。`).join('\n\n')
  : '**对应第二段的笔记**\n\n映射策略需要同时考虑并行度和数据搬运成本。\n\n- 空间映射\n- 时间复用',
  kind: 'thought', origin: 'user', evidenceRole: 'explanation', bundle: 'v1',
  anchor: { sourceId: 'demo', bundle: 'v1', sourceLines: chunk.sourceLines }, referenceStatus: 'current', sourceUpdated: false, deleted: false, canUndo: false }));
for (const [index, paragraph] of [0, 3].entries()) {
 const exact=chunks[0].sourceMarkdown.split('\n\n')[paragraph].split('。')[0]+'。';
 notes.push({...notes[0],noteId:`sentence-${index}`,content:`句子备注卡片 ${index+1}`,sentence:{planId:'plan',chunkId:'chunk-1',layer:'source',range:{start:0,end:exact.length},quote:{exact,prefix:'',suffix:''}}});
}
const view = { status: 'reading', source: { sourceId: 'demo', title: '架构阅读示例', topicId: null }, sessionId: 's1',
  current: chunks[1], navigationCurrent: chunks[1], history: [chunks[0]], sourceNotes: notes,
  conversation: [{ messageId: 'm1', role: 'assistant', content: '这是一条仍留在阅读流中的讨论回复。', chunkId: chunks[0].chunkId,
    reference: { sourceId: 'demo', planId: 'plan', chunkId: chunks[0].chunkId } }],
  timeline: [...chunks.map(chunk => ({ kind: 'reading', chunk })), { kind: 'message', messageId: 'm1' }] };
fs.writeFileSync(path.join(fixture, 'index.html'), '<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>段落笔记验证</title><link rel="icon" href="data:,"><div id="root"></div><script type="module" src="./main.tsx"></script></html>');
fs.writeFileSync(path.join(fixture, 'main.tsx'), `
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { FocusReader } from '${browserRoot}/ui/packages/reader-ui/src/FocusReader.tsx';
import '${browserRoot}/ui/packages/reader-ui/src/focus-tokens.css';
const view = ${JSON.stringify(view)};
window.notesCalls = [];
const host = { getReadingWindow: async () => ({ok:true,value:view}),
  sendMessage: async input => { window.notesCalls.push(input); return {ok:true,value:view}; },
  continueReading: async () => { throw new Error('Unexpected cursor change'); } };
function Fixture() {
 const [fullscreen, setFullscreen] = useState(false);
 return <><style>{'html,body,#root{margin:0;height:100%;}body{background:#eceae4}.fixture-nav{position:absolute;left:24px;top:24px;font:14px system-ui;color:#777}.fixture-reader{height:100%;margin-left:248px}.fixture-reader[data-fullscreen=true]{margin-left:0}@media(max-width:720px){.fixture-reader{margin-left:0}.fixture-nav{display:none}}'}</style>
 {!fullscreen && <div className="fixture-nav">FOCUS · 阅读工作台</div>}
 <div className="fixture-reader" data-fullscreen={fullscreen}><FocusReader host={host} appearance="mist" fullscreen={fullscreen} onFullscreenChange={setFullscreen}/></div></>;
}
createRoot(document.getElementById('root')).render(<Fixture/>);
`);
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [], metrics = {};
page.on('pageerror', e => errors.push(e.message));
page.on('response', response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
const settle = () => page.waitForTimeout(400);
const toggle = page.getByRole('navigation', { name: '阅读功能控制区' }).getByRole('button', { name: '笔记', exact: true });
const layout = () => page.locator('.focus-reader').getAttribute('data-notes-layout');
const geometry = () => page.locator('[data-lens-index="2"] .reading-group-passage').evaluate(e => {
 const source = e.querySelector('.reading-group-source'), notes = e.querySelector('.reader-anno-rail');
 return { passage: e.getBoundingClientRect().width, source: source.getBoundingClientRect().width,
   text: source.querySelector('.focus-markdown').getBoundingClientRect().width, notes: notes?.getBoundingClientRect().width,
   stacked:notes?.dataset.annoRail==='stacked',notesTop:notes?.getBoundingClientRect().top,sourceBottom:source.getBoundingClientRect().bottom };
});
try {
 await page.goto(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT || 5173}/tmp/${path.basename(fixture)}/index.html`);
 await page.getByRole('complementary', { name: '第 2 段笔记', exact: true }).waitFor(); await settle();
 assert.equal(await layout(), 'side');
 metrics.side = await geometry();
 assert.equal(metrics.side.text, 756);
 assert.equal(metrics.side.notes, 280);
 await toggle.click(); await settle();
 assert.equal(await layout(), 'off'); assert.equal((await geometry()).text, metrics.side.text);
 await toggle.click(); await settle();
 await page.setViewportSize({ width: 1280, height: 900 }); await settle();
 assert.equal(await layout(), 'split'); metrics.split = await geometry();
 if(metrics.split.stacked) {
  assert.ok(Math.abs(metrics.split.notes-metrics.split.passage)<1,JSON.stringify(metrics.split));
  assert.ok(metrics.split.notesTop>=metrics.split.sourceBottom-1,JSON.stringify(metrics.split));
 } else assert.ok(Math.abs(metrics.split.notes / metrics.split.passage - .25) < .001,JSON.stringify(metrics.split));
 await page.getByRole('button', { name: '全屏', exact: true }).click(); await settle();
 assert.equal(await layout(), 'side');
 await page.getByRole('button', { name: '退出全屏', exact: true }).click(); await settle();
 assert.equal(await layout(), 'split');
 // Reflow preserves the same visible source paragraph when notes are toggled.
 const anchor = page.locator('[data-lens-index="2"] .reading-group-source .focus-markdown > p').nth(3);
 await anchor.evaluate(e => { const pane=document.querySelector('.focus-stream'); pane.dispatchEvent(new WheelEvent('wheel',{bubbles:true,deltaY:-100})); pane.scrollTop+=e.getBoundingClientRect().top-pane.getBoundingClientRect().top-pane.clientHeight*.1; }); await settle();
 const anchorTop = await anchor.evaluate(e=>e.getBoundingClientRect().top);
 await toggle.click(); await settle();
 assert.ok(Math.abs(await anchor.evaluate(e=>e.getBoundingClientRect().top)-anchorTop)<2);
 await toggle.click(); await settle();
 assert.ok(Math.abs(await anchor.evaluate(e=>e.getBoundingClientRect().top)-anchorTop)<2);
 await page.getByRole('button', { name: '收起', exact: true }).click();
 const firstNotes = page.getByRole('complementary', { name: '第 1 段笔记', exact: true });
 await firstNotes.getByRole('button', { name: '就这段讨论', exact: true }).click(); await settle();
 assert.match(await page.locator('.focus-reference').innerText(), /引用第 1 段/);
 assert.equal(await page.locator('#focus-question').evaluate(e => e === document.activeElement), true);
 await page.locator('#focus-question').fill('解释第一段的数据复用');
 await page.getByRole('button', { name: '发送', exact: true }).click(); await settle();
 assert.equal(await page.evaluate(() => window.notesCalls[0].receipt.chunkId), 'chunk-1');
 assert.match(await page.locator('[data-lens-index="2"] .reading-group-discussion').innerText(), /仍留在阅读流/);
 assert.equal(await firstNotes.getByText('仍留在阅读流中的讨论回复。').count(), 0);
 metrics.longNotes = await firstNotes.evaluate(e => {
  const source=e.closest('.reading-group-passage').querySelector('.reading-group-source').getBoundingClientRect();
  const foot=e.querySelector('.reader-chunk-notes').getBoundingClientRect();
  const cards=[...e.querySelectorAll('[data-anno-card]')].map(card=>card.getBoundingClientRect());
  return {sourceBottom:source.bottom,footTop:foot.top,lastCardBottom:Math.max(...cards.map(card=>card.bottom))};
 });
 assert.ok(metrics.longNotes.footTop>=metrics.longNotes.sourceBottom-1);
 assert.ok(metrics.longNotes.footTop>=metrics.longNotes.lastCardBottom-1);
 assert.equal(await firstNotes.locator('[data-anno-card]').count(),2);
 for (const [width, height] of [[1600,1000], [1440,900], [1280,800], [1024,768], [720,900], [390,844]]) {
  await page.setViewportSize({ width, height }); await settle();
  await page.locator('.focus-stream').evaluate(e => { e.dispatchEvent(new WheelEvent('wheel', {bubbles:true,deltaY:-100})); e.scrollTop = 100; e.dispatchEvent(new Event('scroll', {bubbles:true})); }); await settle();
  const dock = page.getByRole('navigation', { name: '阅读功能控制区' });
  await dock.getByRole('button', { name: /^回到最新/ }).waitFor();
  const bounds = await dock.evaluate(e => {
   const main = document.querySelector('.focus-stream').getBoundingClientRect();
   return { top: e.getBoundingClientRect().top, mainBottom: main.bottom, width: e.clientWidth, scrollWidth: e.scrollWidth,
    buttonsFit: [...e.querySelectorAll('button')].every(b => { const r=b.getBoundingClientRect(); return r.left>=0 && r.right<=innerWidth && r.bottom<=innerHeight; }) };
  });
  assert.ok(bounds.top >= bounds.mainBottom - 1, JSON.stringify(bounds));
  assert.ok(bounds.buttonsFit && bounds.scrollWidth <= bounds.width + 1, JSON.stringify({width,bounds}));
  assert.equal(await toggle.isVisible(), true);
  assert.equal(await page.getByRole('button', {name:'新会话',exact:true}).count(), 0);
  metrics[width] = { layout: await layout(), geometry: await geometry(), dock: bounds };
  assert.ok(await page.locator('.focus-stream').evaluate(e => e.scrollWidth <= e.clientWidth + 1));
  await page.screenshot({ path: path.join(out, `${width}-light.png`) });
 }
 await page.getByRole('button', { name: '关闭回到最新提示' }).click();
 assert.equal(await page.getByRole('button', { name: /^回到最新/ }).count(), 0);
 await page.setViewportSize({width:1440,height:900});
 await page.evaluate(() => document.documentElement.dataset.theme='dark'); await settle();
 await page.screenshot({path:path.join(out,'1440-dark.png')});
 await toggle.click(); await page.reload(); await settle();
 assert.equal(await toggle.getAttribute('aria-pressed'),'false');
 await page.emulateMedia({reducedMotion:'reduce'}); await toggle.click(); await settle();
 assert.equal(await page.locator('.reading-lens').evaluate(e=>getComputedStyle(e).transitionDuration),'0s');
 assert.deepEqual(errors, []);
 fs.writeFileSync(path.join(out,'metrics.json'),JSON.stringify(metrics,null,2));
 console.log('PASS: side/split/stacked notes, normal/fullscreen, paragraph discussion, rail cards and paragraph foot, dock notices, 390–1600px, persistence and reduced motion.');
} finally { await browser.close(); fs.rmSync(fixture,{recursive:true,force:true}); }
