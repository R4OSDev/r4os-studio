/** Fixed metadata control, never an OAuth HTTP client or model input. */
import * as sdk from '/runtime/sdk/sdk.mjs';
import { ClaudeControl } from './claude_engine.mjs';

const requestId = process.argv[2];
if (process.argv.length > 4 || process.argv[3] !== undefined && process.argv[3] !== 'catalog') throw Error('Unknown native metadata mode.');
const control = new ClaudeControl(sdk, { executable: '/claude', cwd: '/inference', home: '/home/studio', config: '/config' }, requestId);
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
