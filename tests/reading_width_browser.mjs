// Four measures replace the old standard/wide toggle; reference removal remains a business regression.
import './reading_measure_browser.mjs';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE,args:['--no-sandbox','--no-zygote']});
try {
 const page=await browser.newPage({viewport:{width:1600,height:1000}});
 await page.goto(`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT}/reading`);await page.waitForSelector('.focus-reading');
 await page.locator('.focus-reading').first().getByRole('button',{name:'引用提问',exact:true}).click();
 await page.getByRole('button',{name:'取消段落引用',exact:true}).click();
 await page.locator('#focus-question').fill('取消引用后的一般问题');assert.equal(await page.locator('.focus-reference').count(),0);
 const request=page.waitForRequest(r=>r.method()==='POST'&&r.postData()?.includes('取消引用后的一般问题'));
 await page.getByRole('button',{name:'发送',exact:true}).click();const sent=(await request).postDataJSON();
 assert.equal(sent.receipt,null);assert.equal(sent.content,'取消引用后的一般问题');
 console.log('PASS width controls and cancelled Source Anchor request');
}finally{await browser.close();}
