/** Fixed metadata-only child entrypoint; filesystem/network isolation is host-owned. */
import { openControl } from './claude_engine.mjs';

let control;
try {
  control = await openControl({ sdk: process.env.STUDIO_CLAUDE_SDK, native: process.env.STUDIO_CLAUDE_NATIVE,
    version: '2.1.312', sdkVersion: '0.3.312', qualified: { offlineInitialization: true, modelTurns: false } },
  { cwd: process.cwd(), home: process.env.HOME, config: process.env.CLAUDE_CONFIG_DIR }, process.argv[2]);
  const initialize = await control.control('initialize'), models = await control.control('models');
  const account = await control.control('account'); await control.control('interrupt');
  if (control.events || initialize.value.claude_code_version !== '2.1.312' || !Array.isArray(models.value)) throw Error();
  await control.close();
  process.stdout.write(JSON.stringify({ schema: 1, nativeVersion: '2.1.312', sdkVersion: '0.3.312',
    advertisedModels: models.value.length, accountFieldNames: Object.keys(account.value).filter(name => ['tokenSource', 'apiProvider', 'apiKeySource', 'email', 'organization', 'subscriptionType'].includes(name)),
    subscriptionVerified: false, promptMessagesSubmitted: 0, toolsAuthorized: false, modelTurnsQualified: false }) + '\n');
} catch {
  process.stderr.write('The original native Claude metadata probe could not be confirmed.\n'); process.exitCode = 1;
} finally { if (control) { try { await control.close(); } catch { process.exitCode = 1; } } }
