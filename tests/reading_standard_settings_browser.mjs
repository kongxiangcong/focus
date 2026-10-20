import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE);
const browser=await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE});
const page=await browser.newPage({viewport:{width:1600,height:1000}});
const wait=()=>page.waitForTimeout(700);
const metrics=[];
try {
 await page.goto(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}/reading`);
 await page.getByRole('button',{name:'进入正文',exact:true}).click();await wait();
 await page.getByRole('link',{name:'设置',exact:true}).click();
 const slider=page.getByRole('slider',{name:'标准阅读宽度',exact:true});
 await slider.fill('1200');await page.getByRole('button',{name:'保存外观',exact:true}).click();
 await page.reload();await slider.waitFor();assert.equal(await slider.inputValue(),'1200');
 await page.getByRole('link',{name:'阅读',exact:true}).click();
 await page.getByRole('button',{name:'全屏',exact:true}).click();await wait();
 const rect=selector=>page.locator(selector).first().evaluate(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height,scroll:e.scrollWidth,client:e.clientWidth};});
 const standard=await rect('.reading-group-source');assert.equal(standard.width,1200);
 const dock=await rect('.mist-reading-actions');assert.equal(dock.width,1248);
 await page.getByRole('button',{name:'资料',exact:true}).click();await wait();
 for(const width of [1600,1440,1024,800,600,390]) {
  await page.setViewportSize({width,height:1000});await wait();
  const drawer=await rect('.reader-left-drawer'),stream=await rect('.focus-stream'),source=await rect('.reading-group-source');
  assert.ok(drawer.width>0 && drawer.height>0 && source.width>0 && stream.height>0);
  assert.ok(drawer.right<=stream.x+1 || drawer.bottom<=stream.y+1,JSON.stringify({width,drawer,stream}));
  assert.ok(drawer.scroll<=drawer.client,JSON.stringify({width,drawer}));
  assert.ok(stream.scroll<=stream.client,JSON.stringify({width,stream}));
  metrics.push({width,drawer,stream,source});
 }
 await page.setViewportSize({width:1600,height:1000});await wait();
 assert.equal((await rect('.mist-reading-actions')).width,dock.width);
 await page.getByRole('button',{name:'收起资料',exact:true}).click();await wait();
 assert.equal((await rect('.reading-group-source')).width,1200);
 await page.getByRole('button',{name:'宽幅',exact:true}).click();await wait();
 assert.ok((await rect('.reading-group-source')).width>1200);
 assert.equal((await rect('.mist-reading-actions')).width,dock.width);
 await page.getByRole('button',{name:'资料',exact:true}).click();await wait();
 await page.getByRole('button',{name:'标准',exact:true}).click();await wait();
 assert.ok((await rect('.reader-left-drawer')).right <= (await rect('.focus-stream')).x);
 await page.getByRole('button',{name:'收起资料',exact:true}).click();await wait();
 assert.equal((await rect('.reading-group-source')).width,1200);
 console.log('PASS',JSON.stringify(metrics));
} finally {await browser.close();}
