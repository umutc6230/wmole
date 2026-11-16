const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

function load(name, mocks) {
  const source = fs.readFileSync(path.join(__dirname, '../src/lib', name), 'utf8');
  const code = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
  }}).outputText;
  const module = { exports: {} };
  new Function('require', 'module', 'exports', code)(id => {
    if (!(id in mocks)) throw new Error(`Unexpected import: ${id}`);
    return mocks[id];
  }, module, module.exports);
  return module.exports;
}

function harness(invoke) {
  const listeners = {}, stores = [], toasts = [];
  const api = load('sidecar.ts', {
    '@tauri-apps/api/event': { listen: async (name, callback) => { listeners[name] = callback; return () => {}; } },
    '@tauri-apps/api/core': { invoke },
    'svelte/store': { writable(value) {
      const store = { value, set(v) { store.value = v; }, update(fn) { store.value = fn(store.value); } };
      stores.push(store); return store;
    } },
    './toast': { toast: (...args) => toasts.push(args) },
    './i18n': { tr: x => x },
  });
  const emit = e => listeners['sidecar-event']({ payload: JSON.stringify(e) });
  return { api, listeners, stores, toasts, emit };
}
const tick = () => new Promise(resolve => setImmediate(resolve));

test('transport failure settles and clears activity and mutation lock', async () => {
  const h = harness(async () => { throw new Error('pipe closed'); });
  const done = await h.api.request({ op: 'delete', targets: ['fixture'] });
  assert.equal(done.ok, false);
  assert.match(done.error, /pipe closed/);
  assert.equal(h.api.mutating.value, false);
  assert.equal(h.api.activity.value.busy, false);
  assert.equal(h.toasts.length, 1);
});

test('sidecar exit finishes every waiting request', async () => {
  const h = harness(async () => {});
  const pending = h.api.request({ op: 'scan' });
  await tick();
  h.listeners['sidecar-exit']();
  assert.equal((await pending).ok, false);
  assert.equal(h.api.connected.value, false);
  assert.equal(h.api.activity.value.busy, false);
});

test('duplicate mutation never reaches the backend; first request can finish', async () => {
  const calls = [];
  const h = harness(async (cmd, args) => calls.push(JSON.parse(args.line)));
  const first = h.api.request({ op: 'delete' });
  const second = await h.api.request({ op: 'delete' });
  await tick();
  assert.equal(second.ok, false);
  assert.equal(calls.length, 1);
  h.emit({ id: calls[0].id, ev: 'done', ok: true });
  assert.equal((await first).ok, true);
  assert.equal(h.api.mutating.value, false);
});

test('throwing UI callback cannot strand a completed request', async () => {
  let req;
  const h = harness(async (_, args) => { req = JSON.parse(args.line); });
  const pending = h.api.request({ op: 'scan' }, () => { throw new Error('render failed'); });
  await tick();
  h.emit({ id: req.id, ev: 'done', ok: true });
  await pending;
  assert.equal(h.api.activity.value.busy, false);
});

test('only completed successful real deletions remove rows', async () => {
  const events = [
    { ev: 'item_result', path: 'removed', ok: true, completed: true },
    { ev: 'item_result', path: 'locked', ok: false },
    { ev: 'item_result', path: 'partial-temp', ok: true, completed: false },
    { ev: 'item_result', path: 'preview', ok: true, dry_run: true },
  ];
  const deletion = load('deletion.ts', {
    './sidecar': { request: async (_, onEvent) => { events.forEach(onEvent); return { ok: false, cancelled: true }; } },
    './toast': { toast() {} }, './i18n': { tr: x => x },
  });
  const removed = await deletion.deleteSelection(['removed', 'locked', 'partial-temp', 'preview', 'not-started'], false);
  assert.deepEqual([...removed], ['removed']);
});
