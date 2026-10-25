import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
import { writable } from "svelte/store";
import type { Request, SidecarEvent } from "./types";

type Handler = (e: SidecarEvent) => void;
interface HandlerRecord {
  handle: Handler;
  timer: ReturnType<typeof setTimeout>;
  terminal: boolean;
  destructive: boolean;
}
const handlers = new Map<string, HandlerRecord>();
const PROTOCOL_VERSION = 1 as const;
let counter = 0;
const DEFAULT_TIMEOUT_MS = 120_000;
const LONG_TIMEOUT_OPS = new Set(["scan", "duplicates", "secret_scan", "supply_audit"]);
const DESTRUCTIVE_OPS = new Set(["delete", "remove", "uninstall_run", "ports_kill", "quarantine_restore"]);

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

listen<string>("sidecar-event", (msg) => {
  let e: SidecarEvent;
  try {
    e = JSON.parse(msg.payload);
  } catch {
    return;
  }
  if (e.ev === "ready") {
    if (e.protocol !== PROTOCOL_VERSION) {
      connected.set(false);
      return;
    }
    void request({ op: "ping" }).then((reply) => connected.set(reply.ok === true)).catch(() => connected.set(false));
    return;
  }
  // Rust tarafı: sidecar süreci beklenmedik şekilde öldü (yeniden başlatma denenecek).
  if (!e.id && (e as any).code === "sidecar_exited") {
    connected.set(false);
    // Bekleyen istekleri kapat ki spinner'lar sonsuza kadar dönmesin.
    for (const [id, record] of handlers) {
      clearTimeout(record.timer);
      if (!record.terminal) {
        record.terminal = true;
        record.handle({ id, ev: "done", ok: false, outcome: "sidecar_exited" } as SidecarEvent);
      }
    }
    handlers.clear();
    inflight = 0;
    activity.set({ busy: false, op: "", label: "", done: 0, total: 0 });
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
    const record = handlers.get(e.id)!;
    if (record.terminal) return;
    record.handle(e);
    if (e.ev === "done") {
      record.terminal = true;
      clearTimeout(record.timer);
      handlers.delete(e.id);
    }
  }
});

export function nextId(prefix = "req"): string {
  counter += 1;
  return `${prefix}-${counter}`;
}

/** İstek gönder; her olay için onEvent çağrılır. done'da Promise çözülür ve done olayını döner. */
export function request(
  req: Omit<Request, "id">,
  onEvent?: Handler,
): Promise<SidecarEvent> {
  const id = nextId(req.op);
  const full: Request = { ...req, id, protocol: PROTOCOL_VERSION };
  startActivity(req.op);
  return new Promise((resolve, reject) => {
    let settled = false;
    const handle = (e: SidecarEvent) => {
      onEvent?.(e);
      if (e.ev === "done" && !settled) {
        settled = true;
        endActivity();
        resolve(e);
      }
    };
    const timeoutMs = LONG_TIMEOUT_OPS.has(req.op) ? 15 * 60_000 : DEFAULT_TIMEOUT_MS;
    const timer = setTimeout(() => {
      const record = handlers.get(id);
      if (!record || record.terminal) return;
      record.terminal = true;
      handlers.delete(id);
      const outcome = record.destructive ? "unknown" : "timeout";
      handle({ id, ev: "done", ok: false, outcome, retryable: !record.destructive } as SidecarEvent);
      if (!record.destructive) void cancel(id).catch(() => undefined);
    }, timeoutMs);
    handlers.set(id, { handle, timer, terminal: false, destructive: DESTRUCTIVE_OPS.has(req.op) });
    void invoke("send_request", { line: JSON.stringify(full) }).catch((error) => {
      const record = handlers.get(id);
      if (record) clearTimeout(record.timer);
      handlers.delete(id);
      if (!settled) {
        settled = true;
        endActivity();
        reject(error);
      }
    });
  });
}

/** Çalışan bir isteği iptal et. */
export function cancel(id: string) {
  return invoke("send_request", {
    line: JSON.stringify({ id, op: "cancel", protocol: PROTOCOL_VERSION }),
  });
}
