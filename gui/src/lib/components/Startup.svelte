<script lang="ts">
  import { onMount } from "svelte";
  import { request } from "$lib/sidecar";
  import type { SidecarEvent } from "$lib/types";
  import { toast } from "$lib/toast";
  import { tr } from "$lib/i18n";
  import { t } from "$lib/i18n";

  interface Entry { path: string; name: string; location: string; enabled: boolean; }
  let items = $state<Entry[]>([]);
  let loading = $state(false);

  async function load() {
    items = [];
    loading = true;
    const buf: Entry[] = [];
    await request({ op: "startup_list" }, (e: SidecarEvent) => {
      if (e.ev === "item") buf.push(e as unknown as Entry);
    });
    items = buf;
    loading = false;
  }
  onMount(load);

  // Girdi silinmez; Windows'un (Görev Yöneticisi) kullandığı bayrak değişir, geri alınabilir.
  async function toggle(e: Entry) {
    let reason = "";
    const d = await request({ op: "startup_set", name: e.name, location: e.location, enabled: !e.enabled },
      (ev: SidecarEvent) => { if (ev.ev === "error") reason = String(ev.message ?? ""); });
    toast(d.ok
      ? `${e.name} ${tr(e.enabled ? "devre dışı bırakıldı" : "etkinleştirildi")}`
      : `${tr("İşlem başarısız")}${reason ? ": " + reason : ""}`, d.ok ? "ok" : "err");
    load();
  }
</script>

<div class="view">
  <div class="toolbar">
    <h2>{$t("Başlangıç Programları")}</h2>
    <button onclick={load} disabled={loading}>{loading ? "…" : $t("Yenile")}</button>
    <span class="count">{items.length} {$t("girdi")}</span>
  </div>
  <div class="list">
    {#each items as e (e.location + e.name)}
      <div class="entry" class:off={!e.enabled}>
        <span class="name">{e.name}{#if !e.enabled} <em>({$t("kapalı")})</em>{/if}</span>
        <span class="loc">{e.location}</span>
        <span class="cmd">{e.path}</span>
        <button class="mini" onclick={() => toggle(e)}>{$t(e.enabled ? "Devre Dışı Bırak" : "Etkinleştir")}</button>
      </div>
    {/each}
    {#if !items.length && !loading}<p class="muted">{$t("Başlangıç girdisi yok.")}</p>{/if}
  </div>
</div>

<style>
  .view { display: flex; flex-direction: column; height: 100%; font-family: monospace; }
  .toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
  h2 { margin: 0; color: var(--fg); }
  .count { color: var(--muted); font-size: 12px; }
  button { background: var(--btn); color: var(--fg); border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-family: monospace; }
  .entry.off .name, .entry.off .cmd { opacity: 0.5; }
  em { color: var(--faint); font-style: normal; font-size: 11px; }
  button.mini { padding: 2px 8px; font-size: 12px; }
  .list { flex: 1; min-height: 0; overflow: auto; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 6px; }
  .entry { display: flex; gap: 12px; align-items: center; padding: 6px 10px; border-radius: 4px; }
  .entry:hover { background: var(--border); }
  .name { color: var(--fg); min-width: 160px; }
  .loc { color: #d29922; min-width: 110px; font-size: 11px; }
  .cmd { color: var(--faint); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
  .muted { color: var(--faint); padding: 12px; }
</style>
