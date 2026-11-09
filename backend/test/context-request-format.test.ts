import test from 'node:test';
import assert from 'node:assert/strict';
import {formatRequest} from '../../frontend/src/features/agent-sessions/request-format';

test('request presentation retains number lexemes, Unicode and escaped literals',()=>{
  const raw='\ufeff{"id":18446744073709551615,"negative":-0,"decimal":1.2300e+40,"text":"Grüße 👩‍💻 é\\nNext\\r\\nLine\\\\nLiteral","empty":[],"nested":{"name":"<script>never run</script>"}}';
  const view=formatRequest(raw);
  assert.equal(view.notice,null);assert.ok(view.text.startsWith('\ufeff{\n  "id": 18446744073709551615,'));
  assert.match(view.text,/"negative": -0/);assert.match(view.text,/"decimal": 1\.2300e\+40/);
  assert.ok(view.text.includes('Grüße 👩‍💻 é\n    Next\n    Line\\\\nLiteral'));
  assert.match(view.text,/"empty": \[\]/);assert.ok(view.text.includes('<script>never run</script>'));
  assert.equal(raw.charCodeAt(0),0xfeff);
});

test('whole large document is formatted without pages or numeric reserialization',()=>{
  const raw='{"tools":['+Array.from({length:12000},(_,i)=>'{"name":"own_'+i+'","number":9007199254740993}').join(',')+'],"last":"DOCUMENT_END"}';
  const result=formatRequest(raw);assert.equal(result.notice,null);
  assert.match(result.text,/"own_11999"/);assert.ok(result.text.endsWith('"last": "DOCUMENT_END"\n}'));
  assert.equal((result.text.match(/9007199254740993/g)??[]).length,12000);
});

test('invalid JSON is displayed intact and deep JSON has bounded indentation',()=>{
  const raw='not JSON\nOriginal text';assert.deepEqual(formatRequest(raw),{text:raw,notice:'This body is not valid JSON. The original text is shown.'});
  const deep='['.repeat(5000)+'0'+']'.repeat(5000),result=formatRequest(deep);
  assert.equal(result.notice,null);assert.ok(result.text.length<700000);assert.equal(result.text.replace(/\s/g,''),deep);
});
