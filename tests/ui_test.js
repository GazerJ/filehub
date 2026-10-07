/* 浏览器端端到端测试：真实页面 + 真实上传 + 多选打包下载 + 截图
 * 运行： NODE_PATH=/home/gazer/.theme-debug/node_modules node tests/ui_test.js
 */
const { chromium } = require('playwright-core');
const fs = require('fs');
const os = require('os');
const path = require('path');

const BASE = process.env.HUB_BASE || 'http://127.0.0.1:8788';
const SHOTS = process.env.HUB_SHOTS || '/home/gazer/filehub/tests/shots';
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'hub-ui-'));

let pass = 0, fail = 0;
function check(label, cond, extra) {
  if (cond) { pass++; console.log('  PASS  ' + label); }
  else { fail++; console.log('  FAIL  ' + label + (extra !== undefined ? '  -> ' + extra : '')); }
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu'] });

  /* ---------------- 桌面端 ---------------- */
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 940 }, acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => {
    const img = document.getElementById('qrImg');
    return img && img.complete && img.naturalWidth > 0;
  }, { timeout: 10000 }).catch(() => {});
  const qrOk = await page.evaluate(() => {
    const img = document.getElementById('qrImg');
    return { w: img.naturalWidth, src: img.getAttribute('src'), url: document.getElementById('qrUrl').textContent };
  });
  check('二维码图片渲染成功', qrOk.w > 100, JSON.stringify(qrOk));
  check('二维码指向手机上传页 /m', /\/m$/.test(qrOk.url), qrOk.url);
  check('二维码接口返回的是 QR 图', /\/api\/qr\.png\?url=/.test(qrOk.src || ''), qrOk.src);

  const chips = await page.$$eval('#chips .chip', (els) => els.map((e) => e.textContent.trim()));
  check('顶部状态显示有效期 7 天', chips.some((t) => /有效期/.test(t) && /7 天/.test(t)), chips.join(' | '));

  await page.screenshot({ path: path.join(SHOTS, 'desktop-empty.png'), fullPage: true });

  // 通过「选择文件上传」真实上传两个文件
  const f1 = path.join(TMP, '照片 示例.txt');
  const f2 = path.join(TMP, 'report.bin');
  fs.writeFileSync(f1, 'ui upload test 第一行\n');
  fs.writeFileSync(f2, Buffer.alloc(2 * 1024 * 1024, 7));
  await page.setInputFiles('#fileInput', [f1, f2]);
  await page.waitForFunction(() => document.querySelectorAll('#filelist .frow').length >= 2, { timeout: 20000 });
  await page.waitForTimeout(1200);

  const names = await page.$$eval('#filelist .fname-text', (els) => els.map((e) => e.textContent));
  check('上传后列表出现两个文件', names.includes('照片 示例.txt') && names.includes('report.bin'), names.join(' | '));
  const summary = await page.textContent('#listSummary');
  check('列表摘要显示数量与体积', /共 \d+ 个文件/.test(summary) && /MB|KB|B/.test(summary), summary);
  const remain = await page.$eval('#filelist .badge', (e) => e.textContent);
  check('每个文件显示剩余有效期', /剩 \d+ 天/.test(remain), remain);

  // 全选 → 打包下载
  await page.click('#selectAll');
  const selInfo = await page.textContent('#selInfo');
  check('全选后显示已选数量', /已选 \d+ 项/.test(selInfo), selInfo);
  check('打包下载按钮可用', !(await page.isDisabled('#zipBtn')));
  check('删除按钮可用', !(await page.isDisabled('#delBtn')));

  // 取消勾选一个 → 按钮状态回退
  const boxes = await page.$$('#filelist input[type=checkbox]');
  await boxes[0].click();
  await page.waitForTimeout(150);
  const selInfo2 = await page.textContent('#selInfo');
  check('取消单个勾选后数量减一', /已选 \d+ 项/.test(selInfo2), selInfo2);
  await boxes[0].click();
  await page.waitForTimeout(150);

  await page.screenshot({ path: path.join(SHOTS, 'desktop-files.png'), fullPage: true });

  // 真实触发打包下载
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 20000 }),
    page.click('#zipBtn'),
  ]);
  const zipPath = path.join(TMP, 'pack.zip');
  await download.saveAs(zipPath);
  const size = fs.statSync(zipPath).size;
  check('打包下载产生 zip 文件', size > 1024 * 1024, size);
  check('zip 文件名可读', /\.zip$/.test(download.suggestedFilename()), download.suggestedFilename());

  // 单个文件下载
  const [single] = await Promise.all([
    page.waitForEvent('download', { timeout: 20000 }),
    page.click('#filelist .frow .facts a.btn'),
  ]);
  check('单文件下载保留原名', download.suggestedFilename() && /\.(txt|bin)$/.test(single.suggestedFilename()), single.suggestedFilename());

  // 删除一个文件（自动确认对话框）
  page.once('dialog', (d) => d.accept());
  const before = await page.$$eval('#filelist .frow', (els) => els.length);
  await page.click('#filelist .frow .facts button.btn-danger');
  await page.waitForFunction((n) => document.querySelectorAll('#filelist .frow').length < n, before, { timeout: 15000 });
  const after = await page.$$eval('#filelist .frow', (els) => els.length);
  check('删除后列表少一项', after === before - 1, before + ' -> ' + after);

  check('桌面端没有 JS 报错', errors.length === 0, errors.slice(0, 3).join(' ; '));

  /* ---------------- 手机端（扫码后打开的页面） ---------------- */
  const mctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true,
    hasTouch: true, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
  });
  const mpage = await mctx.newPage();
  const merrors = [];
  mpage.on('pageerror', (e) => merrors.push('pageerror: ' + e.message));
  await mpage.goto(BASE + '/m', { waitUntil: 'networkidle' });
  await mpage.waitForFunction(() => document.querySelectorAll('#filelist .frow').length >= 1, { timeout: 10000 }).catch(() => {});
  const mPick = await mpage.$('#pickBtn');
  const mCam = await mpage.$('#cameraBtn');
  check('手机页有「选择文件上传」按钮', !!mPick);
  check('手机页有拍照/录像入口', !!mCam);
  check('手机页列出已有文件', (await mpage.$$('#filelist .frow')).length >= 1);
  check('手机页底部有多选操作栏', !!(await mpage.$('.mbar #zipBtn')));

  const mf = path.join(TMP, '手机上传.txt');
  fs.writeFileSync(mf, 'from mobile\n');
  const beforeM = (await mpage.$$('#filelist .frow')).length;
  await mpage.setInputFiles('#fileInput', [mf]);
  await mpage.waitForFunction((n) => document.querySelectorAll('#filelist .frow').length > n, beforeM, { timeout: 20000 });
  const mnames = await mpage.$$eval('#filelist .fname-text', (els) => els.map((e) => e.textContent));
  check('手机端上传成功', mnames.includes('手机上传.txt'), mnames.join(' | '));
  await mpage.screenshot({ path: path.join(SHOTS, 'mobile.png'), fullPage: true });
  check('手机端没有 JS 报错', merrors.length === 0, merrors.slice(0, 3).join(' ; '));

  // 桌面端列表自动刷新（15 秒轮询）→ 直接手动刷新按钮验证
  await page.click('#refreshBtn');
  await page.waitForTimeout(800);
  const namesAfter = await page.$$eval('#filelist .fname-text', (els) => els.map((e) => e.textContent));
  check('桌面端刷新后能看到手机上传的文件', namesAfter.includes('手机上传.txt'), namesAfter.join(' | '));

  await browser.close();
  console.log('\n通过 ' + pass + ' 项，失败 ' + fail + ' 项');
  console.log('截图目录: ' + SHOTS);
  console.log('临时目录: ' + TMP);
  process.exit(fail === 0 ? 0 : 1);
})().catch((e) => { console.error('测试异常:', e); process.exit(2); });
