// SPDX-License-Identifier: GPL-3.0-or-later
const MODELS = new Set(['SM-G970F', 'SM-G973F', 'SM-G975F']);
const CATEGORIES = new Set(['boot', 'camera', 'fingerprint', 'audio', 'dex', 'battery', 'performance', 'display', 'other']);
const COMPONENTS = new Set(['system_server', 'com.android.systemui', 'com.android.settings', 'com.sec.android.app.camera',
  'com.sec.android.app.launcher', 'com.samsung.android.smartsuggestions']);
const MODES = new Set(['rom', 'stock', 'auto', 'oc', 'unknown']);
const response = (body, status = 200) => Response.json(body, { status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
const exact = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);

export function validate(value) {
  if (!exact(value, ['schema', 'installation', 'model', 'build', 'oc_mode', 'crashes', 'report']) || value.schema !== 1
      || !uuid(value.installation) || !MODELS.has(value.model) || typeof value.build !== 'string'
      || !/^v[0-9]{1,4}(?:[._-][A-Za-z0-9]+){0,4}$/.test(value.build) || !MODES.has(value.oc_mode)
      || !Array.isArray(value.crashes) || value.crashes.length > 12
      || !(value.report === null || CATEGORIES.has(value.report))) throw new Error('Invalid event');
  for (const crash of value.crashes) {
    if (!exact(crash, ['signature', 'component', 'exception', 'frames']) || !/^[0-9a-f]{64}$/.test(crash.signature)
        || !COMPONENTS.has(crash.component) || typeof crash.exception !== 'string' || !/^[A-Za-z_$][A-Za-z0-9_.$]{0,159}$/.test(crash.exception)
        || !Array.isArray(crash.frames) || crash.frames.length > 3
        || crash.frames.some(frame => typeof frame !== 'string' || !/^[A-Za-z_$][A-Za-z0-9_.$]{0,199}$/.test(frame))) throw new Error('Invalid crash summary');
  }
  return value;
}

async function read(request) {
  if (!(request.headers.get('content-type') || '').startsWith('application/json')) throw new Error('JSON required');
  const reader = request.body?.getReader();
  if (!reader) throw new Error('Body required');
  const chunks = []; let size = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      if ((size += value.byteLength) > 8192) throw new Error('Event too large');
      chunks.push(value);
    }
  } finally { await reader.cancel(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
}

async function installationId(id, secret) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', encoder.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return [...new Uint8Array(await crypto.subtle.sign('HMAC', key, encoder.encode(id)))].map(byte => byte.toString(16).padStart(2, '0')).join('');
}

async function authorised(request, secret) {
  if (!secret || secret.length < 32) return false;
  const encoder = new TextEncoder();
  const hashes = await Promise.all([request.headers.get('Authorization') || '', `Bearer ${secret}`]
    .map(value => crypto.subtle.digest('SHA-256', encoder.encode(value))));
  const left = new Uint8Array(hashes[0]), right = new Uint8Array(hashes[1]); let difference = 0;
  for (let i = 0; i < left.length; i++) difference |= left[i] ^ right[i];
  return difference === 0;
}

