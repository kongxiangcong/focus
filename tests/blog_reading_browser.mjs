import assert from "node:assert/strict";
const { chromium } = await import(process.env.FOCUS_PLAYWRIGHT_MODULE || "playwright");
const browser = await chromium.launch({ headless: true, executablePath: process.env.FOCUS_CHROMIUM_EXECUTABLE });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(20000);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.addInitScript(() => localStorage.setItem("focus.libraryView", "list"));
  await page.goto(`${process.env.FOCUS_TEST_URL}/library`);
  await page.locator("#source-title-Fixture-paper").click();
  const panel = page.locator(".library-inspector");
  assert.equal(await panel.locator(".blog-statuses li").count(), 2);
  assert.deepEqual(await panel.locator(".blog-statuses li > span").allTextContents(), ["带读博客", "HTML"]);
  await panel.getByRole("button", { name: "生成博客", exact: true }).click();
  await panel.getByRole("button", { name: "重新生成带读博客", exact: true }).click();
  await page.waitForFunction(() => [...document.querySelectorAll(".blog-statuses li")].length === 2
    && [...document.querySelectorAll(".blog-statuses li")].every(node => node.dataset.status === "completed"));
  await panel.getByRole("button", { name: "打开博客", exact: true }).click();
  const viewer = page.frameLocator('iframe[title="博客"]');
  await viewer.locator('section[data-kind="reading_blog"][data-active="true"]').waitFor();
  assert.equal(await viewer.locator("section[data-kind]").count(), 1);
  assert.equal(await viewer.locator('[role="tab"], [data-kind="value_analysis"]').count(), 0);
  assert.equal(await viewer.locator("img").evaluateAll(images => images.every(image => image.complete && image.naturalWidth > 0)), true);
  const response = await page.request.post(`${process.env.FOCUS_TEST_URL}/library/sources/Fixture-paper/blog/regenerate`, {
    data: { artifact: "value_analysis", requestId: "browser-retired-target" },
  });
  assert.equal(response.status(), 400);
  assert.match(await response.text(), /Invalid blog artifact/);
  assert.deepEqual(errors, []);
  console.log("PASS: generation, writing retry, two statuses, single-page viewer, images, retired target rejection");
} finally {
  await browser.close();
}
