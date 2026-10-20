import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.FOCUS_PLAYWRIGHT_MODULE);
const browser=await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE});
const page=await browser.newPage({viewport:{width:1600,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const wait=()=>page.waitForTimeout(700);
const metrics=[];
try {
 await page.goto(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}/reading`);
 await page.getByRole('button',{name:'进入正文',exact:true}).click();await wait();
 await page.getByRole('button',{name:'全屏',exact:true}).click();await wait();
 const measure=()=>page.evaluate(()=>{
  const rect=s=>{const e=document.querySelector(s),r=e.getBoundingClientRect();return {x:r.x,right:r.right,width:r.width,y:r.y,scroll:e.scrollWidth,client:e.clientWidth};};
  return {content:rect('.focus-content'),dock:rect('.mist-reading-actions'),composer:rect('.focus-bottom'),first:rect('.reader-side-toggle'),next:rect('.focus-reader__continue'),source:rect('.reading-group-source'),discussion:rect('.reading-group-discussion'),stream:rect('.focus-stream')};
 });
 const standard=await measure();assert.equal(standard.dock.width,1088);assert.equal(standard.content.width,standard.dock.width);assert.ok(Math.abs(standard.content.x-standard.dock.x)<1);assert.equal(standard.first.y,standard.next.y);
 await page.getByRole('button',{name:'宽幅',exact:true}).click();await wait();const wide=await measure();assert.ok(wide.content.width>standard.content.width);assert.equal(wide.dock.width,standard.dock.width);
 await page.getByRole('button',{name:'吸附讨论',exact:true}).click();await wait();
 assert.equal(await page.locator('.focus-reader').getAttribute('data-discussion-attached'),'true');
 const attached=await measure();assert.ok(attached.source.right<=attached.discussion.x);assert.ok(attached.discussion.right<=attached.content.right);assert.ok(attached.stream.scroll<=attached.stream.client);
 await page.getByRole('button',{name:'＋ 就这段提问',exact:true}).click();
 await page.getByRole('button',{name:'取消段落引用',exact:true}).click();
 await page.locator('#focus-question').fill('取消引用后的一般问题');
 assert.equal(await page.locator('.focus-reference').count(),0);
 const request=page.waitForRequest(r=>r.method()==='POST' && r.postData()?.includes('取消引用后的一般问题'));
 await page.getByRole('button',{name:'发送',exact:true}).click();const sent=(await request).postDataJSON();assert.equal(sent.receipt,null);assert.equal(sent.content,'取消引用后的一般问题');
 await page.getByRole('button',{name:'标准',exact:true}).click();await wait();const restored=await measure();assert.equal(restored.content.width,standard.content.width);assert.equal(restored.dock.width,standard.dock.width);assert.ok(restored.source.right<=restored.discussion.x);
 metrics.push({standard,wide,attached,restored,sent});
 for(const width of [1440,1280,1024,390]) {await page.setViewportSize({width,height:1000});await wait();const m=await measure();assert.ok(Math.abs(m.content.x-m.dock.x)<1);assert.equal(m.content.width,m.dock.width);assert.ok(m.stream.scroll<=m.stream.client);metrics.push({width,...m});}
 assert.deepEqual(errors,[]);console.log('PASS',JSON.stringify(metrics));
} finally {await browser.close();}
