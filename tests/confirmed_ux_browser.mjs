const {chromium} = await import(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
import assert from 'node:assert/strict';
import fs from 'node:fs';
const browser=await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE || undefined,args:['--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-zygote']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const results=[];
const api=async()=> (await (await page.request.get('http://127.0.0.1:8765/reader/window')).json()).value;
const latest=async(index)=> {await page.waitForFunction(i=>document.querySelector('.focus-output[data-current-output="true"]')?.textContent.includes(`Section ${i}`),index)};
const next=async(index)=> {await page.getByRole('button',{name:'继续',exact:true}).click();await latest(index)};
await page.goto('http://127.0.0.1:8765/reading');await latest(1);
// Draft written against paragraph 1 survives moving to 2.
await page.getByRole('textbox',{name:'输入问题或阅读需求'}).fill('第一段的问题');await next(2);
assert.equal(await page.locator('.focus-output').count(),2);
await page.getByRole('button',{name:'发送 ↑',exact:true}).click();
await page.waitForFunction(()=>document.querySelector('[data-role="assistant"]')?.textContent.includes('回复第2句'));
const stream=page.locator('.focus-stream');await stream.hover();await page.mouse.wheel(0,-400);
await page.waitForTimeout(100);const manual=await stream.evaluate(el=>el.scrollTop);
await page.waitForTimeout(550);assert.ok(Math.abs((await stream.evaluate(el=>el.scrollTop))-manual)<10);
await page.getByRole('button',{name:'查看新内容',exact:true}).click();
await page.waitForFunction(()=>document.querySelector('.workspace-status')?.textContent.includes('当前无工作'));
let view=await api();assert.equal(view.conversation[0].reference.chunkId,'chunk-001');results.push('T3/T4/T6 stream order, manual scroll and anchored draft');
// Continue to 8, review 3, browse 4; progress remains 8.
for(let i=3;i<=8;i++)await next(i);
await page.getByRole('navigation',{name:'段落目录'}).getByRole('button',{name:/03/}).click();await latest(3);
const before=await api();await next(4);view=await api();assert.equal(view.navigationCurrent.index,8);assert.equal(view.readingRevision,before.readingRevision);assert.equal(view.readingProgress.length,before.readingProgress.length);results.push('T5 history Continue does not roll back progress');
// New session persists blank across reload and resumes 9 from frontier 8.
await page.getByRole('button',{name:'新会话',exact:true}).click();await page.waitForFunction(()=>document.querySelectorAll('.focus-output').length===0);
await page.reload();await page.getByRole('button',{name:'继续',exact:true}).waitFor();assert.equal(await page.locator('.focus-output').count(),0);
await next(9);view=await api();assert.equal(view.navigationCurrent.index,9);results.push('T7/T26 new session / refresh / next 9');
// Sidebar hides without occupying center space; narrow layout and large font.
if (await page.getByRole('button',{name:'笔记与记录',exact:true}).count()) await page.getByRole('button',{name:'笔记与记录',exact:true}).click();
await page.getByRole('button',{name:'隐藏资料栏',exact:true}).click();const hiddenWidth=(await stream.boundingBox()).width;
await page.getByRole('button',{name:'笔记与记录',exact:true}).click();assert.ok((await stream.boundingBox()).width<hiddenWidth);
// Exercise the sidebar through real HTTP mutations; none may move the frontier.
const notes=page.locator('.reader-materials details').filter({has:page.locator('summary').filter({hasText:/^笔记 ·/})});
await notes.locator('summary').click();
await notes.getByRole('button',{name:'编辑',exact:true}).click();
await page.getByRole('textbox',{name:'编辑笔记',exact:true}).fill('Browser note after editing');
await notes.getByRole('button',{name:'保存修改',exact:true}).click();
await notes.getByText('Browser note after editing',{exact:true}).waitFor();
await notes.getByRole('button',{name:'删除',exact:true}).click();
await notes.getByText('已删除，可撤销',{exact:true}).waitFor();
await notes.getByRole('button',{name:'撤销',exact:true}).click();
await notes.getByText('Browser note after editing',{exact:true}).waitFor();
const records=page.locator('.reader-materials details').filter({has:page.locator('summary').filter({hasText:/^阅读记录 ·/})});
await records.locator('summary').click();
const recordBefore=await api();
await records.getByRole('button',{name:'更正',exact:true}).first().click();
await page.getByRole('textbox',{name:'更正阅读记录',exact:true}).fill('Browser corrected reading record');
await records.getByRole('button',{name:'保存更正',exact:true}).click();
await records.getByText(/Browser corrected reading record/).waitFor();
page.once('dialog',async dialog=>{assert.match(dialog.message(),/阅读位置不会改变/);await dialog.accept()});
await records.getByRole('button',{name:'删除',exact:true}).first().click();
await page.waitForFunction(n=>document.querySelectorAll('.reader-materials details:last-child li').length===n,recordBefore.readingProgress.filter(e=>!e.deleted).length-1);
view=await api();assert.equal(view.navigationCurrent.index,recordBefore.navigationCurrent.index);
assert.equal(view.readingRevision,recordBefore.readingRevision);
assert.equal(view.sourceNotes[0].content,'Browser note after editing');
assert.equal(view.sourceNotes[0].deleted,false);
assert.equal(view.readingProgress.filter(e=>e.deleted).length,1);
results.push('T16 note edit/delete/undo and progress edit/delete preserve cursor');
await page.screenshot({path:`${process.env.FOCUS_BROWSER_OUTPUT || '/tmp'}/focus-desktop.png`});
await page.getByRole('link',{name:'设置',exact:true}).click();await page.getByRole('slider',{name:'字号',exact:true}).fill('3');
// Save appearance only is observed even if external backend config is not verified.
await page.getByRole('button',{name:'保存并应用',exact:true}).click();
await page.getByRole('link',{name:'阅读',exact:true}).click();await page.setViewportSize({width:390,height:844});
await page.waitForTimeout(300);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
assert.ok((await page.getByRole('button',{name:'完成本篇',exact:true}).boundingBox()).y<844);
assert.equal(await page.locator('.reading-title-scroll').count(),0);
await page.getByRole('combobox',{name:'选择阅读材料',exact:true}).focus();
assert.ok(await page.getByRole('combobox',{name:'选择阅读材料',exact:true}).getAttribute('title'));
const pickerBox=await page.locator('.reading-library-picker').boundingBox();
const taskBox=await page.getByRole('button',{name:'任务详情',exact:true}).boundingBox();
assert.ok(Math.abs(pickerBox.y-taskBox.y)<10);
assert.equal(await page.locator('.workspace-task-frame').count(),0);
await page.getByRole('button',{name:'隐藏资料栏',exact:true}).focus();await page.keyboard.press('Enter');
await page.getByRole('button',{name:'笔记与记录',exact:true}).click();await page.keyboard.press('Escape');
assert.equal(await page.getByRole('button',{name:'笔记与记录',exact:true}).count(),1);
await page.screenshot({path:`${process.env.FOCUS_BROWSER_OUTPUT || '/tmp'}/focus-narrow.png`});results.push('T16/T21 sidebar toggle and narrow viewport / extra font');
// Finish then review last remains terminal.
await page.getByRole('button',{name:'完成本篇',exact:true}).click();await page.getByRole('button',{name:'已读完',exact:true}).waitFor();
await page.getByRole('navigation',{name:'段落目录'}).getByRole('button',{name:/09/}).click();await latest(9);
assert.equal(await page.getByRole('button',{name:'已读完',exact:true}).isDisabled(),true);results.push('T9 complete terminal state');
// Reset via Library is confirmed and first Continue opens first, not second.
await page.getByRole('link',{name:'知识库',exact:true}).click();await page.getByRole('button',{name:'详细',exact:true}).click();
assert.equal(await page.getByRole('button',{name:'讨论',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'从头阅读',exact:true}).count(),0);
await page.getByRole('button',{name:'重新阅读',exact:true}).click();await page.getByRole('button',{name:'确认重新阅读',exact:true}).click();
await page.waitForFunction(()=>!document.querySelector('.workspace-confirm[open]'));
await page.getByRole('link',{name:'阅读',exact:true}).click();await page.getByRole('button',{name:'继续',exact:true}).click();await latest(1);
view=await api();assert.equal(view.readingProgress.length,0);assert.equal(view.sourceNotes.length,0);assert.equal(view.conversation.length,0);results.push('T8/U6 confirmed reset clears progress and next opens first');
// Historical browsing reaches the frontier, then advances exactly once.
await next(2);await next(3);
const frontier=await api();
await page.getByRole('navigation',{name:'段落目录'}).getByRole('button',{name:/01/}).click();await latest(1);
await next(2);await next(3);
view=await api();assert.equal(view.navigationCurrent.index,3);
assert.equal(view.readingRevision,frontier.readingRevision);
assert.equal(view.readingProgress.length,frontier.readingProgress.length);
await next(4);view=await api();assert.equal(view.navigationCurrent.index,4);
assert.equal(view.readingRevision,frontier.readingRevision+1);
assert.equal(view.readingProgress.length,frontier.readingProgress.length+1);
results.push('T5 review reaches frontier then advances exactly once');
// Deterministic published blog fixture: this suite verifies the UI, not model generation.
await page.route('**/library/sources/fixture-paper/blog',route=>route.fulfill({json:{ok:true,value:{
 sourceId:'fixture-paper',generated:true,runStatus:'completed',methodVersion:'ui-fixture',
 artifacts:{value_analysis:{status:'completed'},reading_blog:{status:'completed'},html:{status:'completed'}},
 valueAnalysis:{applicable:true,reason:''},verificationLevel:'paper_reading',warnings:[],error:null
}}}));
await page.route('**/library/sources/fixture-paper/blog/html',route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html><body><h1>Published blog fixture</h1><p>Readable content for viewer layout verification.</p></body></html>'}));
// One disclosure owns all upload history; it starts hidden even with multiple batches.
await page.route('**/library/batches', route=>route.fulfill({json:{ok:true,value:[
 {batchId:'visual-running',topicId:'未分类',status:'running',error:null,items:[{itemId:'visual-item',fileName:'visual.pdf',sourceId:null,status:'processing',ingestionStatus:'processing',blog:null,error:null}]},
 {batchId:'visual-done',topicId:'未分类',status:'completed',error:null,items:[]}
]}}));
await page.setViewportSize({width:1440,height:1000});
await page.goto('http://127.0.0.1:8765/library');
await page.getByRole('button',{name:'详细',exact:true}).waitFor();
const toggle=page.getByRole('button',{name:'任务详情',exact:true});
assert.equal(await toggle.getAttribute('aria-expanded'),'false');
assert.equal(await page.locator('.library-inbox').count(),0);
const titleBox=await page.getByRole('heading',{name:'知识库',exact:true}).boundingBox();
const toggleBox=await toggle.boundingBox();assert.ok(Math.abs(titleBox.y-toggleBox.y)<12);
await toggle.click();
assert.equal(await page.locator('.library-inbox details[open]').count(),0);
await page.locator('.library-inbox summary').first().click();
await page.getByText('visual.pdf',{exact:true}).waitFor();
await toggle.click();assert.equal(await page.locator('.library-inbox').count(),0);
await page.screenshot({path:`${process.env.FOCUS_BROWSER_OUTPUT || '/tmp'}/focus-library.png`});
results.push('UI task history hidden by default, single disclosure, heading alignment');
// A modal uses the browser top layer: the close target must win hit testing.
await page.getByRole('button',{name:'详细',exact:true}).click();
const openBlog=page.getByRole('button',{name:'打开博客',exact:true});
await page.waitForFunction(()=>Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='打开博客')?.disabled===false);
for (const viewport of [{width:1440,height:1000},{width:390,height:844}]) {
 await page.setViewportSize(viewport);await openBlog.click();
 const viewer=page.locator('.workspace-blog-viewer');
 assert.equal(await viewer.evaluate(el=>el.matches(':modal')),true);
 const close=viewer.getByRole('button',{name:'关闭',exact:true});
 assert.equal(await close.evaluate(el=>{const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}),true);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.screenshot({path:`${process.env.FOCUS_BROWSER_OUTPUT || '/tmp'}/focus-blog-${viewport.width}.png`});
 await close.click();assert.equal(await viewer.count(),0);
 assert.equal(await openBlog.evaluate(el=>el===document.activeElement),true);
 await openBlog.click();await page.keyboard.press('Escape');assert.equal(await viewer.count(),0);
 assert.equal(await openBlog.evaluate(el=>el===document.activeElement),true);
}
results.push('UI blog top-layer close hit target and Escape at desktop/narrow widths');
assert.deepEqual(errors,[]);
fs.writeFileSync(`${process.env.FOCUS_BROWSER_OUTPUT || '/tmp'}/focus-browser-results.json`,JSON.stringify({results,errors},null,2));console.log(JSON.stringify({results,errors}));await browser.close();
