import assert from 'node:assert/strict';
const { chromium } = await import(process.env.FOCUS_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE });
const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
const base = process.env.FOCUS_TEST_URL;
const scenario = process.env.FOCUS_TEST_SCENARIO;
const value = async path => (await (await page.request.get(base + path)).json()).value;
try {
  await page.goto(base + '/library');
  await page.getByRole('button', { name: '任务详情', exact: true }).click();
  await page.getByRole('region', { name: '任务框' }).getByText(scenario + '.pdf', { exact: true }).waitFor({ state: 'attached' });
  await page.getByRole('button', { name: '全部清空', exact: true }).click();
  await page.getByText('没有进行中或待处理的任务。', { exact: true }).waitFor();
  await page.getByRole('button', { name: '任务详情', exact: true }).click();
  for (const [name, retryLabel] of [[scenario, scenario === 'single' ? '重试解析' : '重试未完成步骤']]) {
    await page.getByRole('button', { name: '上传', exact: true }).click();
    await page.getByLabel('上传材料', { exact: true }).setInputFiles({ name: name + '.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF ' + name) });
    await page.getByRole('button', { name: '开始解析并生成博客', exact: true }).click();
    const panel = page.getByRole('region', { name: '任务框' });
    const retry = panel.getByRole('button', { name: retryLabel, exact: true });
    await retry.waitFor();
    await page.waitForFunction(label => document.activeElement?.textContent === label, retryLabel);
    assert.equal(await panel.getByText('sibling.pdf', { exact: true }).count(), 0);
    assert.equal((await value('/library/inbox')).find(item => item.file_name === name + '.pdf').status, 'failed');
    assert.equal(await page.getByText(/原件已上传，文档尚未入库/).count(), 1);
    await page.reload();
    await page.getByRole('button', { name: '任务详情', exact: true }).click();
    if (name === 'batch') await panel.locator('summary').click();
    await retry.waitFor();
    assert.equal(await panel.getByText('sibling.pdf', { exact: true }).count(), 0);
    await retry.click();
    await page.waitForFunction(async name => {
      const { value } = await (await fetch('/library/inbox')).json();
      return value.find(item => item.file_name === name + '.pdf')?.status === 'completed';
    }, name);
    await page.getByRole('button', { name: '任务详情', exact: true }).click();
  }
  console.log(`PASS: ${scenario} duplicate restores only matching task, focuses retry, survives reload and completes on explicit retry`);
} finally {
  await browser.close();
}
