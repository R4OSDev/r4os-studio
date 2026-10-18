import { readFileSync, writeFileSync } from 'node:fs';

const { version } = JSON.parse(readFileSync(new URL('../shared/version.json', import.meta.url), 'utf8'));
if (typeof version !== 'string' || !/^\d+\.\d+\.\d+$/.test(version)) {
  throw new Error('shared/version.json must contain a numeric major.minor.patch version.');
}
const manifestUrl = new URL('../package.json', import.meta.url);
const manifest = JSON.parse(readFileSync(manifestUrl, 'utf8'));
if (manifest.version !== version) {
  manifest.version = version;
  writeFileSync(manifestUrl, JSON.stringify(manifest, null, 2) + '\n');
}
