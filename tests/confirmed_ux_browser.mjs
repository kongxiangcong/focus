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
await page.getByRole('button',{name:'保存设置',exact:true}).click();
await page.getByRole('link',{name:'阅读',exact:true}).click();await page.setViewportSize({width:390,height:844});
await page.waitForTimeout(300);assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
assert.ok((await page.getByRole('button',{name:'完成本篇',exact:true}).boundingBox()).y<844);
const title=page.getByLabel('材料完整标题', {exact:true}); await title.focus(); await page.keyboard.press('End');
assert.ok(await title.evaluate(el=>el.scrollWidth>el.clientWidth));
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
assert.deepEqual(errors,[]);
fs.writeFileSync(`${process.env.FOCUS_BROWSER_OUTPUT || '/tmp'}/focus-browser-results.json`,JSON.stringify({results,errors},null,2));console.log(JSON.stringify({results,errors}));await browser.close();
