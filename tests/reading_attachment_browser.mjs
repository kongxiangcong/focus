import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.FOCUS_PLAYWRIGHT_MODULE);
const browser=await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
page.setDefaultTimeout(60000);
const out=process.env.FOCUS_BROWSER_OUTPUT || '/tmp/focus-reader-redesign/shots/step6'; fs.mkdirSync(out,{recursive:true});
const metrics={}, errors=[];page.on('pageerror',e=>errors.push(e.message));
const wait=()=>page.waitForTimeout(850);
const button=page.getByRole('button',{name:'吸附讨论',exact:true});
const attached=()=>page.locator('.focus-reader').getAttribute('data-discussion-attached');
const width=()=>page.locator('[data-lens-index="2"] .focus-reading .focus-markdown').first().evaluate(e=>e.getBoundingClientRect().width);
try {
 await page.goto(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}/reading`);
 await page.getByRole('button',{name:'进入正文',exact:true}).click();await wait();
 await page.getByRole('button',{name:'继续',exact:true}).click();await page.waitForSelector('[data-lens-index="2"]');await wait();
 assert.equal(await button.getAttribute('aria-pressed'),'false');
 // The workbench may reserve navigation width; fullscreen exposes the 1440px reading area.
 await page.getByRole('button',{name:'全屏',exact:true}).click();await wait();
 await page.locator('.focus-stream').evaluate(p=>{p.dispatchEvent(new WheelEvent('wheel',{bubbles:true,deltaY:-1}));p.scrollTop+=400;});await wait();
 const anchor=page.locator('[data-lens-index="2"] .focus-markdown > p').filter({hasText:'Paragraph 8:'}).first();
 const top=()=>anchor.evaluate(e=>e.getBoundingClientRect().top);
 for(const mode of ['on','off','onAgain']) {const before=await top();await button.click();await wait();metrics[mode]={error:(await top())-before,width:await width()};assert.ok(Math.abs(metrics[mode].error)<=2,JSON.stringify(metrics));assert.equal(metrics[mode].width,720);}
 assert.equal(await attached(),'true');
 metrics.sticky=await page.locator('[data-lens-index="2"] .reading-group-discussion').evaluate(e=>e.getBoundingClientRect().top-document.querySelector('.focus-stream').getBoundingClientRect().top);
 assert.ok(Math.abs(metrics.sticky-14)<=1,JSON.stringify(metrics));
 await page.screenshot({path:`${out}/1440-sticky.png`});
 await page.getByRole('button',{name:'＋ 就这段提问',exact:true}).click();await wait();assert.match(await page.locator('.focus-reference').innerText(),/引用第 2 段/);assert.equal(await page.locator('#focus-question').evaluate(e=>e===document.activeElement),true);
 await page.locator('.reader-side-toggle').click();await wait();assert.equal(await attached(),'false');assert.match(await button.getAttribute('title'),/资料/);assert.equal(await width(),720);
 await page.locator('.reader-side-toggle').click();await wait();assert.equal(await attached(),'true');
 await page.setViewportSize({width:1100,height:1000});await wait();assert.equal(await attached(),'false');assert.equal(await button.getAttribute('aria-pressed'),'true');assert.match(await button.getAttribute('title'),/1240/);assert.equal(await width(),720);
 await page.setViewportSize({width:1440,height:1000});await wait();assert.equal(await attached(),'true');
 await page.reload();await wait();assert.equal(await button.getAttribute('aria-pressed'),'true');
 if(await attached()!=='true') {await page.getByRole('button',{name:'全屏',exact:true}).click();await wait();}
 await page.locator('#focus-question').fill('讨论吸附验收');await page.getByRole('button',{name:'发送 ↑',exact:true}).click();await page.waitForFunction(index=>{const group=document.querySelector(`[data-lens-index="${index}"]`);return group?.querySelector('[data-role="assistant"]')?.textContent.includes('回复第20句') && !group.querySelector('[data-streaming="true"]');},2);
 await page.locator('[data-lens-index="2"]').evaluate(e=>{const p=document.querySelector('.focus-stream');p.dispatchEvent(new WheelEvent('wheel',{bubbles:true,deltaY:-1}));p.scrollTop+=e.getBoundingClientRect().top-p.getBoundingClientRect().top+250;});await wait();
 metrics.messageSticky=await page.locator('[data-lens-index="2"] .reading-group-discussion').evaluate(e=>e.getBoundingClientRect().top-document.querySelector('.focus-stream').getBoundingClientRect().top);
 assert.ok(Math.abs(metrics.messageSticky-14)<=1,JSON.stringify(metrics));await page.screenshot({path:`${out}/1440-discussion-sticky.png`});
 // A reply taller than a short source must grow the group, with source top-aligned.
 await page.getByRole('button',{name:'继续',exact:true}).click();await page.waitForSelector('[data-lens-index="3"]');await wait();
 await page.locator('#focus-question').fill('短段落的长讨论验收');await page.getByRole('button',{name:'发送 ↑',exact:true}).click();await page.waitForFunction(index=>{const group=document.querySelector(`[data-lens-index="${index}"]`);return group?.querySelector('[data-role="assistant"]')?.textContent.includes('回复第20句') && !group.querySelector('[data-streaming="true"]');},3);
 metrics.tallReply=await page.locator('[data-lens-index="3"]').evaluate(e=>{const s=e.querySelector('.reading-group-source'),d=e.querySelector('.reading-group-discussion');return {group:e.offsetHeight,source:s.offsetHeight,discussion:d.offsetHeight,alignment:s.getBoundingClientRect().top-e.getBoundingClientRect().top};});
 assert.ok(metrics.tallReply.discussion>metrics.tallReply.source,JSON.stringify(metrics.tallReply));assert.ok(metrics.tallReply.group>=metrics.tallReply.discussion);assert.equal(metrics.tallReply.alignment,0);
 await page.locator('[data-lens-index="3"]').evaluate(e=>{const p=document.querySelector('.focus-stream');p.dispatchEvent(new WheelEvent('wheel',{bubbles:true,deltaY:-1}));p.scrollTop+=e.getBoundingClientRect().top-p.getBoundingClientRect().top-100;});await wait();
 const third=page.locator('[data-lens-index="3"] .focus-markdown > p').first();
 for(const mode of ['withMessagesOff','withMessagesOn']) {const before=await third.evaluate(e=>e.getBoundingClientRect().top);await button.click();await wait();metrics[mode]=(await third.evaluate(e=>e.getBoundingClientRect().top))-before;assert.ok(Math.abs(metrics[mode])<=2,JSON.stringify(metrics));}
 await page.emulateMedia({reducedMotion:'reduce'});await button.click();await button.click();await wait();
 metrics.reduced=await page.locator('[data-lens-index="3"] .reading-group-discussion').evaluate(e=>({animation:getComputedStyle(e).animationName,lensTransition:getComputedStyle(document.querySelector('.reading-lens')).transitionDuration}));
 assert.equal(metrics.reduced.animation,'none');assert.equal(metrics.reduced.lensTransition,'0s');await page.screenshot({path:`${out}/1440-reduced-motion.png`});
 await page.emulateMedia({reducedMotion:'no-preference'});
 metrics.longDiscussion=await page.locator('[data-lens-index="2"]').evaluate(e=>({group:e.offsetHeight,source:e.querySelector('.reading-group-source').offsetHeight,discussion:e.querySelector('.reading-group-discussion').offsetHeight}));
 for(const w of [1440,1024,390]) {await page.setViewportSize({width:w,height:1000});for(const theme of ['light','dark']) {await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);await wait();await page.screenshot({path:`${out}/${w}-${theme}.png`});} if(w===390)assert.equal(await button.isVisible(),false);}
 assert.deepEqual(errors,[]);fs.writeFileSync(`${out}/metrics.json`,JSON.stringify(metrics,null,2));console.log('PASS',metrics);
} finally {await browser.close();}
