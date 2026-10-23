/** Fixture-only disclosure checks. Start reader:dev on FOCUS_BROWSER_PORT (5173). */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const {chromium}=createRequire(import.meta.url)(process.env.FOCUS_PLAYWRIGHT_MODULE);
const root=process.cwd(), dir=path.join(root,'ui/apps/standalone/tmp/discussion-fold');
fs.mkdirSync(dir,{recursive:true});
fs.writeFileSync(path.join(dir,'index.html'),'<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module" src="./main.tsx"></script></body></html>');
fs.writeFileSync(path.join(dir,'main.tsx'),`
import React,{useState} from 'react';import{createRoot}from'react-dom/client';
import{FocusReader}from'/@fs/${root}/ui/packages/reader-ui/src/FocusReader.tsx';
import'/@fs/${root}/ui/packages/reader-ui/src/focus-tokens.css';
const chunk={sourceId:'demo',planId:'p',chunkId:'c',index:1,total:2,sectionPath:['正文'],sourceLines:[1,2],sourceMarkdown:'完整正文保留。This is the original paragraph.',translation:null,images:[],relevantGlossary:[],presentationStatus:'source-ready'};
const answer=Array.from({length:55},(_,i)=>'讨论内容 '+i+'：这一段是用于真实几何验证的长回答。').join('\\n\\n');
let v={status:'reading',sessionId:'s',source:{sourceId:'demo',title:'Demo'},current:chunk,history:[],conversation:[{messageId:'a',chunkId:'c',role:'assistant',content:answer},{messageId:'b',chunkId:'c',role:'assistant',content:answer}],timeline:[{kind:'reading',eventId:'r1',chunk},{kind:'message',messageId:'a'},{kind:'reading',eventId:'r2',chunk},{kind:'message',messageId:'b'}]};
let emit;const ok=()=>({ok:true,value:{...v}});window.update=patch=>{v={...v,...patch};emit(ok())};window.stream=()=>{v={...v,agent:{models:[],run:{runId:'r',status:'running',approvals:[],activity:[]}}};emit(ok())};window.tick=()=>{v={...v,conversation:v.conversation.map((m,i)=>i?{...m,content:m.content+'\\n\\n更多增量内容'}:m)};emit(ok())};window.stops=0;
const host={getReadingWindow:async()=>ok(),subscribe:f=>{emit=f;return()=>{}},continueReading:async()=>ok(),sendMessage:async()=>ok(),stop:async()=>{window.stops++;v={...v,agent:undefined};return ok()}};
function App(){const[full,setFull]=useState(false);return <><style>{'html,body,#root{margin:0;height:100%}.wrap{height:100%}'}</style><div className="wrap"><FocusReader host={host} appearance="mist" fullscreen={full} onFullscreenChange={setFull}/></div></>};createRoot(document.getElementById('root')).render(<App/>);
`);
const browser=await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE});
const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
const url=`http://127.0.0.1:${process.env.FOCUS_BROWSER_PORT||5173}/tmp/discussion-fold/index.html`;
const buttons=()=>page.locator('.reading-discussion-divider button');
const settle=()=>page.waitForTimeout(850);
try{
 await page.goto(url);await buttons().first().waitFor();await settle();
 await buttons().first().click();assert.equal(await buttons().first().getAttribute('aria-expanded'),'false');assert.equal(await buttons().nth(1).getAttribute('aria-expanded'),'true');
 assert.equal(await page.locator('.reading-group-source').first().isVisible(),true);
 await page.reload();await buttons().first().waitFor();assert.equal(await buttons().first().getAttribute('aria-expanded'),'false');
 await page.evaluate(()=>window.update({sessionId:'other'}));assert.equal(await buttons().first().getAttribute('aria-expanded'),'true');
 await page.evaluate(()=>window.update({sessionId:'s'}));assert.equal(await buttons().first().getAttribute('aria-expanded'),'false');
 await page.evaluate(()=>window.stream());await buttons().nth(1).click();await settle();
 const before=await page.locator('.focus-stream').evaluate(e=>e.scrollTop);
 await page.evaluate(()=>{for(let i=0;i<5;i++)window.tick()});await settle();
 assert.equal(await buttons().nth(1).getAttribute('aria-expanded'),'false');assert.match(await buttons().nth(1).textContent(),/生成中/);
 assert.equal(await page.locator('[data-streaming="true"]').count(),0);
 assert.ok(Math.abs(await page.locator('.focus-stream').evaluate(e=>e.scrollTop)-before)<3);
 await page.getByRole('button',{name:'停止',exact:true}).click();assert.equal(await page.evaluate(()=>window.stops),1);
 // Native keyboard disclosure and focus retention, including hidden descendants.
 await buttons().nth(1).focus();await page.keyboard.press('Enter');await settle();assert.equal(await buttons().nth(1).getAttribute('aria-expanded'),'true');
 await page.keyboard.press('Space');await settle();assert.equal(await buttons().nth(1).getAttribute('aria-expanded'),'false');assert.equal(await buttons().nth(1).evaluate(e=>e===document.activeElement),true);
 await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>!!document.activeElement.closest('[hidden]')),false);
 // Programmatic close while reading the bottom of a long answer must return the retained trigger to view.
 await buttons().nth(1).click();await settle();await page.locator('.reading-group-discussion').nth(1).evaluate(e=>e.scrollIntoView({block:'end'}));
 await buttons().nth(1).evaluate(e=>e.click());await settle();
 const box=await buttons().nth(1).boundingBox(),pane=await page.locator('.focus-stream').boundingBox();assert.ok(box.y>=pane.y&&box.y+box.height<=pane.y+pane.height);
 await page.getByRole('textbox').fill('新问题');await page.getByRole('button',{name:'发送',exact:true}).click();await settle();assert.equal(await buttons().nth(1).getAttribute('aria-expanded'),'true');
 for(const theme of ['light','dark'])for(const width of [1440,390,320]){
  await page.setViewportSize({width,height:844});await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);await page.emulateMedia({reducedMotion:'reduce'});
  await buttons().first().click();await settle();await buttons().first().click();await settle();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert.equal(await buttons().first().evaluate(e=>getComputedStyle(e.parentElement,'::before').borderTopStyle),'dashed');
  await buttons().first().scrollIntoViewIfNeeded();await settle();
  fs.mkdirSync(path.join(root,'tmp/test-runs/discussion-fold'),{recursive:true});
  await page.screenshot({path:path.join(root,`tmp/test-runs/discussion-fold/${theme}-${width}.png`)});
 }
 const full=page.getByRole('button',{name:'全屏',exact:true});assert.equal(await full.count(),1);await full.click();assert.equal(await page.getByRole('button',{name:'退出全屏',exact:true}).count(),1);await buttons().first().click();await settle();
 assert.deepEqual(errors,[]);console.log(JSON.stringify({browser:browser.version(),passed:['independent/repeated chunk','refresh/session isolation','streaming/stop/no scroll drift','keyboard/hidden tab','long-answer bottom geometry','send expansion','light/dark/320/390/1440/reduced-motion/fullscreen'],errors}));
}finally{await browser.close();fs.rmSync(dir,{recursive:true,force:true})}
