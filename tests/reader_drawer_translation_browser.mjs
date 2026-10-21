// Width is now a reader preference. Drawer width invariants replace the superseded disjoint desktop columns.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE,args:['--no-sandbox','--no-zygote']});
const output=process.env.FOCUS_BROWSER_OUTPUT||'/tmp/focus-drawer';fs.mkdirSync(output,{recursive:true});
const page=await browser.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'});
const wait=()=>page.waitForTimeout(150);
const rect=selector=>page.locator(selector).first().evaluate(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height,scroll:e.scrollWidth,client:e.clientWidth};});
try {
 await page.goto(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}/reading`);await page.waitForSelector('.focus-reading');
 await page.getByRole('link',{name:'设置',exact:true}).click();assert.equal(await page.getByRole('slider',{name:'标准阅读宽度'}).count(),0);
 await page.getByRole('link',{name:'阅读',exact:true}).click();await page.getByRole('button',{name:'全屏',exact:true}).click();
 await page.getByRole('button',{name:'行宽',exact:true}).click();await page.getByRole('radio',{name:'宽',exact:true}).click();await page.keyboard.press('Escape');
 await page.reload();await page.waitForSelector('.focus-reading');await page.getByRole('button',{name:'全屏',exact:true}).click();assert.equal(await page.evaluate(()=>localStorage.getItem('focus.readingMeasure')),'wide');
 for(const [width,height] of [[1600,1000],[1280,800],[1024,768],[390,844]]) for(const theme of ["light","dark"]) {
  await (await page.context().newCDPSession(page)).send('Emulation.setTouchEmulationEnabled',{enabled:width===390,maxTouchPoints:1});await page.setViewportSize({width,height});await page.emulateMedia({colorScheme:theme});await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);await wait();
  const before=await rect('.reading-group-source'),dock=await rect('.mist-reading-actions');
  await page.getByRole('button',{name:'资料',exact:true}).click();await wait();
  const drawer=await rect('.reader-left-drawer'),stream=await rect('.focus-stream'),source=await rect('.reading-group-source');
  assert.ok(drawer.width>0&&drawer.height>0&&source.width>0&&stream.height>0);
  assert.ok(Math.abs(before.width-source.width)<1,JSON.stringify({width,before,source}));
  assert.equal((await rect('.mist-reading-actions')).width,dock.width);
  if(width<=720) assert.ok(drawer.bottom<=stream.y+1);
  const shift=await page.locator('.focus-reader').evaluate(e=>parseFloat(e.style.getPropertyValue('--reader-shift')));
  if(shift>0) assert.ok(source.x>=drawer.right-1,JSON.stringify({width,source,drawer,shift}));
  await page.screenshot({path:`${output}/${width}-${height}-${theme}.png`});
  assert.ok(drawer.scroll<=drawer.client+1);assert.ok(stream.scroll<=stream.client+1);
  await page.getByRole('button',{name:'关闭阅读侧栏',exact:true}).click();await wait();assert.equal((await rect('.reading-group-source')).width,before.width);
 }
 console.log('PASS persisted measure, unchanged drawer/text/dock widths, mobile stacking and overflow');
}finally{await browser.close();}
