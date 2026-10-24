// The dev/e2e server (tests/e2e/server.mjs) must survive malformed requests.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, resolveFile } from '../e2e/server.mjs';

test('resolveFile: malformed percent-encoding resolves to nothing instead of throwing', () => {
  assert.equal(resolveFile('/%E0%A4%A'), null);
  assert.equal(resolveFile('/..%2f..%2fpackage.json'), null);
});

test('server: a malformed URL gets 404 and the server keeps answering', async () => {
  const { url, close } = await startServer({ port: 0 });
  try {
    const bad = await fetch(new URL('%E0%A4%A', url));
    assert.equal(bad.status, 404);
    await bad.arrayBuffer();
    const ok = await fetch(url);
    assert.equal(ok.status, 200);
    await ok.arrayBuffer();
  } finally {
    await close();
  }
});
