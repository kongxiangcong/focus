import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE);
const browser=await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE});
const page=await browser.newPage({viewport:{width:1440,height:1000}}), metrics={}, posts=[], errors=[];
page.setDefaultTimeout(60000);
page.on('response',r=>{if(r.status()>=400)errors.push(`${r.status()} ${r.url()}`)});
page.on('pageerror', error => errors.push(error.message));
page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
page.on('request',r=>{if(r.method()==='POST')posts.push({url:r.url(),body:r.postDataJSON()});});
const api=async()=>(await(await page.request.get(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}/reader/window`)).json()).value;
// This fixture intentionally exposes a direct Host, without a Workbench binding API.
await page.route('**/reader/workspace',route=>route.fulfill({json:{ok:true,value:{bound:true}}}));
try {
 await page.goto(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}/reading`);
 await page.getByRole('button',{name:'进入正文',exact:true}).click();await page.waitForSelector('.focus-reading .focus-markdown p');await page.getByRole('button',{name:'查看原文',exact:true}).first().click();await page.waitForTimeout(700);
 metrics.selection=await page.locator('.focus-reading .focus-markdown p').filter({hasText:'Paragraph 1:'}).first().evaluate(el=>{
  const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);const node=walker.nextNode();const range=document.createRange();range.setStart(node,0);range.setEnd(node,Math.min(node.length,12));const selection=getSelection();selection.removeAllRanges();selection.addRange(range);el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));return selection.toString();
 });
 await page.locator('.reader-anno-bubble').getByRole('button',{name:'引用提问',exact:true}).click();
 assert.ok((await page.locator('.focus-reference').innerText()).includes(metrics.selection));assert.equal(await page.locator('#focus-question').evaluate(el=>el===document.activeElement),true);
 await page.locator('#focus-question').fill('引用交互验收');await page.getByRole('button',{name:'发送',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('.reader-answer-actions'));
 const quote=page.locator('.reader-quote-bar').first();await quote.click();
 assert.equal(await page.evaluate(()=>CSS.highlights.has('reader-quote')),true);assert.equal(await page.getByRole('button',{name:'↩ 返回刚才位置',exact:true}).isVisible(),true);
 await page.waitForTimeout(2600);assert.equal(await page.evaluate(()=>CSS.highlights.has('reader-quote')),false);
 await page.mouse.move(0,0);await quote.hover();assert.equal(await page.evaluate(()=>CSS.highlights.has('reader-quote')),true);await page.mouse.move(0,0);assert.equal(await page.evaluate(()=>CSS.highlights.has('reader-quote')),false);
 const before=await api();const postCount=posts.length;
 await page.getByRole('button',{name:'回看第 1 段',exact:true}).first().click();await page.waitForTimeout(600);assert.equal(posts.length,postCount);assert.equal((await api()).readingRevision,before.readingRevision);
 // Verify graceful fallback by removing the registry for one interaction.
 await page.evaluate(()=>{window.savedHighlights=CSS.highlights;Object.defineProperty(CSS,'highlights',{value:undefined,configurable:true});});await quote.click();await page.evaluate(()=>Object.defineProperty(CSS,'highlights',{value:window.savedHighlights,configurable:true}));
 await page.getByRole('button',{name:'存为笔记',exact:true}).first().click();
 let saved;
 const notesBefore=before.sourceNotes.filter(n=>!n.deleted).length;
 for(let attempt=0;attempt<120;attempt++) {saved=await api();if(saved.sourceNotes.filter(n=>!n.deleted).length===notesBefore+1 && !['running','approval','stopping'].includes(saved.agent?.run?.status))break;await page.waitForTimeout(500);}
 metrics.notes={before:notesBefore,after:saved.sourceNotes.filter(n=>!n.deleted).length};
 assert.equal(metrics.notes.after,metrics.notes.before+1);
 const notePost=posts.find(p=>p.body?.content?.includes('记下来'));assert.ok(notePost);assert.deepEqual(Object.keys(notePost.body).sort(),['attachmentIds','content','receipt','requestId','sessionId','sourceId'].sort());assert.equal(notePost.body.receipt.chunkId,'chunk-001');metrics.noteRequest=notePost.body;
 await page.getByRole('button',{name:'资料',exact:true}).click();assert.equal(await page.getByRole('button',{name:'笔记',exact:true}).locator('small').innerText(),String(metrics.notes.after));await page.getByRole('button',{name:'关闭阅读侧栏',exact:true}).click();
 const locator=page.getByRole('button',{name:'当前阅读位置',exact:true});await locator.click();await page.getByRole('button',{name:'文章结构总览',exact:true}).click();await page.getByRole('region',{name:'文章结构',exact:true}).waitFor();await page.keyboard.press('Escape');assert.equal(await locator.evaluate(el=>el===document.activeElement),true);
 assert.equal(await page.locator('.mist-history-rail').count(),0);
 assert.deepEqual(errors, []);
 fs.writeFileSync(`${process.env.FOCUS_BROWSER_OUTPUT}/discussion.json`,JSON.stringify(metrics,null,2));console.log('PASS',metrics);
} catch(error) {console.log("STATE",JSON.stringify(await api()));console.log("BODY",await page.locator("body").innerText());throw error;} finally {await browser.close();}
