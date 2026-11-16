// Run with: playwright-cli -s=wmole-review run-code --filename=gui/tests/browser-smoke.js
// Vite must be running. All IPC is mocked; this never touches user files.
async (page) => {
  await page.addInitScript(() => {
    localStorage.setItem('wmole-onboarded', '1');
    localStorage.setItem('wmole-lang', 'tr');
    const callbacks = new Map(), listeners = new Map();
    let counter = 0;
    window.__wmoleTest = { deletes: [], failScan: false };
    const emit = e => {
      const cb = listeners.get('sidecar-event');
      if (cb) callbacks.get(cb)({ payload: JSON.stringify(e) });
    };
    window.__TAURI_EVENT_PLUGIN_INTERNALS__ = { unregisterListener() {} };
    window.__TAURI_INTERNALS__ = {
      metadata: { currentWindow: { label: 'main' }, currentWebview: { label: 'main' } },
      transformCallback(fn) { const id = ++counter; callbacks.set(id, fn); return id; },
      unregisterCallback(id) { callbacks.delete(id); },
      async invoke(cmd, args = {}) {
        if (cmd === 'plugin:event|listen') { listeners.set(args.event, args.handler); return args.handler; }
        if (cmd === 'plugin:app|version') return '0.9.1';
        if (cmd === 'check_update') return { available: false, current: '0.9.1', latest: '0.9.1' };
        if (cmd !== 'send_request') return false;
        const req = JSON.parse(args.line);
        if (req.op === 'scan' && window.__wmoleTest.failScan) {
          window.__wmoleTest.failScan = false;
          throw new Error('test: pipe closed');
        }
        if (req.op === 'delete') window.__wmoleTest.deletes.push(req);
        setTimeout(() => {
          emit({ id: req.id, ev: 'started' });
          if (req.op === 'scan') {
            for (const name of ['safe.tmp', 'locked.tmp'])
              emit({ id: req.id, ev: 'item', path: `C:\\fixtures\\${name}`, name, size: 10, selected: true, kind: 'temp' });
          }
          if (req.op === 'delete') {
            for (const path of req.targets)
              emit({ id: req.id, ev: 'item_result', path, ok: !path.endsWith('locked.tmp'),
                error: path.endsWith('locked.tmp') ? 'test: locked' : undefined, completed: true });
          }
          emit({ id: req.id, ev: 'done', ok: true, payload: req.op === 'security_overview'
            ? { quarantine: [], config: {} } : req.op === 'cleanup_history' ? { recent: [], count: 0, total_freed: 0 } : {} });
        }, 50);
      },
    };
  });
  await page.goto('http://127.0.0.1:1420/');
  await page.getByRole('button', { name: 'Temizle', exact: true }).waitFor();
  console.log('Mocked desktop UI ready');
}
