import assert from 'node:assert/strict';
const {chromium} = await import(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({headless:true,executablePath:process.env.FOCUS_CHROMIUM_EXECUTABLE});
const page = await browser.newPage({viewport:{width:1366,height:768}});
const tasks = page.getByRole('region', { name: '任务框' });
const toggle = page.getByRole('button', { name: '任务详情', exact: true });
try {
  await page.goto(process.env.FOCUS_TEST_URL + '/library');
  await page.getByRole('heading',{name:/^知识库(?:\s*\d+)?$/}).waitFor();
  await toggle.click();
  await tasks.getByText('failed.pdf',{exact:true}).waitFor({state:'attached'});
  assert.equal(await page.getByText('completed.pdf',{exact:true}).count(),0);
  await page.getByRole('button',{name:'全部清空',exact:true}).click();
  await page.getByText('failed.pdf',{exact:true}).first().waitFor({state:'detached'});
  assert.equal(await page.getByText('completed.pdf',{exact:true}).count(),0);
  assert.equal(await tasks.getByText('waiting.pdf',{exact:true}).count(),1);
  await page.reload();
  await toggle.click();
  await tasks.getByText('waiting.pdf',{exact:true}).waitFor();
  assert.equal(await page.getByText('failed.pdf',{exact:true}).count(),0);
  assert.equal(await page.getByText('completed.pdf',{exact:true}).count(),0);
  assert.equal(await page.getByRole('alert').count(),0);
  await page.getByRole('button',{name:'上传',exact:true}).click();
  assert.equal(await page.getByRole('combobox',{name:'专题',exact:true}).inputValue(),'');
  await page.screenshot({path:'tmp/status-clear-browser.png',fullPage:true});
  console.log('PASS: successful uploads are hidden and bulk clear removes failed statuses across reload');
} finally { await browser.close(); }
