// Browser regression: cached attachment responses without CORS must remain
// downloadable. Pass the running workbench and selected part explicitly.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [frontend, api, partKey] = process.argv.slice(2);
if (!frontend || !api || !partKey) throw new Error('Usage: node scripts/check_native_downloads.cjs <frontend-url> <api-url> <part-key>');

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  let legacy;
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
    const inventory = await (await page.request.get(`${api}/api/parts`)).json();
    const part = inventory.parts.find(part => part.key === partKey);
    assert(part, 'Requested part exists in the selected project');
    const files = {};
    for (const artifact of part.artifacts.filter(artifact => ['step', 'stl'].includes(artifact.kind))) {
      const url = new URL(artifact.content_url, api);
      url.searchParams.set('download', 'true');
      const response = await page.request.get(url.href);
      assert.equal(response.status(), 200);
      files[artifact.kind] = { bytes: await response.body(), filename: artifact.relative_path.split('/').pop(), sha256: artifact.sha256 };
    }
    assert(files.step && files.stl, 'Both built formats are required for this regression');
    // Reproduce the legacy server/cache response: immutable attachment, no Vary
    // and no CORS header. Browser navigation works; JavaScript fetch rejects it.
    legacy = http.createServer((request, response) => {
      const kind = new URL(request.url, 'http://localhost').pathname.slice(1);
      const file = files[kind];
      if (!file) { response.writeHead(404); response.end(); return; }
      response.writeHead(200, {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': `attachment; filename="${file.filename}"`,
        'Cache-Control': 'public, max-age=31536000, immutable',
        'Content-Length': file.bytes.length,
      });
      response.end(file.bytes);
    });
    await new Promise(resolve => legacy.listen(0, '127.0.0.1', resolve));
    const legacyBase = `http://127.0.0.1:${legacy.address().port}`;
    const firstDownload = page.waitForEvent('download');
    await page.goto(`${legacyBase}/stl`).catch(error => {
      if (!/Download is starting|ERR_ABORTED/.test(error.message)) throw error;
    });
    await firstDownload;
    // Keep display artifacts and assembly metadata real; route only download
    // links to the legacy response so the production UI exercises this failure.
    await page.route(`${api}/api/parts*`, async route => {
      const payload = structuredClone(inventory);
      payload.parts.find(part => part.key === partKey).artifacts.forEach(artifact => {
        if (files[artifact.kind]) artifact.content_url = `${legacyBase}/${artifact.kind}`;
      });
      await route.fulfill({ json: payload });
    });
    await page.goto(frontend);
    const rejected = await page.evaluate(async url => {
      try { await fetch(url); return false; } catch { return true; }
    }, `${legacyBase}/stl`);
    assert(rejected, 'The previous JavaScript-fetch download path must fail in this fixture');
    await page.getByRole('tab', { name: /^All/ }).click();
    await page.locator('.inventory-search input').fill(part.key);
    await page.getByRole('option').filter({ hasText: part.display_name || part.key }).click();
    const originalPage = page.url();
    for (const kind of ['step', 'stl', 'stl']) {
      const [download] = await Promise.all([
        page.waitForEvent('download'),
        page.locator('.inspector-dock').getByRole('link', { name: `Download ${kind.toUpperCase()}` }).click(),
      ]);
      assert.equal(download.suggestedFilename(), files[kind].filename);
      assert.equal(crypto.createHash('sha256').update(fs.readFileSync(await download.path())).digest('hex'), files[kind].sha256);
      assert.equal(page.url(), originalPage, 'Downloading must preserve the workbench');
    }
    console.log(`PASS ${inventory.project_id}: old fetch rejects; native STEP/STL downloads and repeated cached STL download match artifact hashes`);
  } finally {
    await browser.close();
    if (legacy) await new Promise(resolve => legacy.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
