import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const commands = [
  ['node_modules/vite/bin/vite.js', '--config', 'frontend/vite.config.ts'],
  ['node_modules/tsx/dist/cli.mjs', 'watch', 'backend/src/server.ts'],
];
const children = commands.map((args) => spawn(process.execPath, args, {
  cwd: root,
  stdio: 'inherit',
}));
let stopping = false;

function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  children.forEach((child) => child.kill('SIGTERM'));
}

process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());
children.forEach((child) => {
  child.on('error', (error) => {
    console.error(error);
    stop(1);
  });
  child.on('exit', (code) => stop(code ?? 1));
});
