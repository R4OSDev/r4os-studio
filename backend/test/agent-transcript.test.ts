import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MessageText, transcriptText } from '../../frontend/src/features/agent-sessions/Transcript.js';

await test('transcript formats Markdown/code and excludes active HTML, remote images, unsafe links and OSC clipboard commands', () => {
  const body = '**Result**\n\n```c\n<script>alert(1)</script>\n```\n\n<img src="https://example.invalid/raw" onerror="alert(2)">\n\n![private](https://example.invalid/pixel)\n\n[bad](javascript:alert(3))\n\n[docs](https://example.com/docs)';
  const html = renderToStaticMarkup(createElement(MessageText, { text: body, markdown: true }));
  assert(html.includes('<strong>Result</strong>')); assert(html.includes('Copy code'));
  assert(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
  assert(!html.includes('<script')); assert(!html.includes('<img')); assert(!html.includes('src="https://example.invalid'));
  assert(!html.includes('href="javascript:')); assert(html.includes('rel="noopener noreferrer"'));
  const output = '\u001b]52;c;c2VjcmV0\u0007\u001b[31mvisible\u001b[0m\n';
  assert.equal(transcriptText(output), 'visible\n');
  assert.equal(transcriptText('\u001b]52;unterminated'), '');
});
