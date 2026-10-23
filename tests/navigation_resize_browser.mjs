import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE);
const browser=await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(()=>localStorage.setItem('focus.navigation','expanded'));
const handle=()=>page.getByRole('separator',{name:'调整工作台导航宽度'});
const nav=()=>page.getByRole('complementary',{name:'工作台导航'});
const width=()=>nav().evaluate(e=>e.getBoundingClientRect().width);
const wait=()=>page.waitForTimeout(150);
async function drag(delta,finish='up') {
 const b=await handle().boundingBox();const x=b.x+b.width/2,y=b.y+b.height/2;
 await page.mouse.move(x,y);await page.mouse.down();await page.mouse.move(x+delta,y,{steps:8});await wait();
 const during=await width();
 if(finish==='escape')await page.keyboard.press('Escape');
 else if(finish==='cancel')await handle().dispatchEvent('pointercancel',{pointerId:1});
 else if(finish==='lost')await handle().evaluate(e=>e.releasePointerCapture(1));
 await page.mouse.up();await wait();return during;
}
try {
 await page.goto(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT||5173}/reading`);await handle().waitFor();await wait();
 assert.equal(await width(),288);
 assert.equal(await handle().evaluate(e=>getComputedStyle(e).cursor),'col-resize');
 assert.equal(await drag(2),288);assert.equal(await width(),288);
 assert.equal(await drag(80),368);assert.equal(await width(),368);
 assert.equal(await page.locator('.workspace-app').getAttribute('data-nav-resizing'),null);
 assert.equal(await drag(500),420);assert.equal(await width(),420);
 assert.equal(await drag(-500),240);assert.equal(await width(),240);
 await handle().focus();await page.keyboard.press('Enter');assert.equal(await width(),288);
 assert.equal(await drag(70,'escape'),358);assert.equal(await width(),288);
 assert.equal(await drag(70,'cancel'),358);assert.equal(await width(),288);
 assert.equal(await drag(70,'lost'),358);assert.equal(await width(),288);
 await handle().focus();await page.keyboard.press('ArrowRight');assert.equal(await width(),304);
 await page.keyboard.press('End');assert.equal(await width(),420);
 await page.setViewportSize({width:800,height:900});await wait();assert.equal(await width(),320);
 assert.equal(await handle().getAttribute('aria-valuemax'),'320');
 await page.setViewportSize({width:1440,height:1000});await wait();assert.equal(await width(),420);
 await page.getByRole('button',{name:'收起导航',exact:true}).click();assert.equal(await width(),56);assert.equal(await handle().count(),0);
 await page.getByRole('button',{name:'展开导航',exact:true}).click();assert.equal(await width(),420);
 for(const theme of ['light','dark']) {
  await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
  await handle().focus();await page.keyboard.press('Home');assert.equal(await width(),240);
  assert.equal(await handle().evaluate(e=>getComputedStyle(e).outlineStyle),'solid');
  await page.keyboard.press('Enter');assert.equal(await width(),288);
 }
 await page.emulateMedia({reducedMotion:'reduce'});assert.equal(await drag(40),328);
 await page.setViewportSize({width:390,height:844});await wait();assert.equal(await handle().count(),0);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.ok(await width()<=390);
 await page.getByRole('button',{name:'收起导航',exact:true}).click();await page.getByRole('button',{name:'展开导航',exact:true}).click();
 await page.setViewportSize({width:1440,height:1000});await wait();assert.equal(await width(),328);
 await page.getByRole('button',{name:'全屏',exact:true}).click();assert.equal(await handle().count(),0);
 await page.getByRole('button',{name:'关闭全屏模式',exact:true}).click();await wait();assert.equal(await width(),328);
 await page.getByRole('link',{name:'设置',exact:true}).click();assert.equal(await width(),328);
 await page.getByRole('link',{name:'阅读',exact:true}).click();assert.equal(await width(),328);
 await page.reload();await handle().waitFor();assert.equal(await width(),288);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({browser:browser.version(),passed:['real drag/threshold/min/max','pointer up/cancel/lost capture/Escape','keyboard/focus/reset','container clamp','collapse/expand','light/dark','reduced motion','390px top navigation','reading fullscreen','route width retention/refresh default'],errors}));
}finally{await browser.close();}
