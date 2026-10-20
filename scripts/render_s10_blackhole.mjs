// SPDX-License-Identifier: GPL-3.0-or-later
// Offline WebGL asset renderer; the phone never loads a browser or shader.
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
const option = (name) => args[args.indexOf(name) + 1];
if (!args.includes('--browser') || !args.includes('--output')) {
  throw new Error('Pass --browser <Chromium executable> and --output <new directory>.');
}
const browser = option('--browser');
const output = resolve(option('--output'));
const source = fileURLToPath(new URL('../target/beyond1lte/oneui9/settings-branding/blackhole.frag', import.meta.url));
const fragment = await readFile(source, 'utf8');
const profile = await mkdtemp(join(tmpdir(), 's10-blackhole-'));
const child = spawn(browser, ['--headless=new', '--no-first-run', '--no-default-browser-check',
  '--disable-extensions', '--disable-background-networking', '--use-angle=swiftshader',
  '--enable-unsafe-swiftshader', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'],
  { stdio: 'ignore' });
let ws;
try {
  let port;
  for (let attempt = 0; attempt < 100; attempt++) {
    try { port = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break; }
    catch { await new Promise((done) => setTimeout(done, 100)); }
  }
  if (!port) throw new Error('The temporary headless browser did not start.');
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((done, reject) => { ws.addEventListener('open', done); ws.addEventListener('error', reject); });
  let sequence = 0;
  const pending = new Map();
  ws.addEventListener('message', ({ data }) => {
    const message = JSON.parse(data);
    if (message.id && pending.has(message.id)) {
      const [done, reject] = pending.get(message.id);
      pending.delete(message.id);
      message.error ? reject(new Error(JSON.stringify(message.error))) : done(message.result);
    }
  });
  const send = (method, params = {}) => new Promise((done, reject) => {
    const id = ++sequence; pending.set(id, [done, reject]); ws.send(JSON.stringify({ id, method, params }));
  });
  const evaluate = async (expression) => {
    const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const renderer = (fragment) => {
    const canvas = document.createElement('canvas');
    canvas.width = 640; canvas.height = 360;
    const gl = canvas.getContext('webgl', { alpha: false, antialias: false, preserveDrawingBuffer: true });
    if (!gl) throw new Error('WebGL unavailable.');
    const compile = (type, source) => {
      const shader = gl.createShader(type); gl.shaderSource(shader, source); gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
      return shader;
    };
    const program = gl.createProgram();
    gl.attachShader(program, compile(gl.VERTEX_SHADER, 'attribute vec2 P;void main(){gl_Position=vec4(P,0.,1.);}'));
    gl.attachShader(program, compile(gl.FRAGMENT_SHADER, fragment));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
    gl.useProgram(program);
    const buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,3,-1,-1,3]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, 'P');
    gl.enableVertexAttribArray(position); gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
    const uniform = (name) => gl.getUniformLocation(program, name);
    gl.uniform2f(uniform('R'), 640, 360); gl.uniform2f(uniform('M'), .5, .5);
    gl.uniform3f(uniform('A'), 1, 233/255, 199/255);
    gl.uniform3f(uniform('B'), 217/255, 144/255, 74/255);
    gl.uniform3f(uniform('C'), 139/255, 143/255, 181/255);
    gl.uniform3f(uniform('K'), .5, .5, 100); gl.uniform1f(uniform('S'), 0);
    gl.viewport(0, 0, 640, 360);
    const composite = document.createElement('canvas'); composite.width = 640; composite.height = 360;
    const context = composite.getContext('2d');
    const snapshot = (time) => {
      gl.uniform1f(uniform('T'), time); gl.drawArrays(gl.TRIANGLES, 0, 3); gl.finish();
      const copy = document.createElement('canvas'); copy.width = 640; copy.height = 360;
      copy.getContext('2d').drawImage(canvas, 0, 0); return copy;
    };
    const first = snapshot(18);
    window.renderBlackhole = (index) => {
      const current = snapshot(18 + index / 18);
      context.globalAlpha = 1; context.drawImage(current, 0, 0);
      // Blend the final six frames back to the opening frame for a seamless loop.
      if (index >= 30) { context.globalAlpha = (index - 29) / 7; context.drawImage(first, 0, 0); }
      context.globalAlpha = 1;
      return composite.toDataURL('image/webp', .94).split(',')[1];
    };
    return gl.getParameter(gl.VERSION);
  };
  console.log(await evaluate(`(${renderer.toString()})(${JSON.stringify(fragment)})`));
  await mkdir(output);
  for (let index = 0; index < 36; index++) {
    const encoded = await evaluate(`window.renderBlackhole(${index})`);
    await writeFile(join(output, `s10_blackhole_${String(index).padStart(2, '0')}.webp`), Buffer.from(encoded, 'base64'));
  }
  console.log(`Rendered 36 frames, 640 × 360, ${(640 * 360 * 4 * 36 / 1024 / 1024).toFixed(1)} MiB decoded.`);
} finally {
  if (ws) ws.close();
  child.kill();
  await new Promise((done) => setTimeout(done, 500));
  await rm(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 });
}
