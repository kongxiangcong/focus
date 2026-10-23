/**
 * Reading annotations acceptance against an isolated Vite server.
 * Uses the canonical synthetic fixture and FixtureReaderHost; no external model calls.
 * Required: FOCUS_PLAYWRIGHT_MODULE, FOCUS_CHROMIUM_EXECUTABLE.
 * Optional: FOCUS_BROWSER_PORT, FOCUS_BROWSER_OUTPUT, FOCUS_READER_ROOT (worktree modules).
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const { chromium } = createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE);
function repositoryRoot() {
    let candidate = path.dirname(fileURLToPath(import.meta.url));
    for (;;) {
        if (fs.existsSync(path.join(candidate, 'tests/fixtures/reading-annotations-demo.json')) &&
            fs.existsSync(path.join(candidate, 'package.json')))
            return candidate;
        const parent = path.dirname(candidate);
        if (parent === candidate)
            throw new Error('Run this browser suite from a FOCUS checkout.');
        candidate = parent;
    }
}
const root = repositoryRoot();
const moduleRoot = (process.env.FOCUS_READER_ROOT || root).replaceAll('\\', '/');
const demo = JSON.parse(fs.readFileSync(path.join(root, 'tests/fixtures/reading-annotations-demo.json'), 'utf8'));
const tempRoot = path.join(root, 'ui/apps/standalone/tmp');
fs.mkdirSync(tempRoot, { recursive: true });
const fixture = fs.mkdtempSync(path.join(tempRoot, 'reading-annotations-'));
const out = process.env.FOCUS_BROWSER_OUTPUT || path.join(root, 'tmp/test-runs/annotations/browser');
fs.mkdirSync(out, { recursive: true });
fs.writeFileSync(path.join(fixture, 'index.html'), '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="icon" href="data:,"></head><body><div id="root"></div><script type="module" src="./main.tsx"></script></body></html>');
fs.writeFileSync(path.join(fixture, 'main.tsx'), `
import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {FocusReader} from '/@fs/${moduleRoot}/ui/packages/reader-ui/src/FocusReader.tsx';
import {FixtureReaderHost} from '/@fs/${moduleRoot}/ui/apps/standalone/src/adapters/fixture-reader-host.ts';
import {seedMarks} from '/@fs/${moduleRoot}/ui/packages/reader-ui/src/test-support/annotation-demo.ts';
import {cursorReceipt} from '/@fs/${moduleRoot}/ui/packages/reader-contracts/src/index.ts';
import '/@fs/${moduleRoot}/ui/packages/reader-ui/src/focus-tokens.css';
const demo = ${JSON.stringify(demo)};
const seeds = seedMarks(demo);
// Keep the canonical prototype fixture unchanged; one translated layer exercises layer isolation.
demo.chunks[2].translation='Translation layer: dynamic partitioning reduces external memory traffic. The switching overhead must also be measured.';
const stored = JSON.parse(sessionStorage.getItem('annotation-browser-state') || 'null');
const host = new FixtureReaderHost({source:demo.source,chunks:demo.chunks,notes:stored?.notes || [...demo.sourceNotes,...seeds.notes],highlights:stored?.highlights || seeds.highlights});
window.__annoHost=host;window.__annoCalls=[];
const dialogueNotes=[];let feedback=null;
const decorate=result=>result.ok?{...result,value:{...result.value,sourceNotes:[...result.value.sourceNotes,...dialogueNotes],noteFeedback:feedback,conversation:result.value.conversation.map(m=>({...m,sourceId:demo.source.sourceId,...(m.chunkId?{reference:{sourceId:demo.source.sourceId,planId:'plan-anno',chunkId:m.chunkId}}:{})}))}}:result;
const originalWindow=host.getReadingWindow.bind(host);host.getReadingWindow=async()=>decorate(await originalWindow());
const originalSend=host.sendMessage.bind(host);host.sendMessage=async input=>{
 window.__annoCalls.push({method:'sendMessage',args:[structuredClone(input)]});
 const result=await originalSend(input);
 if(result.ok && input.content.includes('记下来')){
  const chunk=demo.chunks.find(c=>c.chunkId===input.receipt?.chunkId);
  dialogueNotes.push({noteId:crypto.randomUUID().replaceAll('-',''),sourceId:demo.source.sourceId,revision:1,content:demo.dialogueNote.text,kind:'conclusion',origin:'dialogue',evidenceRole:'explanation',bundle:'anno-v1',anchor:null,placement:chunk?{sourceId:demo.source.sourceId,bundle:'anno-v1',sourceLines:chunk.sourceLines}:null,sentence:null,referenceStatus:'current',sourceUpdated:false,deleted:false,canUndo:true});feedback={status:'saved',sourceId:demo.source.sourceId};
 }
 return decorate(result);
};
for(const method of ['createHighlight','changeHighlight','createSourceNote','changeSourceNote']){
 const original=host[method].bind(host);
 host[method]=async(...args)=>{window.__annoCalls.push({method,args:structuredClone(args)});const result=await original(...args);if(result.ok)sessionStorage.setItem('annotation-browser-state',JSON.stringify({notes:result.value.sourceNotes,highlights:result.value.sourceHighlights}));return decorate(result);};
}
let view=(await host.getReadingWindow()).value;
while(view.current && view.current.index<demo.chunks.length)view=(await host.continueReading({receipt:cursorReceipt(view),requestId:crypto.randomUUID(),sessionId:view.sessionId})).value;
function Fixture(){const[fullscreen,setFullscreen]=useState(false);return <><style>{'html,body,#root{margin:0;height:100%}body{background:var(--reader-canvas,#f5f3ed)}.fixture-reader{height:100%;margin-left:248px}.fixture-reader[data-fullscreen=true]{margin-left:0}@media(max-width:720px){.fixture-reader{margin-left:0}}'}</style><div className="fixture-reader" data-fullscreen={fullscreen}><FocusReader host={host} appearance="mist" fullscreen={fullscreen} onFullscreenChange={setFullscreen}/></div></>}
createRoot(document.getElementById('root')).render(<Fixture/>);
`);
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE });
const errors = [], metrics = {};
function collectContextErrors(context, label) {
    const attach = page => {
        page.setDefaultTimeout(15000);
        page.on('pageerror', error => errors.push({ context: label, kind: 'pageerror', message: error.message }));
        page.on('console', message => {
            if (message.type() === 'error')
                errors.push({ context: label, kind: 'console', message: message.text() });
        });
        // Include client errors such as 400/401/404 as well as server failures.
        page.on('response', response => {
            if (response.status() >= 400)
                errors.push({ context: label, kind: 'response', status: response.status(), url: response.url() });
        });
    };
    context.on('page', attach);
    for (const page of context.pages())
        attach(page);
}
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
collectContextErrors(context, 'desktop');
const page = await context.newPage();
const chunk = id => page.locator(`.focus-reading[data-chunk-key="demo-anno/plan-anno/${id}"]`);
const snapshot = () => page.evaluate(async () => (await window.__annoHost.getReadingWindow()).value);
const settle = () => page.waitForTimeout(500);
async function checkpoint(name) { (metrics.positions ??= []).push({ name, ...await page.locator('.focus-stream').evaluate(el => ({ scroll: el.scrollTop, first: el.querySelector('.focus-reading')?.getBoundingClientRect().top })) }); }
async function top() { await page.locator('.focus-stream').evaluate(el => { el.dispatchEvent(new WheelEvent('wheel', { bubbles: true, deltaY: -100 })); el.scrollTop = 0; el.dispatchEvent(new Event('scroll', { bubbles: true })); }); await settle(); }
async function select(id, exact) {
    return chunk(id).locator('.focus-markdown').evaluate((root, exact) => {
        const nodes = [], walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        let text = '';
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            if (node.parentElement.closest('.katex,figure,[data-anno-ui],script,style'))
                continue;
            if (/^(TABLE|THEAD|TBODY|TFOOT|TR)$/.test(node.parentElement.tagName) && !node.data.trim())
                continue;
            nodes.push({ node, start: text.length });
            text += node.data;
        }
        const start = text.indexOf(exact);
        if (start < 0)
            throw Error('Selection quote missing');
        const end = start + exact.length;
        const first = nodes.find(n => n.start + n.node.length > start), last = nodes.find(n => n.start + n.node.length >= end);
        const range = document.createRange();
        range.setStart(first.node, start - first.start);
        range.setEnd(last.node, end - last.start);
        const selection = getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        root.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
        root.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
        document.dispatchEvent(new Event('selectionchange'));
        return { start, end, text: selection.toString() };
    }, exact);
}
try {
    await page.goto(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT || 5174}/tmp/${path.basename(fixture)}/index.html`);
    await chunk('c1').waitFor();
    await top();
    const toggle = page.getByRole('navigation', { name: '阅读功能控制区' }).getByRole('button', { name: '笔记', exact: true });
    if (await toggle.getAttribute('aria-pressed') === 'true') {
        await toggle.click();
        await settle();
    }
    // A1: a selection crossing two paragraphs only offers discussion, never a write.
    await chunk('c1').locator('.focus-markdown').evaluate(root => { const paragraphs = root.querySelectorAll('p'), range = document.createRange(); range.setStartBefore(paragraphs[0]); range.setEndAfter(paragraphs[1]); const s = getSelection(); s.removeAllRanges(); s.addRange(range); document.dispatchEvent(new Event('selectionchange')); });
    await settle();
    assert.deepEqual(await page.locator('.reader-anno-bubble button').allTextContents(), ['引用提问']);
    await page.keyboard.press('Escape');
    await page.evaluate(() => getSelection().removeAllRanges());
    const quote = '访问一次 DRAM 的能耗大约是一次 8 位乘加的两百倍';
    await checkpoint('before-selection');
    metrics.selection = await select('c1', quote);
    await settle();
    const bubble = page.locator('.reader-anno-bubble');
    await bubble.waitFor();
    await bubble.getByRole('button', { name: '重点', exact: true }).waitFor();
    await bubble.getByRole('button', { name: '备注', exact: true }).waitFor();
    await bubble.getByRole('button', { name: '引用提问', exact: true }).waitFor();
    await bubble.getByRole('button', { name: '重点', exact: true }).click();
    await settle();
    await checkpoint('after-highlight');
    const mark = chunk('c1').locator('.reader-anno--hl').filter({ hasText: '访问一次' }).first();
    await mark.waitFor();
    metrics.highlight = await mark.evaluate(el => ({ weight: getComputedStyle(el).fontWeight, image: getComputedStyle(el).backgroundImage }));
    assert.equal(metrics.highlight.weight, '700');
    assert.match(metrics.highlight.image, /linear-gradient/);
    const ids = (await snapshot()).sourceHighlights.filter(item => !item.deleted).map(item => item.highlightId);
    await page.reload();
    await chunk('c1').waitFor();
    await top();
    await checkpoint('after-reload-top');
    assert.deepEqual((await snapshot()).sourceHighlights.filter(item => !item.deleted).map(item => item.highlightId), ids);
    await chunk('c1').locator('.reader-anno--hl').filter({ hasText: '访问一次' }).first().click();
    await page.locator('.reader-anno-bubble').getByRole('button', { name: '备注', exact: true }).click();
    const editor = page.locator('.reader-anno-pop').filter({ has: page.locator('textarea') });
    await editor.waitFor();
    await checkpoint('editor-open');
    metrics.editor = await editor.evaluate(el => { const spans = [...document.querySelectorAll('.reader-anno[data-anno-key]')].filter(el => el.textContent.includes('访问一次')); const key = spans[0]?.getAttribute('data-anno-key'); const parts = [...document.querySelectorAll('.reader-anno[data-anno-key]')].filter(el => el.getAttribute('data-anno-key') === key); const boxes = parts.flatMap(el => [...el.getClientRects()]); const last = boxes.at(-1), box = el.getBoundingClientRect(); return { top: box.top, bottom: box.bottom, anchorBottom: last?.bottom, gap: box.top - (last?.bottom ?? 0) }; });
    assert.ok(metrics.editor.gap >= 0 && metrics.editor.gap <= 20, JSON.stringify(metrics.editor));
    const field = editor.locator('textarea');
    await field.fill('面积开销很小，');
    await field.press('Shift+Enter');
    await field.pressSequentially('但没算布线。');
    await field.press('Enter');
    await settle();
    await checkpoint('after-note-save');
    const noteMark = chunk('c1').locator('.reader-anno--note').filter({ hasText: '访问一次' }).first();
    await noteMark.waitFor();
    const noteKey = await noteMark.getAttribute('data-anno-key');
    const bulb = chunk('c1').locator(`[data-anno-bulb="${noteKey}"]`);
    await bulb.click();
    await page.getByRole('dialog', { name: '备注', exact: true }).waitFor();
    assert.match(await page.getByRole('dialog', { name: '备注', exact: true }).innerText(), /面积开销很小，\n但没算布线。/);
    await page.keyboard.press('Escape');
    await checkpoint('note-view-close');
    // A4: edit through the annotation toolbar; deleting the combined mark deletes both entities.
    await top();
    await noteMark.click();
    await page.locator('.reader-anno-bubble').getByRole('button', { name: '编辑备注', exact: true }).click();
    await page.getByRole('textbox', { name: '备注文字', exact: true }).fill('编辑后的句子备注');
    await page.getByRole('textbox', { name: '备注文字', exact: true }).press('Enter');
    await settle();
    const beforeDelete = await snapshot();
    const activeCounts = view => ({ notes: view.sourceNotes.filter(n => !n.deleted).length, highlights: view.sourceHighlights.filter(n => !n.deleted).length });
    const counts = activeCounts(beforeDelete);
    await noteMark.click();
    await page.locator('.reader-anno-bubble').getByRole('button', { name: '删除标注', exact: true }).click();
    await settle();
    assert.deepEqual(activeCounts(await snapshot()), { notes: counts.notes - 1, highlights: counts.highlights - 1 });
    assert.equal(await page.evaluate(() => window.__annoCalls.filter(c => c.args[2] === 'delete').slice(-2).map(c => c.method).sort().join(',')), 'changeHighlight,changeSourceNote');
    await page.locator('.reader-anno-toast').getByRole('button', { name: '撤销', exact: true }).click();
    await settle();
    assert.deepEqual(activeCounts(await snapshot()), counts);
    // Cancel only the highlight, keeping the remark; the mark remains red and gains no yellow fill.
    await noteMark.click();
    await page.locator('.reader-anno-bubble').getByRole('button', { name: '取消重点', exact: true }).click();
    await settle();
    assert.deepEqual(activeCounts(await snapshot()), { notes: counts.notes, highlights: counts.highlights - 1 });
    assert.equal(await chunk('c1').locator('.reader-anno--hl').filter({ hasText: '访问一次' }).count(), 0);
    const onlyHighlight = chunk('c1').locator('.reader-anno--hl').filter({ hasText: '决定性能上限' }).first();
    await onlyHighlight.click();
    await page.locator('.reader-anno-bubble').getByRole('button', { name: '取消重点', exact: true }).click();
    await settle();
    assert.equal(await onlyHighlight.count(), 0);
    await page.locator('.reader-anno-toast').getByRole('button', { name: '撤销', exact: true }).click();
    await settle();
    await onlyHighlight.waitFor();
    // A17: sentence remarks are ordinary SourceNotes in their own materials group.
    await page.getByRole('button', { name: '资料', exact: true }).click();
    await page.locator('.reader-left-drawer').getByRole('button', { name: '笔记', exact: true }).click();
    const sentenceGroup = page.locator('.source-notes-group[aria-label="句子备注"]');
    const savedRemark = (await snapshot()).sourceNotes.find(note => !note.deleted && note.content === '编辑后的句子备注');
    assert.ok(savedRemark?.sentence, 'A sentence remark must be persisted as a SourceNote with a sentence locator.');
    assert.equal(savedRemark.sentence.quote.exact, quote);
    const remarkRow = sentenceGroup.locator('[data-source-note-id="' + savedRemark.noteId + '"]');
    await remarkRow.getByText('「' + quote + '」', { exact: true }).waitFor();
    await remarkRow.getByText('编辑后的句子备注', { exact: true }).waitFor();
    assert.equal(await page.locator('.source-notes-group[aria-label="小段笔记"] [data-source-note-id="' + savedRemark.noteId + '"]').count(), 0);
    const sentenceIds = (await snapshot()).sourceNotes.filter(note => !note.deleted && note.sentence).map(note => note.noteId);
    for (const noteId of sentenceIds) {
        const duplicate = page.locator('.reader-chunk-notes [data-chunk-note-id="' + noteId + '"], .reader-chunk-notes-fold [data-chunk-note-id="' + noteId + '"]');
        assert.equal(await duplicate.count(), 0, 'Sentence remarks must not also appear in paragraph-note lists: ' + noteId);
    }
    metrics.materials = { sentenceNoteId: savedRemark.noteId, sentenceNoteCount: sentenceIds.length, duplicatedParagraphEntries: 0 };
    await page.getByRole('button', { name: '关闭阅读侧栏', exact: true }).click();
    // A10: original and translated marks never leak across layers.
    const c3 = chunk('c3');
    await c3.getByRole('button', { name: '查看原文', exact: true }).click();
    await settle();
    const sourceMarks = await c3.locator('.reader-anno').count();
    assert.ok(sourceMarks > 0);
    await c3.getByRole('button', { name: '查看译文', exact: true }).click();
    await settle();
    assert.equal(await c3.locator('.reader-anno').count(), 0);
    await select('c3', 'dynamic partitioning reduces external memory traffic');
    await settle();
    await page.locator('.reader-anno-bubble').getByRole('button', { name: '重点', exact: true }).click();
    await settle();
    assert.equal(new Set(await c3.locator('.reader-anno--hl').evaluateAll(es => es.map(e => e.dataset.annoKey))).size, 1);
    assert.equal((await snapshot()).sourceHighlights.at(-1).layer, 'translation');
    await c3.getByRole('button', { name: '查看原文', exact: true }).click();
    await settle();
    assert.equal(await c3.locator('.reader-anno').count(), sourceMarks);
    assert.equal(await c3.locator('.reader-anno').filter({ hasText: 'dynamic partitioning' }).count(), 0);
    await top();
    metrics.passed = ['A1', 'A2', 'A3', 'A4', 'A10', 'A17'];
    await page.screenshot({ path: path.join(out, 'anno-detached-1600x1000-light.png') });
    // A5: sentence cards follow the source text; paragraph notes sit below both text and cards.
    await toggle.click();
    await page.waitForTimeout(1000);
    async function railGeometry() {
        return page.locator('.reading-group-passage').evaluateAll(groups => groups.map(group => {
            const rail = group.querySelector('.reader-anno-rail'), source = group.querySelector('.reading-group-source');
            if (!rail || !source)
                return null;
            const rect = el => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right }; };
            const cards = [...rail.querySelectorAll('.reader-anno-card')].map(card => { const key = card.dataset.annoCard, mark = [...source.querySelectorAll('[data-anno-key]')].find(m => m.dataset.annoKey === key); return { ...rect(card), key, displaced: card.classList.contains('is-displaced'), anchorTop: mark?.getClientRects()[0]?.top }; });
            const foot = rail.querySelector('.reader-chunk-notes');
            return { source: rect(source), cards, foot: foot ? rect(foot) : null };
        }).filter(Boolean));
    }
    async function assertRails(stacked = false) { const geometry = await railGeometry(); assert.equal(geometry.length, 3); for (const item of geometry) {
        for (let i = 1; i < item.cards.length; i++)
            assert.ok(item.cards[i].top >= item.cards[i - 1].bottom - 1, JSON.stringify(item));
        if (!stacked)
            for (const card of item.cards) {
                assert.equal(typeof card.anchorTop, 'number', JSON.stringify(card));
                if (!card.displaced)
                    assert.ok(Math.abs(card.top - card.anchorTop) <= 8, JSON.stringify(card));
            }
        if (item.foot) {
            assert.ok(item.foot.top >= item.source.bottom - 1, JSON.stringify(item));
            if (item.cards.length)
                assert.ok(item.foot.top >= item.cards.at(-1).bottom - 1, JSON.stringify(item));
        }
    } return geometry; }
    for (const [width, height] of [[1600, 1000], [1280, 800], [1024, 768]]) {
        await page.setViewportSize({ width, height });
        await page.waitForTimeout(1000);
        await top();
        metrics[`rail-${width}`] = await assertRails((await page.locator('.focus-reader').getAttribute('data-anno-rail')) === 'stacked');
        assert.ok(await page.locator('.reader-anno-bulb').evaluateAll(es => es.every(e => getComputedStyle(e).visibility === 'hidden')));
        await page.screenshot({ path: path.join(out, `anno-attached-${width}x${height}-light.png`) });
    }
    assert.match(await page.getByRole('complementary', { name: '第 2 段笔记', exact: true }).innerText(), /来自讨论/);
    await page.setViewportSize({ width: 1600, height: 1000 });
    await page.waitForTimeout(600);
    await top();
    // A6: saving remains an inline editor; its resulting card visibly flies to the rail.
    await chunk('c2').scrollIntoViewIfNeeded();
    await select('c2', '这篇文章的核心主张是');
    await settle();
    await page.locator('.reader-anno-bubble').getByRole('button', { name: '备注', exact: true }).click();
    const attachedEditor = page.getByRole('textbox', { name: '备注文字', exact: true });
    assert.equal(await attachedEditor.locator('xpath=ancestor::aside').count(), 0);
    await attachedEditor.fill('吸附模式新增备注');
    await attachedEditor.press('Enter');
    await page.waitForTimeout(150);
    metrics.saveAnimations = await page.evaluate(() => document.getAnimations().map(a => ({ target: a.effect?.target?.className, state: a.playState })));
    assert.ok(metrics.saveAnimations.some(a => String(a.target).includes('reader-anno-card')), JSON.stringify(metrics.saveAnimations));
    await page.screenshot({ path: path.join(out, 'anno-save-flight-1600x1000-light.png') });
    await page.waitForTimeout(1000);
    await page.locator('.reader-anno-card').filter({ hasText: '吸附模式新增备注' }).waitFor();
    // A7: detach ghosts finish, bulbs return, and paragraph note disclosures remain operable.
    await toggle.click();
    await page.waitForTimeout(1000);
    assert.equal(await page.locator('.reader-anno-ghost-layer > *').count(), 0);
    assert.ok(await page.locator('.reader-anno-bulb').evaluateAll(es => es.every(e => getComputedStyle(e).visibility === 'visible')));
    const fold = page.locator('.reader-chunk-notes-fold').first(), disclosure = fold.getByRole('button', { name: /小段笔记 ·/ });
    assert.equal(await disclosure.getAttribute('aria-expanded'), 'false');
    await disclosure.click();
    assert.equal(await disclosure.getAttribute('aria-expanded'), 'true');
    await disclosure.click();
    assert.equal(await disclosure.getAttribute('aria-expanded'), 'false');
    metrics.passed.push('A5', 'A6', 'A7');
    // A8: a discussion save lands in the referenced chunk; removing the reference yields a whole-source note.
    await chunk('c3').getByRole('button', { name: '引用提问', exact: true }).click();
    await page.locator('#focus-question').fill('讨论第三段的限制');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await settle();
    await page.getByRole('button', { name: '存为笔记', exact: true }).last().click();
    await settle();
    assert.match(await page.locator('.reader-anno-toast').innerText(), /第 3 段/);
    const thirdFold = page.locator('.reader-chunk-notes-fold').nth(2);
    assert.match(await thirdFold.innerText(), /来自讨论/);
    assert.match(await thirdFold.innerText(), /批大小为一/);
    await chunk('c3').getByRole('button', { name: '引用提问', exact: true }).click();
    await page.getByRole('button', { name: '取消段落引用', exact: true }).click();
    await page.locator('#focus-question').fill('无引用的讨论');
    await page.getByRole('button', { name: '发送', exact: true }).click();
    await settle();
    await page.getByRole('button', { name: '存为笔记', exact: true }).last().click();
    await settle();
    assert.match(await page.locator('.reader-anno-toast').innerText(), /已存为整篇笔记/);
    metrics.passed.push('A8');
    // A9: direct paragraph notes carry chunk identity, and stale bundles offer a whole-source fallback.
    await fold.getByRole('button', { name: /记小段笔记$/ }).click();
    await page.getByRole('textbox', { name: '小段笔记', exact: true }).fill('直接保存的小段笔记');
    await page.getByRole('textbox', { name: '小段笔记', exact: true }).press('Enter');
    await settle();
    const direct = await page.evaluate(() => window.__annoCalls.filter(c => c.method === 'createSourceNote' && c.args[0].content === '直接保存的小段笔记').at(-1));
    assert.deepEqual(direct.args[0].chunk, { planId: 'plan-anno', chunkId: 'c1' });
    await page.evaluate(() => window.__annoHost.noteCreateOutcome = 'note_bundle_changed');
    await fold.getByRole('button', { name: /记小段笔记$/ }).click();
    await page.getByRole('textbox', { name: '小段笔记', exact: true }).fill('原文变化后的草稿');
    await page.getByRole('textbox', { name: '小段笔记', exact: true }).press('Enter');
    await settle();
    await page.getByRole('button', { name: '存为整篇笔记', exact: true }).waitFor();
    await page.evaluate(() => window.__annoHost.noteCreateOutcome = 'success');
    await page.getByRole('button', { name: '存为整篇笔记', exact: true }).click();
    await settle();
    assert.equal((await snapshot()).sourceNotes.find(n => n.content === '原文变化后的草稿')?.anchor, null);
    metrics.passed.push('A9');
    // A13: a touch context uses stacked cards and the promised 43px bulb hit target.
    const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    await mobileContext.addInitScript(() => { if (location.protocol === 'http:' || location.protocol === 'https:') localStorage.setItem('focus.attachNotes', 'true'); });
    collectContextErrors(mobileContext, 'mobile-touch');
    const mobile = await mobileContext.newPage();
    await mobile.goto(page.url());
    await mobile.locator('.reader-anno-card').first().waitFor();
    await mobile.waitForTimeout(1000);
    assert.equal(await mobile.locator('.focus-reader').getAttribute('data-anno-rail'), 'stacked');
    assert.ok(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    metrics.mobileStack = await mobile.locator('.reading-group-passage').first().evaluate(group => {
        const bottom = el => el.getBoundingClientRect().bottom, top = el => el.getBoundingClientRect().top;
        const cards = [...group.querySelectorAll('.reader-anno-card')];
        return { bodyBottom: bottom(group.querySelector('.reading-group-source')), cardTops: cards.map(top), cardBottoms: cards.map(bottom), notesTop: top(group.querySelector('.reader-chunk-notes')) };
    });
    assert.ok(metrics.mobileStack.cardTops.length > 0);
    assert.ok(metrics.mobileStack.cardTops[0] >= metrics.mobileStack.bodyBottom - 1, JSON.stringify(metrics.mobileStack));
    assert.ok(metrics.mobileStack.notesTop >= metrics.mobileStack.cardBottoms.at(-1) - 1, JSON.stringify(metrics.mobileStack));
    await mobile.locator('.reader-anno-card').first().evaluate(el => {
        const pane = document.querySelector('.focus-stream');
        pane.dispatchEvent(new WheelEvent('wheel', { bubbles: true, deltaY: -100 }));
        pane.scrollTop += el.getBoundingClientRect().top - 150;
    });
    await mobile.waitForTimeout(400);
    await mobile.screenshot({ path: path.join(out, 'anno-stacked-390x844-light.png') });
    await mobile.getByRole('navigation', { name: '阅读功能控制区' }).getByRole('button', { name: '笔记', exact: true }).click();
    await mobile.waitForTimeout(1000);
    const mobileBulb = mobile.locator('.reader-anno-bulb').first();
    await mobileBulb.scrollIntoViewIfNeeded();
    metrics.touchTarget = await mobileBulb.evaluate(el => { const r = el.getBoundingClientRect(), x = r.x + r.width / 2, y = r.y + r.height / 2; return { width: r.width, after: getComputedStyle(el, '::after').inset, hit: [[-21, 0], [21, 0], [0, -21], [0, 21]].map(([dx, dy]) => el.contains(document.elementFromPoint(x + dx, y + dy))) }; });
    assert.ok(metrics.touchTarget.hit.every(Boolean), JSON.stringify(metrics.touchTarget));
    await mobileContext.close();
    metrics.passed.push('A13');
    // A14: capture the fully settled theme state for visual inspection.
    await page.evaluate(() => document.documentElement.dataset.theme = 'dark');
    await toggle.click();
    await top();
    await page.waitForTimeout(1800);
    await page.screenshot({ path: path.join(out, 'anno-attached-1600x1000-dark.png') });
    metrics.passed.push('A14');
    // A12: start a separate reduced-motion context and exercise toggle and deletion.
    const reducedContext = await browser.newContext({ viewport: { width: 1600, height: 1000 }, reducedMotion: 'reduce' });
    collectContextErrors(reducedContext, 'reduced-motion');
    const reduced = await reducedContext.newPage();
    await reduced.goto(page.url());
    await reduced.locator('.reader-anno').first().waitFor();
    const rt = reduced.getByRole('navigation', { name: '阅读功能控制区' }).getByRole('button', { name: '笔记', exact: true });
    await rt.click();
    await reduced.waitForTimeout(100);
    await rt.click();
    await reduced.waitForTimeout(100);
    assert.equal(await reduced.evaluate(() => document.getAnimations().length), 0);
    await reduced.locator('.focus-stream').evaluate(el => { el.dispatchEvent(new WheelEvent('wheel', { bubbles: true, deltaY: -100 })); el.scrollTop = 0; });
    await reduced.locator('.reader-anno[data-anno-key]').first().click();
    await reduced.locator('.reader-anno-bubble').getByRole('button', { name: '删除标注', exact: true }).click();
    await reduced.waitForTimeout(100);
    assert.equal(await reduced.evaluate(() => document.getAnimations().length), 0);
    await reducedContext.close();
    metrics.passed.push('A12');
    assert.deepEqual(errors, []);
    metrics.errors = errors;
    fs.writeFileSync(path.join(out, 'metrics.json'), JSON.stringify(metrics, null, 2));
    console.log('PASS:', metrics.passed);
}
finally {
    await browser.close();
    fs.rmSync(fixture, { recursive: true, force: true });
}
