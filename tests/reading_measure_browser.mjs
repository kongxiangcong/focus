import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import fs from 'node:fs';
const require=createRequire(import.meta.url),{chromium}=require(process.env.FOCUS_PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE,args:['--no-sandbox','--disable-dev-shm-usage','--no-zygote']});
const output=process.env.FOCUS_BROWSER_OUTPUT||'/tmp/focus-measure';fs.mkdirSync(output,{recursive:true});
try {
 for(const [width,height] of [[1600,1000],[1280,800],[1024,768],[390,844]]) for(const theme of ['light','dark']) {
  const ctx=await browser.newContext({viewport:{width,height},hasTouch:width===390,reducedMotion:'reduce',colorScheme:theme});
  await ctx.addInitScript(()=>localStorage.getItem('focus.readingMeasure')||localStorage.setItem('focus.readingMeasure','standard'));
  const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}/reading`);
  await page.waitForSelector('.focus-reading');await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
  const trigger=page.getByRole('button',{name:'行宽',exact:true});await trigger.click();
  const radios=page.getByRole('radiogroup',{name:'阅读行宽'});assert.equal(await radios.getByRole('radio').count(),4);
  const bounds=await radios.boundingBox();assert.ok(bounds.x>=0&&bounds.y>=0&&bounds.x+bounds.width<=width,JSON.stringify(bounds));
  const metrics=await page.locator('.focus-reader').evaluate(el=>({width:parseFloat(el.style.getPropertyValue('--reader-available-width')),size:parseFloat(getComputedStyle(el).getPropertyValue('--reader-reading-size'))}));
  for(const [name,count] of [['窄',36],['标准',42],['宽',50],['超宽',62]]) {
   const button=radios.getByRole('radio',{name,exact:true});assert.equal(await button.isDisabled(),count*metrics.size+48>metrics.width);
   if(await button.isEnabled()) {await button.click();assert.equal(await button.getAttribute('aria-checked'),'true');}
  }
  await page.screenshot({path:`${output}/${width}-${height}-${theme}.png`});
  await page.keyboard.press('Escape');assert.equal(await radios.count(),0);assert.ok(await trigger.evaluate(e=>e===document.activeElement));
  const preference=await page.evaluate(()=>localStorage.getItem('focus.readingMeasure'));
  await page.reload();await page.waitForSelector('.focus-reading');
  assert.equal(await page.evaluate(()=>localStorage.getItem('focus.readingMeasure')),preference);
  await page.setViewportSize({width:1600,height:1000});await page.waitForTimeout(100);
  assert.equal(await page.locator('.focus-reader').getAttribute('data-reading-measure'),preference);
  assert.deepEqual(errors,[]);await ctx.close();
 }
 console.log('PASS four measures, availability, popover geometry, Escape/focus, 8 viewport/theme screenshots;',browser.version());
}finally{await browser.close();}
