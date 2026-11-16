<script lang="ts">
  import { deleteSelection } from "$lib/deletion";
  import { mutating } from "$lib/sidecar";
  import { onMount, onDestroy } from "svelte";
  import { request } from "$lib/sidecar";
  import type { ScanItem, SidecarEvent } from "$lib/types";
  import ConfirmModal from "./ConfirmModal.svelte";
  import VirtualList from "./VirtualList.svelte";
  import StatusBar from "./StatusBar.svelte";
  import { toast } from "$lib/toast";
  import { notify } from "$lib/notify";
  import { t, tr } from "$lib/i18n";
  import { theme } from "$lib/theme";

  let { onNavigate = () => {} }: { onNavigate?: (view: string) => void } = $props();

  let s = $state<Record<string, any>>({});
  // Özet karoları için: açık başlangıç girdisi sayısı ve karantina boyutu.
  let startupOn = $state<number | null>(null);
  let quarantine = $state<{ count: number; bytes: number } | null>(null);
  let hist = $state<Record<string, any>>({});
  let timer: ReturnType<typeof setInterval>;

  // Hızlı temizlik durumu
  let scanItems = $state<ScanItem[]>([]);
  let scanning = $state(false);
  let scanned = $state(false);
  let confirmOpen = $state(false);
  let progress = $state({ done: 0, total: 0, label: "" });

  let chosen = $derived(scanItems.filter((i) => i.selected));
  let reclaimable = $derived(chosen.reduce((a, i) => a + (i.size || 0), 0));

  function toggle(it: ScanItem) {
    it.selected = !it.selected;
    scanItems = [...scanItems];
  }
  function setAll(v: boolean) {
    scanItems.forEach((i) => (i.selected = v));
    scanItems = [...scanItems];
  }

  function fmt(n: number) {
    const u = ["B", "KB", "MB", "GB", "TB"];
    let i = 0,
      v = n;
    while (v >= 1024 && i < u.length - 1) {
      v /= 1024;
      i++;
    }
    return v.toFixed(1) + " " + u[i];
  }
  function color(p: number, warn = 75, crit = 90) {
    return p >= crit ? "#e5534b" : p >= warn ? "#d29922" : "#58d6a0";
  }

  // Health counts *down*: 100 is good, so it is toned on its inverse.
  let metrics = $derived([
    { label: "Disk", value: s.disk_percent ?? 0, tone: color(s.disk_percent ?? 0),
      display: s.disk_percent != null ? `${s.disk_percent}%` : "—" },
    { label: "RAM", value: s.memory_percent ?? 0, tone: color(s.memory_percent ?? 0),
      display: s.memory_percent != null ? `${s.memory_percent}%` : "—" },
    { label: "CPU", value: s.cpu_percent ?? 0, tone: color(s.cpu_percent ?? 0),
      display: s.cpu_percent != null ? `${s.cpu_percent}%` : "—" },
    { label: "Sağlık", value: s.health ?? 0, tone: color(100 - (s.health ?? 0)),
      display: s.health != null ? `${s.health}/100` : "—" },
  ]);

  const METER_STYLE: Record<string, "bars" | "tiles" | "gauges"> = {
    fluent: "bars", linear: "bars", cards: "tiles", bento: "tiles", hud: "gauges",
  };
  let meterStyle = $derived(METER_STYLE[$theme] ?? "bars");

  async function poll() {
    const done = await request({ op: "status" });
    if (done.payload) s = done.payload as Record<string, any>;
  }
  async function loadHistory() {
    const done = await request({ op: "cleanup_history" });
    if (done.payload) hist = done.payload as Record<string, any>;
  }

  async function loadSummary() {
    let on = 0;
    await request({ op: "startup_list" }, (e: SidecarEvent) => {
      if (e.ev === "item" && (e as any).enabled !== false) on++;
    });
    startupOn = on;
    const sec = await request({ op: "security_overview", limit: 1 });
    const rows = ((sec.payload as any)?.quarantine ?? []) as { size?: number }[];
    quarantine = { count: rows.length, bytes: rows.reduce((a, r) => a + (r.size || 0), 0) };
  }

  // Tek cümlelik durum: en acil sorun neyse onu söyler.
  let verdict = $derived(
    (s.disk_percent ?? 0) >= 90
      ? { tone: "var(--danger)", text: "Disk neredeyse dolu" }
      : (s.memory_percent ?? 0) >= 90
        ? { tone: "var(--warn)", text: "Bellek kullanımı yüksek" }
        : (s.disk_percent ?? 0) >= 75
          ? { tone: "var(--warn)", text: "Disk dolmaya başladı" }
          : { tone: "var(--ok)", text: "Sistem iyi durumda" },
  );

  async function quickScan() {
    if ($mutating || scanning) return;
    scanItems = [];
    scanning = true;
    scanned = false;
    const buf: ScanItem[] = [];
    await request({ op: "scan", mode: "clean" }, (e: SidecarEvent) => {
      if (e.ev === "item" && (e as any).selected) buf.push(e as unknown as ScanItem);
    });
    scanItems = buf;
    scanning = false;
    scanned = true;
  }

  async function quickClean(permanent: boolean) {
    if ($mutating) return;
    confirmOpen = false;
    const targets = chosen.map(i => i.path);
    const removed = await deleteSelection(targets, permanent, false, e => {
      
      if (e.ev === "progress") progress = { done: Number(e.done), total: Number(e.total), label: String(e.label ?? "") };
    });
    scanItems = scanItems.filter(i => !removed.has(i.path));
    progress = { done: 0, total: 0, label: "" };
    scanned = scanItems.length > 0;
    await loadHistory();
    await loadSummary();
  }

  onMount(() => {
    poll();
    loadHistory();
    loadSummary();
    timer = setInterval(poll, 2000);
  });
  onDestroy(() => clearInterval(timer));
