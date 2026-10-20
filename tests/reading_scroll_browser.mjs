import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const base = `http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT || 8875}`;
const output = process.env.FOCUS_BROWSER_OUTPUT || '/tmp/focus-reader-redesign/shots/step5';
fs.mkdirSync(output, {recursive:true});
const errors=[]; page.on('pageerror',e=>errors.push(e.message));
const metrics={};
const sleep=ms=>page.waitForTimeout(ms);
const position=()=>page.locator('.focus-stream').evaluate(el=>el.scrollTop);
const landing=()=>page.evaluate(()=>{const p=document.querySelector('.focus-stream'),g=document.querySelector('[data-reading-group]:last-of-type');return {error:g.getBoundingClientRect().top-p.getBoundingClientRect().top-Math.max(24,p.clientHeight*.1),height:g.offsetHeight,viewport:p.clientHeight};});
try {
 await page.goto(`${base}/reading`);
 await page.getByRole('button',{name:'进入正文',exact:true}).click(); await page.waitForSelector('[data-reading-group]'); await sleep(850);
 for(let n=2;n<=3;n++) {
  await page.getByRole('button',{name:'继续',exact:true}).click();
  await page.waitForFunction(n=>document.querySelector(`[data-lens-index="${n}"]`),n); await sleep(850);
  metrics[`landing${n}`]=await landing(); assert.ok(Math.abs(metrics[`landing${n}`].error)<=2,JSON.stringify(metrics));
 }
 assert.ok(metrics.landing2.height > metrics.landing2.viewport);
 assert.ok(metrics.landing3.height < metrics.landing3.viewport);
 await page.screenshot({path:`${output}/short-landing.png`});
 const group=page.locator('[data-lens-index="3"]');
 const top=()=>group.evaluate(el=>el.getBoundingClientRect().top);
 let before=await top();
 await page.getByRole('button',{name:'收起',exact:true}).click(); await sleep(900);
 metrics.collapse=(await top())-before; assert.ok(Math.abs(metrics.collapse)<=1,JSON.stringify(metrics));
 before=await top(); await page.getByRole('button',{name:'提问',exact:true}).click(); await sleep(900);
 metrics.expand=(await top())-before; assert.ok(Math.abs(metrics.expand)<=1,JSON.stringify(metrics));
 before=await top();
 for(let n=0;n<3;n++) {await page.locator('.reader-side-toggle').click(); await sleep(300);await page.locator('.reader-side-toggle').click(); await sleep(300);}
 metrics.materials=(await top())-before; assert.ok(Math.abs(metrics.materials)<=2,JSON.stringify(metrics));
 // Scroll to earlier text, then use the visual progress link and return.
 await page.locator('.focus-stream').evaluate(p=>{p.dispatchEvent(new WheelEvent('wheel',{bubbles:true,deltaY:-1}));p.scrollTop=0;}); await sleep(900);
 before=await position();
 await page.getByRole('button',{name:'回到进度',exact:true}).click();await sleep(600);
 await page.getByRole('button',{name:'↩ 返回刚才位置',exact:true}).click();await sleep(600);
 metrics.return=(await position())-before;assert.ok(Math.abs(metrics.return)<=1,JSON.stringify(metrics));
 await page.locator('#focus-question').fill('请解释滚动跟随验收'); await page.getByRole('button',{name:'发送 ↑',exact:true}).click();
 await page.waitForSelector('[data-streaming="true"]');
 await page.locator('.focus-stream').hover();await page.mouse.wheel(0,-100);
 await page.getByRole('button',{name:/回到最新/}).waitFor();
 before=await position();await sleep(250);metrics.paused=(await position())-before;assert.ok(Math.abs(metrics.paused)<=1,JSON.stringify(metrics));
 metrics.latestEntryWithinPane=await page.getByRole('button',{name:/回到最新/}).evaluate(el=>{const a=el.getBoundingClientRect(),p=document.querySelector('.focus-stream').getBoundingClientRect();return a.bottom<=p.bottom && a.top>=p.top;});
 assert.ok(metrics.latestEntryWithinPane);
 await page.screenshot({path:`${output}/stream-paused.png`});
 await page.getByRole('button',{name:/回到最新/}).click();await sleep(650);
 assert.equal(await page.getByRole('button',{name:/回到最新/}).count(),0);
 metrics.latest=await page.evaluate(()=>{const p=document.querySelector('.focus-stream'),a=p.querySelector('[data-streaming="true"]'); return a ? a.getBoundingClientRect().bottom-p.getBoundingClientRect().bottom : 0;});
 assert.ok(Math.abs(metrics.latest + 24)<=2,JSON.stringify(metrics));
 await sleep(1800);
 for(const width of [1440,1024,390]) {await page.setViewportSize({width,height:1000});for(const theme of ['light','dark']){await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);await sleep(400);await page.screenshot({path:`${output}/${width}-${theme}.png`});}}
 assert.deepEqual(errors,[]); fs.writeFileSync(`${output}/metrics.json`,JSON.stringify(metrics,null,2));console.log('PASS',metrics);
} finally {await browser.close();}
