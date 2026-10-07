const { chromium } = require('playwright-core');
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu'] });
  const page = await browser.newPage({ viewport: { width: 1280, height: 820 } });
  page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
  await page.goto('http://127.0.0.1:8788/', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => { const i = document.getElementById('qrImg'); return i && i.complete && i.naturalWidth > 0; }, { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(600);
  await page.screenshot({ path: '/home/gazer/filehub/tests/shots/final-desktop.png', fullPage: true });
  console.log('QR url =', await page.textContent('#qrUrl'));
  console.log('chips =', (await page.$$eval('#chips .chip', (e) => e.map((x) => x.textContent.trim()))).join(' | '));
  console.log('summary =', await page.textContent('#listSummary'));
  console.log('empty visible =', await page.isVisible('#empty'));

  const m = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  await m.goto('http://127.0.0.1:8788/m', { waitUntil: 'networkidle' });
  await m.waitForTimeout(500);
  await m.screenshot({ path: '/home/gazer/filehub/tests/shots/final-mobile.png', fullPage: true });
  await browser.close();
})();