</script>

<div class="dash">
  <h2>{$t("Gösterge Paneli")}</h2>

  <!-- Akıllı tarama: tek cümlelik durum + tek birincil eylem + tıklanabilir özet karoları. -->
  <section class="hero surface">
    <div class="hero-main">
      <span class="verdict" style="--tone:{verdict.tone}">{$t(verdict.text)}</span>
      <p class="hero-sub">
        {#if scanning}
          {$t("Taranıyor…")}
        {:else if scanned && chosen.length}
          {$t("Geri kazanılabilir:")} <strong>{fmt(reclaimable)}</strong>
        {:else if scanned}
          {$t("✓ Temizlenecek önemli bir şey yok")}
        {:else}
          {$t("Güvenli temizlik adaylarını tara ve tek tıkla temizle.")}
        {/if}
      </p>
      <button
        class="cta"
        disabled={scanning || $mutating}
        onclick={() => (scanned && chosen.length ? (confirmOpen = true) : quickScan())}
      >
        {scanning
          ? $t("Taranıyor…")
          : scanned && chosen.length
            ? `${$t("Hızlı Temizle")} (${chosen.length})`
            : scanned
              ? $t("Yeniden Tara")
              : $t("Hızlı Tara")}
      </button>
    </div>
    <div class="hero-tiles">
      <button class="stat" onclick={quickScan} disabled={scanning || $mutating}>
        <span>{$t("Geri kazanılabilir")}</span>
        <strong style="color:var(--ok)">{scanned ? fmt(reclaimable) : "—"}</strong>
        <em>{$t(scanned ? "seçili öğeler" : "taramak için tıkla")}</em>
      </button>
      <button class="stat" onclick={() => onNavigate("Analyze")}>
        <span>{$t("Boş alan")}</span>
        <strong style="color:{color(s.disk_percent ?? 0)}">{s.disk_free ? fmt(s.disk_free) : "—"}</strong>
        <em>{$t("en büyük klasörleri gör")}</em>
      </button>
      <button class="stat" onclick={() => onNavigate("Startup")}>
        <span>{$t("Başlangıç")}</span>
        <strong>{startupOn ?? "—"}</strong>
        <em>{$t("açılışta çalışan program")}</em>
      </button>
      <button class="stat" onclick={() => onNavigate("Security")}>
        <span>{$t("Karantina")}</span>
        <strong>{quarantine ? fmt(quarantine.bytes) : "—"}</strong>
        <em>{quarantine?.count ?? 0} {$t("öğe geri alınabilir")}</em>
      </button>
    </div>
  </section>

  <!-- Metreler. Sunum biçimi aktif layout temasına göre değişir:
       çubuk (Fluent/Linear), döşeme (Cards/Bento), kadran (HUD). -->
  <div class="meters surface" class:tiles={meterStyle === "tiles"}>
    {#if meterStyle === "gauges"}
      <div class="gauges">
        {#each metrics as m}
          <div class="gauge" title="{m.label}: {m.display}">
            <svg viewBox="0 0 100 100" aria-hidden="true">
              <circle class="track" cx="50" cy="50" r="42" />
              <circle
                class="arc"
                cx="50"
                cy="50"
                r="42"
                stroke={m.tone}
                stroke-dasharray="{(m.value / 100) * 264} 264"
              />
            </svg>
            <div class="gv">
              <strong style="color:{m.tone}">{m.display}</strong>
              <span>{$t(m.label)}</span>
            </div>
          </div>
        {/each}
      </div>
    {:else if meterStyle === "tiles"}
      {#each metrics as m}
        <div class="tile">
          <span class="tl">{$t(m.label)}</span>
          <strong class="tv" style="color:{m.tone}">{m.display}</strong>
          <div class="bar"><div class="fill" style="width:{m.value}%; background:{m.tone}"></div></div>
        </div>
      {/each}
    {:else}
      {#each metrics as m}
        <div class="meter">
          <span class="ml">{$t(m.label)}</span>
          <div class="bar">
            <div class="fill" style="width:{m.value}%; background:{m.tone}"></div>
          </div>
          <span class="mv">{m.display}</span>
        </div>
      {/each}
    {/if}
    <div class="sub">
      Disk: {s.disk_free ? fmt(s.disk_free) + " " + $t("boş") : "—"} · RAM: {s.memory_used
        ? fmt(s.memory_used)
        : "—"} / {s.memory_total ? fmt(s.memory_total) : "—"} · Uptime: {s.uptime_seconds
        ? Math.floor(s.uptime_seconds / 3600) + "s"
        : "—"}
      {#if s.battery_percent != null}· 🔋 {s.battery_percent}%{s.power_plugged ? " ⚡" : ""}{/if}
    </div>
    {#if s.cpu_per_core?.length}
      <div class="cores">
        <span class="ml">{$t("Çekirdek")}</span>
        {#each s.cpu_per_core as c}
          <div class="core" title="{c.toFixed(0)}%">
            <div class="corefill" style="height:{Math.max(4, c)}%; background:{color(c)}"></div>
          </div>
        {/each}
      </div>
    {/if}
    {#if s.temperature_sensors && Object.keys(s.temperature_sensors).length}
      <div class="sub">🌡 {Object.values(s.temperature_sensors).flat().slice(0, 4).map((x: any) => `${x.label || "sensor"}: ${x.current}°`).join(" · ")}</div>
    {/if}
  </div>

  <!-- Tarama sonucu: silmeden önce gözden geçir. Yalnız sonuç varken görünür;
       başlatma eylemi yukarıdaki kahraman alanında. -->
  {#if scanned && scanItems.length}
  <section class="card">
    <h3>{$t("Temizlik Analizi")}</h3>
    {#if scanned && scanItems.length}
      <p>
        {$t("Geri kazanılabilir:")} <strong class="green">{fmt(reclaimable)}</strong>
        <span class="muted">({chosen.length}/{scanItems.length} {$t("seçili")})</span>
      </p>
      <div class="row">
        <button onclick={() => setAll(true)}>{$t("Tümünü Seç")}</button>
        <button onclick={() => setAll(false)}>{$t("Hiçbiri")}</button>
        <button onclick={quickScan}>{$t("Yeniden Tara")}</button>
      </div>
      <div class="cleanlist">
        <VirtualList items={scanItems} rowHeight={24}>
          {#snippet row(item)}
            <label class="clitem">
              <input type="checkbox" checked={item.selected} onchange={() => toggle(item)} />
              <span class="csize">{fmt(item.size)}</span>
              <span class="ccat">{item.category ?? ""}</span>
              <span class="cpath">{item.path}</span>
            </label>
          {/snippet}
        </VirtualList>
      </div>
    {/if}
  </section>
  {/if}

  <!-- Temizlik Geçmişi -->
  <section class="card">
    <h3>{$t("Yapılan Temizlikler")}</h3>
    {#if hist.count > 0}
      <p>
        {$t("Toplam boşaltılan:")} <strong class="green">{fmt(hist.total_freed)}</strong>
        <span class="muted">({hist.count} işlem · son: {hist.last_ts})</span>
      </p>
      {#if (hist.recent ?? []).length}
        {@const maxSz = Math.max(...(hist.recent ?? []).map((e: any) => e.size), 1)}
        <div class="chart">
          {#each hist.recent ?? [] as e}
            <div class="cbar" title="{fmt(e.size)} · {e.path}">
              <div class="cbarfill" style="height:{Math.max(3, (e.size / maxSz) * 100)}%"></div>
            </div>
          {/each}
        </div>
      {/if}
      <ul class="histlist">
        {#each hist.recent ?? [] as e}
          <li>
            <span class="green">{fmt(e.size)}</span>
            <span class="muted">{e.path}</span>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="muted">{$t("Henüz temizlik kaydı yok.")}</p>
    {/if}
  </section>
</div>

<ConfirmModal
  open={confirmOpen}
  count={chosen.length}
  bytes={reclaimable}
  onConfirm={quickClean}
  onCancel={() => (confirmOpen = false)}
/>
<StatusBar label={progress.label} done={progress.done} total={progress.total} onCancel={null} />

<style>
  .dash { display: flex; flex-direction: column; gap: var(--gap); font-family: var(--font); font-size: var(--fs); }
  h2 { margin: 0; color: var(--fg); font-size: var(--fs-lg); }
  h3 { margin: 0 0 var(--gap); color: var(--accent); font-size: var(--fs); }
  /* Kahraman alanı: solda durum + birincil eylem, sağda özet karoları. */
  .hero {
    display: grid;
    grid-template-columns: minmax(220px, 1fr) 2fr;
    gap: var(--pad);
    padding: calc(var(--pad) * 1.4);
    align-items: center;
  }
  .hero-main { display: flex; flex-direction: column; gap: var(--gap); align-items: flex-start; }
  .verdict {
    font-size: calc(var(--fs-lg) * 1.35);
    font-weight: 700;
    line-height: 1.15;
    color: var(--fg);
    padding-left: 12px;
    border-left: 4px solid var(--tone);
  }
  .hero-sub { margin: 0; color: var(--muted); }
  .hero-sub strong { color: var(--ok); }
  button.cta {
    background: var(--accent);
    color: var(--accent-fg);
    font-weight: 700;
    font-size: var(--fs-lg);
    padding: 10px 26px;
    border-radius: 999px;
    transition: filter 0.15s, transform 0.15s;
  }
  button.cta:hover:not(:disabled) { filter: brightness(1.12); transform: translateY(-1px); }
  .hero-tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--gap); }
  button.stat {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
    padding: var(--pad);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    text-align: left;
    min-width: 0;
    transition: border-color 0.15s, transform 0.15s;
  }
  button.stat:hover:not(:disabled) { border-color: var(--accent); transform: translateY(-1px); }
  .stat span { color: var(--muted); font-size: var(--fs-sm); text-transform: uppercase; letter-spacing: 0.04em; }
  .stat strong {
    font-size: calc(var(--fs-lg) * 1.4);
    line-height: 1.1;
    font-family: var(--font-mono);
    color: var(--fg);
    white-space: nowrap;
  }
  .stat em { color: var(--faint); font-size: var(--fs-sm); font-style: normal; }
  @media (max-width: 1000px) {
    .hero { grid-template-columns: 1fr; }
    .hero-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  .meters {
    padding: var(--pad);
    display: flex; flex-direction: column; gap: calc(var(--gap) * 0.7);
  }
  /* Bento/Cards: metrics become a tile board rather than stacked bars. */
  .meters.tiles {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: var(--gap);
  }
  /* The summary line and the core strip are full-width captions, not tiles. */
  .meters.tiles .sub,
  .meters.tiles .cores { grid-column: 1 / -1; }
  .tile {
    display: flex; flex-direction: column; gap: 5px;
    padding: var(--pad);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  :global(html[data-theme="bento"]) .tile { border-color: transparent; box-shadow: var(--shadow); }
  .tl { color: var(--muted); font-size: var(--fs-sm); text-transform: uppercase; letter-spacing: 0.04em; }
  .tv { font-size: calc(var(--fs-lg) * 1.7); line-height: 1.1; font-weight: 800; }
  .meter { display: flex; align-items: center; gap: var(--gap); }
  .ml { color: var(--muted); min-width: 60px; }
  .bar { flex: 1; height: 10px; background: var(--border); border-radius: 6px; overflow: hidden; }
  .tile .bar { flex: none; height: 5px; }
  .fill { height: 100%; transition: width 0.3s; }
  .mv { color: var(--fg); min-width: 70px; text-align: right; font-family: var(--font-mono); }
  .sub { color: var(--faint); font-size: var(--fs-sm); margin-top: 4px; }

  /* HUD: radial instrument gauges. */
  .gauges { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: var(--gap); }
  .gauge { position: relative; display: flex; align-items: center; justify-content: center; }
  .gauge svg { width: 100%; max-width: 132px; transform: rotate(-90deg); }
  .gauge .track { fill: none; stroke: var(--border); stroke-width: 7; }
  .gauge .arc {
    fill: none; stroke-width: 7; stroke-linecap: round;
    transition: stroke-dasharray 0.4s;
  }
  .gv {
    position: absolute; inset: 0;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 2px; pointer-events: none;
  }
  .gv strong { font-size: var(--fs-lg); font-family: var(--font-mono); }
  .gv span { color: var(--muted); font-size: var(--fs-sm); text-transform: uppercase; }
  .cores { display: flex; align-items: flex-end; gap: 3px; margin-top: 6px; height: 36px; }
  .core { width: 10px; height: 100%; background: var(--border); border-radius: 2px; display: flex; align-items: flex-end; overflow: hidden; }
  .corefill { width: 100%; border-radius: 2px; }
  .chart { display: flex; align-items: flex-end; gap: 4px; height: 60px; margin: 8px 0; }
  .cbar { flex: 1; height: 100%; display: flex; align-items: flex-end; background: var(--bg); border-radius: 3px; overflow: hidden; }
  .cbarfill { width: 100%; background: #58d6a0; border-radius: 3px; }
  .card {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: var(--pad);
    box-shadow: var(--shadow); backdrop-filter: var(--panel-blur);
  }
  .muted { color: var(--faint); }
  .green { color: var(--ok); }
  .row { display: flex; gap: var(--gap); margin-top: var(--gap); flex-wrap: wrap; }
  button {
    background: var(--btn); color: var(--fg); border: none; padding: 6px 14px;
    border-radius: var(--radius); cursor: pointer; font-family: var(--font); font-size: var(--fs);
  }
  .histlist { list-style: none; padding: 0; margin: 8px 0 0; display: flex; flex-direction: column; gap: 3px; }
  .histlist li { display: flex; gap: 10px; font-size: 12px; }
  .histlist .green { min-width: 80px; text-align: right; }
  .histlist .muted { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cleanlist { height: 220px; margin-top: 10px; background: var(--bg); border: 1px solid var(--border); border-radius: 6px; }
  .clitem { display: flex; gap: 10px; align-items: center; padding: 0 10px; width: 100%; font-size: 12px; cursor: pointer; }
  .csize { color: #58d6a0; min-width: 70px; text-align: right; }
  .ccat { color: #d29922; min-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cpath { color: var(--muted); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
