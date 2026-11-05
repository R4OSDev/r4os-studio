import { readdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { brotliCompress, constants, gzip } from 'node:zlib';
import { promisify } from 'node:util';

const brotli = promisify(brotliCompress), zip = promisify(gzip);
const root = fileURLToPath(new URL('../frontend/dist/', import.meta.url));
let count = 0, original = 0, compressed = 0;
async function compress(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) { await compress(path); continue; }
    if (!entry.isFile() || !/\.(js|mjs|css|html|svg|json|wasm)$/.test(entry.name)) continue;
    const raw = await readFile(path);
    if (raw.length < 1024) continue;
    const variants = await Promise.all([
      brotli(raw, { params: { [constants.BROTLI_PARAM_QUALITY]: 9 } }), zip(raw, { level: 9 }),
    ]);
    for (const [index, bytes] of variants.entries()) {
      if (bytes.length < raw.length) await writeFile(path + (index ? '.gz' : '.br'), bytes);
    }
    count++; original += raw.length; compressed += Math.min(raw.length, variants[0].length);
  }
}
await compress(root);
console.log(`Public assets: ${count} files, ${original} bytes; Brotli ${compressed} bytes.`);
