// Pure bounded SKILL.md validation. YAML metadata never installs or grants rights.
import yaml from 'js-yaml';
const chunks = [];
let bytes = 0;
for await (const chunk of process.stdin) {
  bytes += chunk.length;
  if (bytes > 65536) { console.log(JSON.stringify({ valid: false, errors: ['SKILL.md exceeds 64 KiB.'] })); process.exit(0); }
  chunks.push(chunk);
}
const errors = [];
let metadata;
try {
  const text = new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks)).replaceAll('\r\n', '\n');
  if (Array.from(text).some((character) => { const code = character.codePointAt(0); return code === 127 || (code < 32 && ![9, 10, 13].includes(code)); })) throw new Error('Invalid text.');
  const match = /^---\n([\s\S]*?)\n---(?:\n|$)/.exec(text);
  if (!match) errors.push('SKILL.md needs YAML frontmatter delimited by --- with name and description.');
  else {
    const value = yaml.load(match[1], { schema: yaml.JSON_SCHEMA });
    if (!value || typeof value !== 'object' || Array.isArray(value)) errors.push('Frontmatter must be a YAML mapping.');
    else {
      const name = value.name, description = value.description;
      if (typeof name !== 'string' || name.length > 64 || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(name)) errors.push('Name must use lowercase letters, digits and single hyphens, up to 64 characters.');
      if (typeof description !== 'string' || !description.trim() || description.length > 1024 || /[<>\p{Cc}\p{Cs}]/u.test(description.replaceAll('\n', ' '))) errors.push('Description must be nonempty text of at most 1024 characters.');
      if (!text.slice(match[0].length).trim()) errors.push('Add Markdown instructions below the frontmatter.');
      if (!errors.length) metadata = { name, description: description.trim().split(/\s+/).join(' ') };
    }
  }
} catch { errors.push('SKILL.md contains invalid UTF-8 text or YAML frontmatter.'); }
console.log(JSON.stringify({ valid: errors.length === 0, errors, ...(metadata ? { metadata } : {}) }));
