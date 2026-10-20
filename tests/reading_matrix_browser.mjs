import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE);
const browser=await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE});
const output=process.env.FOCUS_BROWSER_OUTPUT;fs.mkdirSync(output,{recursive:true});const selectedWidth=Number(process.env.FOCUS_MATRIX_WIDTH || 0);const results=selectedWidth && fs.existsSync(path.join(output,'matrix.json')) ? JSON.parse(fs.readFileSync(path.join(output,'matrix.json'),'utf8')).filter(r=>!r.name.startsWith(`${selectedWidth}-`)) : [];
try {
 for(const width of [390,768,1024,1440]) for(const theme of ['light','dark']) for(const reduced of [false,true]) for(const fullscreen of [false,true]) {
  if(selectedWidth && width!==selectedWidth)continue;
  const name=`${width}-${theme}-${reduced?'reduced':'normal'}-${fullscreen?'fullscreen':'window'}`;
  const context=await browser.newContext({viewport:{width,height:1000},colorScheme:theme,reducedMotion:reduced?'reduce':'no-preference',recordVideo:{dir:output,size:{width,height:1000}}});
  await context.addInitScript(({theme,reduced})=>{localStorage.setItem('focus.theme',theme);localStorage.setItem('focus.reducedMotion',String(reduced));},{theme,reduced});
  const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}/reading`);await page.waitForSelector('.workspace-app');
  const enter=page.getByRole('button',{name:'进入正文',exact:true});if(await enter.count())await enter.click();await page.waitForSelector('.focus-reading');
  if(fullscreen)await page.getByRole('button',{name:'全屏',exact:true}).click();
  await page.waitForTimeout(700);
  const geometry=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,controlsMin:Math.min(...Array.from(document.querySelectorAll('.mist-reading-actions > button')).filter(el=>el.checkVisibility()).map(el=>el.getBoundingClientRect().height)),bodyWidth:document.querySelector('.focus-reading .focus-markdown').getBoundingClientRect().width,theme:document.documentElement.dataset.theme,reduced:document.documentElement.dataset.reducedMotion,fullscreen:document.querySelector('.workspace-app').className}));
  assert.equal(geometry.overflow,false,name);if(width<600)assert.ok(geometry.controlsMin>=40,JSON.stringify({name,...geometry}));assert.equal(geometry.theme,theme);assert.equal(geometry.reduced,String(reduced));
  await page.screenshot({path:path.join(output,`${name}.png`)});
  // Record interaction as well as the settled page for every combination.
  await page.locator('.reader-side-toggle').click();await page.waitForTimeout(350);await page.getByRole('button',{name:'关闭阅读侧栏',exact:true}).click();
  await page.waitForTimeout(350);await page.getByRole('button',{name:'当前阅读位置',exact:true}).click();await page.waitForTimeout(300);await page.keyboard.press('Escape');await page.waitForTimeout(250);
  const video=page.video();await context.close();await video.saveAs(path.join(output,`${name}.webm`));await video.delete();
  assert.deepEqual(errors,[],name);results.push({name,...geometry,screenshot:`${name}.png`,video:`${name}.webm`});fs.writeFileSync(path.join(output,'matrix.json'),JSON.stringify(results,null,2));console.log('PASS',name);
 }
 fs.writeFileSync(path.join(output,'matrix.json'),JSON.stringify(results,null,2));
} finally {await browser.close();}
