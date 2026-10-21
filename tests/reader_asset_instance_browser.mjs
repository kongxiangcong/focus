import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import fs from 'node:fs';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser=await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE,args:['--no-sandbox','--disable-dev-shm-usage','--no-zygote']});
const out=process.env.FOCUS_BROWSER_OUTPUT || '/tmp/focus-assets';fs.mkdirSync(out,{recursive:true});
try {
 for(const [width,height] of [[1600,1000],[1280,800],[1024,768],[390,844]]) for(const theme of ['light','dark']) {
  const context=await browser.newContext({viewport:{width,height},hasTouch:width===390,colorScheme:theme,reducedMotion:'reduce'});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}/reading`);
  await page.evaluate(theme=>{document.documentElement.dataset.theme=theme;},theme);
  await page.waitForSelector('.focus-reader');await page.waitForTimeout(500);
  const enter=page.getByRole('button',{name:'进入正文',exact:true});if(await enter.count()) await enter.click();else if(!await page.locator('.reader-thumbnail img').count()) await page.getByRole('button',{name:/^继续/}).click();
  const thumbnail=page.locator('.reader-thumbnail img').first();await thumbnail.waitFor();await thumbnail.scrollIntoViewIfNeeded();
  await page.waitForFunction(()=>document.querySelector('.reader-thumbnail img')?.naturalWidth>0);
  await thumbnail.click();await page.getByRole('dialog',{name:'图片放大'}).waitFor();
  await page.waitForFunction(()=>document.querySelector('.reader-image-viewport img')?.naturalWidth>0);
  await page.getByRole('button',{name:'关闭放大'}).click();
  await page.locator('.reader-thumbnail').first().getByRole('button',{name:'在资料栏固定'}).click();
  await page.waitForFunction(()=>document.querySelector('.reader-figure-zoom img')?.naturalWidth>0);
  for(const image of await page.locator('.reader-thumbnail img,.reader-figure-zoom img').all()) {
   assert.ok(await image.evaluate(el=>el.naturalWidth>0));const src=await image.getAttribute('src');assert.equal((await page.request.get(new URL(src,page.url()).href)).status(),200);
  }
  await page.screenshot({path:`${out}/${width}-${height}-${theme}.png`});assert.deepEqual(errors,[]);await context.close();
 }
 console.log('PASS asset thumbnail/viewer/gallery HTTP 200 and naturalWidth; browser',browser.version());
} finally {await browser.close();}
