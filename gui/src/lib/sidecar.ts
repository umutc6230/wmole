import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
import { writable } from "svelte/store";
import type { Request, SidecarEvent } from "./types";
import { toast } from "./toast";
import { tr } from "./i18n";

type Handler = (e: SidecarEvent) => void;
const handlers = new Map<string, Handler>();
let counter = 0;

export const connected = writable(false);

/** Uygulama geneli canlı durum: aktif istek sayısı + son ilerleme bilgisi. */
export const activity = writable<{
  busy: boolean;
  op: string;
  label: string;
  done: number;
  total: number;
}>({ busy: false, op: "", label: "", done: 0, total: 0 });

let inflight = 0;

function startActivity(op: string) {
  inflight += 1;
  activity.update((a) => ({ ...a, busy: true, op }));
}
function endActivity() {
  inflight = Math.max(0, inflight - 1);
  if (inflight === 0) activity.set({ busy: false, op: "", label: "", done: 0, total: 0 });
}

const eventListener = listen<string>("sidecar-event", (msg) => {
  let e: SidecarEvent;
  try {
    e = JSON.parse(msg.payload);
  } catch {
    return;
  }
  if (e.ev === "ready") {
    connected.set(true);
    return;
  }
  if (e.ev === "progress") {
    activity.update((a) => ({
      ...a,
      busy: true,
      label: String((e as any).label ?? ""),
      done: Number((e as any).done ?? 0),
      total: Number((e as any).total ?? 0),
    }));
  }
  if (e.id && handlers.has(e.id)) {
    connected.set(true);
    handlers.get(e.id)!(e);
    if (e.ev === "done") handlers.delete(e.id);
  }
});

// Sidecar çöktüyse hiçbir istek artık "done" almaz: hepsini başarısız kapat.
const exitListener = listen("sidecar-exit", () => {
  connected.set(false);
  for (const [id, handler] of [...handlers]) {
    handlers.delete(id);
    handler({ id, ev: "done", ok: false, error: "sidecar exited" } as unknown as SidecarEvent);
  }
});

export function nextId(prefix = "req"): string {
  counter += 1;
  return `${prefix}-${counter}`;
}

/** İstek gönder; her olay için onEvent çağrılır. done'da Promise çözülür ve done olayını döner. */
export const mutating = writable(false);
let mutationActive = false;
const mutations = new Set(["delete", "remove", "quarantine_empty", "quarantine_restore",
  "settings_set", "schedule_set", "schedule_clear", "startup_set", "optimize_run",
  "uninstall_run", "ports_kill", "update", "journal"]);

/** Always settles with a terminal event, including transport failures. Inspect ok. */
export function request(req: Omit<Request, "id">, onEvent?: Handler): Promise<SidecarEvent> {
  const id = nextId(req.op);
  const full: Request = { ...req, id };
  const mutation = mutations.has(req.op);
  if (mutation && mutationActive) {
    const done: SidecarEvent = { id, ev: "done", ok: false, error: tr("Başka bir işlem sürüyor") };
    toast(String(done.error), "err");
    onEvent?.(done);
    return Promise.resolve(done);
  }
  if (mutation) { mutationActive = true; mutating.set(true); }
  startActivity(req.op);
  return new Promise(resolve => {
    let settled = false;
    let lastError = "";
    let timer: ReturnType<typeof setTimeout>;
    const finish = (event: SidecarEvent) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      handlers.delete(id);
      endActivity();
      if (mutation) { mutationActive = false; mutating.set(false); }
      if (!event.ok && !event.cancelled)
        toast(String(event.error || lastError || tr("İşlem başarısız")), "err");
      resolve(event);
    };
    const resetTimeout = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        void cancel(id).catch(() => {});
        const event: SidecarEvent = { id, ev: "done", ok: false, error: tr("İşlem zaman aşımına uğradı") };
        try { onEvent?.(event); } finally { finish(event); }
      }, 10 * 60 * 1000);
    };
    const handler: Handler = e => {
      resetTimeout();
      if (e.ev === "error") lastError = String(e.message ?? "");
      try { onEvent?.(e); }
      catch (error) { lastError = String(error); }
      finally { if (e.ev === "done") finish(e); }
    };
    handlers.set(id, handler);
    resetTimeout();
    void Promise.all([eventListener, exitListener])
      .then(() => invoke("send_request", { line: JSON.stringify(full) }))
      .catch(error => handler({ id, ev: "done", ok: false, error: String(error) }));
  });
}

export function cancel(id: string) {
  return invoke("send_request", { line: JSON.stringify({ id, op: "cancel" }) });
}

export async function reconnect() {
  try {
    await invoke("restart_sidecar");
    await request({ op: "ping" });
  } catch (error) { toast(String(error), "err"); }
}
