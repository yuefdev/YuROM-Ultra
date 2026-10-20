// SPDX-License-Identifier: GPL-3.0-or-later
import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFile } from 'node:fs/promises';
import worker, { fetchHandler } from '../worker.mjs';

const ID = 'e2023123-a123-4123-8123-123456789abc';
const event = () => ({ schema: 1, installation: ID, model: 'SM-G970F', build: 'v30-test', oc_mode: 'auto', report: 'audio',
  crashes: [{ signature: 'a'.repeat(64), component: 'com.android.settings', exception: 'java.lang.IllegalStateException', frames: ['com.android.settings.Foo.onCreate'] }] });
async function setup() {
  const db = new DatabaseSync(':memory:'); db.exec(await readFile(new URL('../schema.sql', import.meta.url), 'utf8'));
  const env = { INSTALLATION_SALT: 's'.repeat(64), ADMIN_TOKEN: 't'.repeat(64), DB: {
    prepare(sql) { const command = { sql, args: [], bind(...args) { this.args = args; return this; } }; return command; },
    async batch(commands) { db.exec('BEGIN'); try { const result = commands.map(c => { const statement = db.prepare(c.sql); return { results: c.sql.trim().startsWith('SELECT') ? statement.all(...c.args) : (statement.run(...c.args), []) }; }); db.exec('COMMIT'); return result; } catch (e) { db.exec('ROLLBACK'); throw e; } }
  } };
  const send = (value, path = '/v1/event') => fetchHandler(new Request('https://telemetry.test' + path, { method: 'POST', headers: { 'content-type': 'application/json', 'CF-Connecting-IP': '192.0.2.1' }, body: JSON.stringify(value) }), env);
  return { db, env, send };
}

test('retries deduplicate activity/issues, private IDs/IPs are not stored, admin authentication and deletion work', async () => {
  const { db, env, send } = await setup();
  assert.equal((await send(event())).status, 200); assert.equal((await send(event())).status, 200);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM installations').get().n, 1);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM activity').get().n, 1);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM issues').get().n, 2);
  const stored = JSON.stringify(db.prepare('SELECT * FROM installations').all());
  assert.ok(!stored.includes(ID) && !stored.includes('192.0.2.1'));
  assert.equal((await fetchHandler(new Request('https://telemetry.test/v1/stats'), env)).status, 401);
  const stats = await fetchHandler(new Request('https://telemetry.test/v1/stats', { headers: { Authorization: `Bearer ${env.ADMIN_TOKEN}` } }), env);
  const data = await stats.json(); assert.equal(data.totals.known_installations, 1); assert.equal(data.issues.length, 2);
  assert.equal((await send({ installation: ID }, '/v1/forget')).status, 200);
  for (const table of ['installations', 'activity', 'issues']) assert.equal(db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n, 0);
  db.close();
});

test('reject unknown personal fields, raw messages, unauthorised devices, oversized uploads and invalid IDs', async () => {
  const { db, send } = await setup();
  const invalid = [Object.assign(event(), { imei: 'private' }), Object.assign(event(), { model: 'SM-G970U' }), Object.assign(event(), { installation: 'serial' }),
    Object.assign(event(), { report: 'user email@example.test' }), Object.assign(event(), { build: 'private ' + 'x'.repeat(9000) })];
  const message = event(); message.crashes[0].message = 'private content'; invalid.push(message);
  const frame = event(); frame.crashes[0].frames = ['at Foo (/data/user/0/private:42)']; invalid.push(frame);
  for (const value of invalid) assert.equal((await send(value)).status, 400);
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM installations').get().n, 0); db.close();
});

test('ninety-day retention removes inactive installations and associated data', async () => {
  const { db, env, send } = await setup(); await send(event());
  db.prepare("UPDATE installations SET last_day=date('now','-100 days')").run();
  await worker.scheduled({}, env);
  for (const table of ['installations', 'activity', 'issues']) assert.equal(db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n, 0);
  db.close();
});

test('ingest limiting runs before database writes and uses an opaque key', async () => {
  const { db, env } = await setup(); let limitedKey;
  env.INGEST_LIMITER = { async limit({ key }) { limitedKey = key; return { success: false }; } };
  const request = new Request('https://telemetry.test/v1/event', { method: 'POST', headers: {
    'content-type': 'application/json', 'CF-Connecting-IP': '192.0.2.1'
  }, body: JSON.stringify(event()) });
  assert.equal((await fetchHandler(request, env)).status, 429);
  assert.match(limitedKey, /^[0-9a-f]{64}$/);
  assert.ok(!limitedKey.includes('192.0.2.1'));
  assert.equal(db.prepare('SELECT COUNT(*) AS n FROM installations').get().n, 0); db.close();
});
