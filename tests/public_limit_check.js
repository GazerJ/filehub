const { chromium } = require('playwright-core');
const fs = require('fs');
(async () => {
  const big = '/tmp/big-file-test.bin';
  if (!fs.existsSync(big)) fs.writeFileSync(big, Buffer.alloc(120 * 1024 * 1024, 3));
  const b = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu'] });
  const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
  await p.goto('https://file.gaoxiao.asia/', { waitUntil: 'networkidle', timeout: 30000 });
  await p.setInputFiles('#fileInput', [big]);
  await p.waitForTimeout(1500);
  const toast = await p.textContent('#toast');
  const rows = await p.$$eval('#filelist .frow', (e) => e.length);
  console.log('提示语:', toast);
  console.log('列表行数（应为 0，说明被跳过没有上传）:', rows);
  console.log('排队区是否出现:', await p.isVisible('#queue'));
  await p.screenshot({ path: '/home/gazer/filehub/tests/shots/public-100mb-guard.png' });
  await b.close();
})();
