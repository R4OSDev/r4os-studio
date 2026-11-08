/** Fixed metadata control, never an OAuth HTTP client or model input. */
import { pathToFileURL } from 'node:url';
const sdk = await import(pathToFileURL(process.env.STUDIO_CLAUDE_SDK).href);
import { ClaudeControl } from './claude_engine.mjs';

const requestId = process.argv[2];
if (process.argv.length > 4 || process.argv[3] !== undefined && process.argv[3] !== 'catalog') throw Error('Unknown native metadata mode.');
const control = new ClaudeControl(sdk, { executable: process.env.STUDIO_CLAUDE_NATIVE, cwd: process.cwd(), home: process.env.HOME, config: process.env.CLAUDE_CONFIG_DIR }, requestId);
try {
  const init = await control.control('initialize');
  if (init.value.claude_code_version !== '2.1.312') throw Error('Unqualified native version.');
  const account = await control.control('account'), usage = await control.control('usage');
  const models = process.argv[3] === 'catalog' ? (await control.control('models')).value : undefined;
  process.stdout.write(JSON.stringify({ schema: 1, requestId, nativeVersion: init.value.claude_code_version,
    sdkVersion: '0.3.312', account: account.value, models, usage: {
      subscription_type: usage.value?.subscription_type, rate_limits_available: usage.value?.rate_limits_available,
      rate_limits: usage.value?.rate_limits,
    }, promptMessagesSubmitted: 0 }) + '\n');
} finally { await control.close(); }
