// Prueba de extremo a extremo: carga cada archivo, descarga el resultado y comprueba que no hubo tráfico de red.
// Uso: node tests/e2e.cjs <carpeta_fixtures> <carpeta_salida>
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
(async () => {
  const [fx, out] = process.argv.slice(2);
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ acceptDownloads: true });
  const page = await ctx.newPage();
  const net = [];
  page.on('request', (r) => { if (!r.url().startsWith('file:') && !r.url().startsWith('blob:') && !r.url().startsWith('data:')) net.push(r.url()); });
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto('file://' + path.resolve(__dirname, '../anonimizador.html'));
  for (const f of fs.readdirSync(fx).filter((f) => !f.includes('ANONIMIZADO'))) {
    await page.setInputFiles('#file', path.join(fx, f));
    await page.waitForSelector('#step-review:not([hidden])');
    await page.waitForTimeout(300);
    const err = await page.$eval('#error', (e) => (e.hidden ? '' : e.textContent));
    if (err) { console.log(f, 'ERROR:', err); continue; }
    const ents = await page.$$eval('.ent', (rows) => rows.map((r) => r.querySelector('.orig').firstChild.textContent + ' => ' + r.querySelector('.rep').value));
    console.log('\n=== ' + f + ' (' + ents.length + ' datos)\n  ' + ents.join('\n  '));
    const [dl] = await Promise.all([page.waitForEvent('download'), page.click('#btn-download')]);
    const dest = path.join(out, dl.suggestedFilename());
    await dl.saveAs(dest);
    console.log('  -> ' + dest);
    await page.click('#btn-reset');
  }
  await page.setViewportSize({ width: 1300, height: 900 });
  await page.setInputFiles('#file', path.join(fx, 'demanda.docx'));
  await page.waitForSelector('#step-review:not([hidden])');
  await page.screenshot({ path: path.join(out, 'captura.png'), fullPage: true });
  await page.click('.seg-btn[data-view="anon"]');
  await page.screenshot({ path: path.join(out, 'captura_anon.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 800 });
  await page.screenshot({ path: path.join(out, 'captura_movil.png'), fullPage: true });
  console.log('\nPeticiones de red:', net.length ? net : 'ninguna');
  console.log('Errores de consola:', errors.length ? errors : 'ninguno');
  await browser.close();
})();
