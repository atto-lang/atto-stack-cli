import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const generator = read('../src/main.ores');
const cli = read('../bin/oreslang-stack');
const nativeTest = read('./native-generator-contract.sh');
const api = read('../examples/hello-api/src/routes/rest/route.ores');

test('API generator emits the upstream v1 contract declarations, not function-body syntax', () => {
  const marker = 'fs.write_text_atomic(source_root + "/contracts/RouteContract.ores"';
  const start = generator.indexOf(marker);
  assert.ok(start >= 0, 'contract writer must exist');
  const end = generator.indexOf('fs.write_text_atomic(route_dir + "/handlers.ores"', start);
  assert.ok(end > start, 'contract writer must precede handlers');
  const template = generator.slice(start, end);
  assert.match(template, /"define contract RouteContract as\\n"/);
  assert.match(template, /fnc get\(String request\) => String;/);
  assert.match(template, /fnc post\(String request\) => String;/);
  assert.doesNotMatch(template, /pub define contract/);
  assert.doesNotMatch(template, /fnc (get|post)\(String request\) -> String;/);
});
test('API generator uses parser-accepted conformance spelling', () => {
  assert.match(generator, /define module Route conforms RouteContract as/);
  assert.doesNotMatch(generator, /define module Route conforms to RouteContract as/);
});
test('native integration suite asserts generated canonical signatures', () => {
  for (const fragment of [
    'define contract RouteContract as',
    'fnc get(String request) => String;',
    'fnc post(String request) => String;',
    'define module Route conforms RouteContract as',
  ]) assert.ok(nativeTest.includes(fragment), fragment);
});
test('existing legacy sample remains explicitly separate from canonical two-operation scaffold', () => {
  assert.match(api, /@ores-route GET \/ greet/);
  assert.match(api, /define module route as/);
  assert.match(cli, /native Oreslang/i);
});
