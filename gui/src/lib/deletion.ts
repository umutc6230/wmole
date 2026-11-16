import { request } from "./sidecar";
import type { SidecarEvent } from "./types";
import { toast } from "./toast";
import { tr } from "./i18n";

/** Only a successful, complete item result is evidence that a row can go away. */
export function completedPaths(events: SidecarEvent[]): Set<string> {
  return new Set(events.filter(e => e.ev === "item_result" && e.ok &&
    e.completed !== false && !e.dry_run).map(e => String(e.path)));
}

export async function deleteSelection(
  targets: string[], permanent: boolean, dryRun = false,
  onEvent?: (event: SidecarEvent) => void,
): Promise<Set<string>> {
  const events: SidecarEvent[] = [];
  const done = await request({ op: "delete", targets, permanent, dry_run: dryRun }, e => {
    if (e.ev === "item_result") events.push(e);
    onEvent?.(e);
  });
  const completed = events.filter(e => e.ok && e.completed !== false).length;
  const remaining = targets.length - completed;
  const details = events.flatMap(e => [e.error, ...((e.report as any)?.details ?? [])
    .map((d: any) => `${d.path}: ${d.reason}`)]).filter(Boolean);
  const message = `${dryRun ? tr("Dry-run:") : tr("Temizlik:")} ${completed} ${tr("tamamlandı")}, ${remaining} ${tr("öğe kaldı")}`;
  toast(message + (details.length ? ` · ${String(details[0])}` : ""),
    remaining || !done.ok ? "err" : "ok");
  return completedPaths(events);
}
