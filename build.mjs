// Genera anonimizador.html: un único archivo autocontenido, sin dependencias externas.
// Uso: node build.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const src = join(root, 'src');
let html = readFileSync(join(src, 'index.html'), 'utf8');
html = html.replace(/\/\*INLINE:([^*]+)\*\//g, (_, file) => {
  const code = readFileSync(join(src, file.trim()), 'utf8');
  return code.replace(/<\/(script|style)/gi, '<\\/$1').replace(/<!--/g, '<\\!--');
});
const out = join(root, 'anonimizador.html');
writeFileSync(out, html);
console.log(`Generado ${out} (${(Buffer.byteLength(html) / 1024 / 1024).toFixed(2)} MB)`);
