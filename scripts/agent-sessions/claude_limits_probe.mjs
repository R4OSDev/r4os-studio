/** Fixed metadata control, never an OAuth HTTP client or model input. */
import * as sdk from '/runtime/sdk/sdk.mjs';
import { ClaudeControl } from './claude_engine.mjs';

const requestId = process.argv[2];
const control = new ClaudeControl(sdk, { executable: '/claude', cwd: '/inference', home: '/home/studio', config: '/config' }, requestId);
try {
  const init = await control.control('initialize');
  if (init.value.claude_code_version !== '2.1.312') throw Error('Unqualified native version.');
  const account = await control.control('account'), usage = await control.control('usage');
  process.stdout.write(JSON.stringify({ schema: 1, requestId, nativeVersion: init.value.claude_code_version,
    sdkVersion: '0.3.312', account: account.value, usage: {
      subscription_type: usage.value?.subscription_type, rate_limits_available: usage.value?.rate_limits_available,
      rate_limits: usage.value?.rate_limits,
    }, promptMessagesSubmitted: 0 }) + '\n');
} finally { await control.close(); }
