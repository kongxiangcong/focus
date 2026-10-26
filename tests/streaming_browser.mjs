import assert from 'node:assert/strict';
const { chromium } = await import(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE});
try {
  const page = await browser.newPage({viewport:{width:1366,height:900}});
  await page.addInitScript(() => {
    window.streamSamples = []; window.displaySamples = [];
    const Native = window.EventSource;
    window.EventSource = class extends Native {
      constructor(...args) {
        super(...args);
        this.addEventListener('text', event => {
          const value = JSON.parse(event.data);
          const message = value.messages.find(m => m.messageId === 'browser-stream');
          if (message) window.streamSamples.push({length: message.content.length, received: performance.timeOrigin + performance.now()});
        });
      }
    };
    new MutationObserver(() => {
      const text = document.querySelector('[data-message-id="browser-stream"] .focus-markdown')?.textContent ?? '';
      if (text.length && !window.firstDisplay) window.firstDisplay = {length: text.length, time: performance.timeOrigin + performance.now()};
      if (text.length && text.length !== window.lastDisplay?.length) {
        window.lastDisplay = {length: text.length, time: performance.timeOrigin + performance.now()};
        window.displaySamples.push(window.lastDisplay);
      }
    }).observe(document, {childList:true,characterData:true,subtree:true});
  });
  await page.goto(process.env.FOCUS_TEST_URL + '/reading');
  await page.locator('[data-message-id="browser-stream"]').waitFor();
  console.log('READY');
  await page.waitForFunction(() => (document.querySelector('[data-message-id="browser-stream"] .focus-markdown')?.textContent.length ?? 0) >= 50);
  // Refresh during output exercises a new authoritative baseline and live continuation.
  const beforeReload = await page.evaluate(() => ({firstReceived:window.streamSamples[0],firstDisplay:window.firstDisplay}));
  await page.reload();
  await page.waitForFunction(() => document.querySelector('[data-message-id="browser-stream"] .focus-markdown')?.textContent === Array.from({length:300},(_,i)=>String.fromCharCode(0x4e00+i)).join(''));
  const result = await page.evaluate(() => ({samples:window.streamSamples, display:window.lastDisplay, displays:window.displaySamples}));
  const last = result.samples.at(-1);
  assert(last && last.length > 50, 'No real incremental SSE events after refresh');
  assert.equal(await page.locator('[data-message-id="browser-stream"]').count(), 1);
  const refreshText = await page.locator('[data-message-id="browser-stream"] .focus-markdown').textContent();
  assert(result.displays.length >= 10, 'Too few progressive DOM updates');
  assert(Math.max(...result.displays.slice(1).map((sample,i) => sample.time-result.displays[i].time)) < 1000, 'Display stalled for a second');
  assert.equal(refreshText, Array.from({length:300},(_,i)=>String.fromCharCode(0x4e00+i)).join(''));
  await page.reload();
  await page.waitForFunction(() => document.querySelector('[data-message-id="browser-stream"] .focus-markdown')?.textContent === Array.from({length:300},(_,i)=>String.fromCharCode(0x4e00+i)).join(''));
  console.log(JSON.stringify({beforeReload, eventSamples:result.samples.length, firstReceived:result.samples[0], lastReceived:last,
    displayed:result.display, displaySamples:result.displays.length, maxDisplayGapMs:Math.max(...result.displays.slice(1).map((sample,i) => sample.time-result.displays[i].time)), finalCharacters:300, exactOutput:true, reloadDuringStream:true, terminalReload:true}));
} finally { await browser.close(); }
