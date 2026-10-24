import { StreamLanguage } from '@codemirror/language';
import type { Extension } from '@codemirror/state';

const zigKeywords = new Set(('addrspace align allowzero and anyframe anytype asm async await break callconv catch comptime const continue defer else enum errdefer error export extern fn for if inline linksection noalias noinline nosuspend opaque or orelse packed pub resume return section struct suspend switch test threadlocal try union unreachable usingnamespace var volatile while').split(' '));
const zig = StreamLanguage.define({
  token(stream) {
    if (stream.eatSpace()) return null;
    if (stream.match('//')) { stream.skipToEnd(); return 'comment'; }
    if (stream.match('\\\\')) { stream.skipToEnd(); return 'string'; }
    if (stream.match(/^@?"(?:[^"\\]|\\.)*(?:"|$)/) || stream.match(/^'(?:[^'\\]|\\.)*(?:'|$)/)) return 'string';
    if (stream.match(/^@[A-Za-z_]\w*/)) return 'variableName.standard';
    if (stream.match(/^(?:0[xX][\da-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|\d[\w.]*)/)) return 'number';
    const word = stream.match(/^[A-Za-z_]\w*/);
    if (word) {
      const name = (word as RegExpMatchArray)[0];
      return zigKeywords.has(name) ? 'keyword' : /^(?:[iu]\d+|usize|isize|f\d+|bool|void|noreturn|type|anyerror)$/.test(name) ? 'typeName' : /^(?:true|false|null|undefined)$/.test(name) ? 'atom' : 'variableName';
    }
    stream.next(); return 'operator';
  }, languageData: { commentTokens: { line: '//' }, closeBrackets: { brackets: ['(', '[', '{', '"', "'"] } },
});
const manifest = StreamLanguage.define({
  token(stream) {
    if (stream.sol() && stream.match(/[A-Z][A-Z0-9_]*(?==)/)) return 'keyword';
    if (stream.match('=')) return 'operator';
    stream.skipToEnd(); return 'string';
  },
});

export function languageName(path: string) {
  if (/\.rs$/i.test(path)) return 'Rust';
  if (/\.(?:c|h|cpp|hpp|cc)$/i.test(path)) return 'C';
  if (/\.(?:zig|zon)$/i.test(path)) return 'Zig';
  if (/\.r4mf$/i.test(path)) return 'R4MF';
  if (/\.json$/i.test(path)) return 'JSON';
  if (/\.md$/i.test(path)) return 'Markdown';
  if (/\.toml$/i.test(path) || /(?:^|\/)Cargo.lock$/.test(path)) return 'TOML';
  return 'Plain text';
}
export async function languageFor(path: string): Promise<Extension> {
  switch (languageName(path)) {
    case 'Rust': return (await import('@codemirror/lang-rust')).rust();
    case 'C': return (await import('@codemirror/lang-cpp')).cpp();
    case 'Zig': return zig;
    case 'R4MF': return manifest;
    case 'JSON': return (await import('@codemirror/lang-json')).json();
    case 'Markdown': return (await import('@codemirror/lang-markdown')).markdown();
    case 'TOML': return StreamLanguage.define((await import('@codemirror/legacy-modes/mode/toml')).toml);
    default: return [];
  }
}