export async function fetchHandler(request, env) {
  const path = new URL(request.url).pathname;
  if (request.method === 'GET' && path === '/') return new Response(DASHBOARD, { headers: {
    'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
    'Referrer-Policy': 'no-referrer'
  } });
  if (request.method === 'GET' && path === '/v1/stats') {
    if (!await authorised(request, env.ADMIN_TOKEN)) return response({ error: 'Unauthorised' }, 401);
    const results = await env.DB.batch([
      env.DB.prepare(`SELECT COUNT(*) AS known_installations, SUM(last_day=date('now')) AS active_today,
        SUM(last_day>=date('now','-6 days')) AS active_7_days, SUM(last_day>=date('now','-29 days')) AS active_30_days FROM installations`),
      env.DB.prepare(`SELECT model,build,COUNT(*) AS known_installations,SUM(last_day>=date('now','-6 days')) AS active_7_days FROM installations GROUP BY model,build ORDER BY model,build`),
      env.DB.prepare(`SELECT day,COUNT(*) AS active_installations FROM activity WHERE day>=date('now','-29 days') GROUP BY day ORDER BY day`),
      env.DB.prepare(`SELECT model,build,category,signature,component,exception,frames,COUNT(*) AS daily_reports,COUNT(DISTINCT installation) AS affected_installations
        FROM issues WHERE day>=date('now','-29 days') GROUP BY model,build,category,signature,component,exception,frames ORDER BY affected_installations DESC LIMIT 100`)
    ]);
    return response({ scope: 'Opted-in installations; resets/reinstalls may create a new installation', retention_days: 90,
      totals: results[0].results[0], models: results[1].results, daily: results[2].results, issues: results[3].results });
  }
  if (request.method !== 'POST' || !['/v1/event', '/v1/forget'].includes(path)) return response({ error: 'Not found' }, 404);
  if (!env.DB || !env.INSTALLATION_SALT || env.INSTALLATION_SALT.length < 32) return response({ error: 'Service not configured' }, 503);
  if (env.INGEST_LIMITER) {
    const key = await installationId('ingest:' + (request.headers.get('CF-Connecting-IP') || 'unknown'), env.INSTALLATION_SALT);
    if (!(await env.INGEST_LIMITER.limit({ key })).success) return response({ error: 'Too many requests' }, 429);
  }
  let event;
  try { event = await read(request); if (path === '/v1/event') validate(event);
    else if (!exact(event, ['installation']) || !uuid(event.installation)) throw new Error('Invalid installation');
  } catch { return response({ error: 'Invalid payload' }, 400); }
  const id = await installationId(event.installation, env.INSTALLATION_SALT);
  if (path === '/v1/forget') {
    await env.DB.batch(['issues', 'activity', 'installations'].map(table => env.DB.prepare(`DELETE FROM ${table} WHERE ${table === 'installations' ? 'id' : 'installation'}=?`).bind(id)));
    return response({ deleted: true });
  }
  const commands = [env.DB.prepare(`INSERT INTO installations(id,first_day,last_day,model,build) VALUES(?,date('now'),date('now'),?,?)
    ON CONFLICT(id) DO UPDATE SET last_day=date('now'),model=excluded.model,build=excluded.build`).bind(id, event.model, event.build),
    env.DB.prepare(`INSERT INTO activity(installation,day,model,build,oc_mode) VALUES(?,date('now'),?,?,?)
      ON CONFLICT(installation,day) DO UPDATE SET model=excluded.model,build=excluded.build,oc_mode=excluded.oc_mode`).bind(id, event.model, event.build, event.oc_mode)];
  for (const issue of event.crashes) commands.push(env.DB.prepare(`INSERT OR IGNORE INTO issues(installation,day,model,build,category,signature,component,exception,frames)
    VALUES(?,date('now'),?,?,'crash',?,?,?,?)`).bind(id, event.model, event.build, issue.signature, issue.component, issue.exception, JSON.stringify(issue.frames)));
  if (event.report) commands.push(env.DB.prepare(`INSERT OR IGNORE INTO issues(installation,day,model,build,category,signature,component,exception,frames)
    VALUES(?,date('now'),?,?,?,?,'','','[]')`).bind(id, event.model, event.build, event.report, event.report));
  await env.DB.batch(commands);
  return response({ accepted: true });
}

export default {
  fetch: fetchHandler,
  async scheduled(_event, env) {
    await env.DB.batch([
      env.DB.prepare("DELETE FROM issues WHERE day<date('now','-89 days')"),
      env.DB.prepare("DELETE FROM activity WHERE day<date('now','-89 days')"),
      env.DB.prepare("DELETE FROM installations WHERE last_day<date('now','-89 days')")
    ]);
  }
};

const DASHBOARD = `<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ArtisanROM istatistikleri</title><style>body{font:16px system-ui;background:#10131b;color:#eee;max-width:1000px;margin:32px auto;padding:16px}input,button{font:inherit;padding:10px;margin:4px}pre{white-space:pre-wrap;background:#1c2331;padding:20px;border-radius:12px}</style>
<h1>ArtisanROM</h1><p>Katılan kurulumlar, aktif kullanım ve sorun özetleri</p>
<form><input type="password" autocomplete="off" placeholder="Yönetim anahtarı" aria-label="Yönetim anahtarı"><button>İstatistikleri göster</button></form>
<p id="state">Anahtar yalnız bu sayfanın belleğinde kullanılır.</p><pre id="result"></pre>
<script>document.querySelector('form').onsubmit=async e=>{e.preventDefault();const state=document.querySelector('#state');state.textContent='Yükleniyor…';try{const r=await fetch('/v1/stats',{headers:{Authorization:'Bearer '+document.querySelector('input').value}});if(!r.ok)throw Error('Erişim reddedildi veya hizmet hazır değil');const d=await r.json();state.textContent='Veriler son 90 gün içinde katılan kurulumları kapsar.';document.querySelector('#result').textContent=JSON.stringify(d,null,2);}catch(x){state.textContent=x.message;}};</script></html>`;
