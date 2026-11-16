<script lang="ts">
  import { t } from "$lib/i18n";
  let { active, onSelect }: { active: string; onSelect: (view: string) => void } =
    $props();

  // 24x24 stroke icons (inline, no icon dependency). Emoji rendered differently
  // per Windows build and ignored the theme colour.
  const ICONS: Record<string, string> = {
    Dashboard: "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z",
    Analyze: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-4.3-4.3",
    Categories: "M12 2 2 7l10 5 10-5zM2 12l10 5 10-5M2 17l10 5 10-5",
    Clean: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15v4M17 17h4",
    Purge: "M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6",
    Installers: "M21 8l-9-5-9 5v8l9 5 9-5zM3 8l9 5 9-5M12 13v8",
    Duplicates: "M9 9h11v11H9zM5 15H4V4h11v1",
    Uninstall: "M3 3h18v18H3zM8 12h8",
    Optimize: "M13 2 3 14h9l-1 8 10-12h-9z",
    Startup: "M12 2v10M18.4 6.6a9 9 0 1 1-12.8 0",
    Ports: "M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4",
    Processes: "M22 12h-4l-3 9L9 3l-3 9H2",
    Maintenance:
      "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94z",
    Security: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
    Settings: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6",
    Help: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01",
  };

  // [routeId, trLabel]; `tone` gives each module group its own colour so the
  // active item tells you which area you are in at a glance.
  const groups = [
    { label: "Genel", tone: "var(--accent)", items: [["Dashboard", "Gösterge Paneli"]] },
    {
      label: "Temizlik",
      tone: "var(--ok)",
      items: [
        ["Analyze", "Gezgin"],
        ["Categories", "Kategoriler"],
        ["Clean", "Temizle"],
        ["Purge", "Artıklar"],
        ["Installers", "Kurulumlar"],
        ["Duplicates", "Yinelenenler"],
      ],
    },
    {
      label: "Sistem",
      tone: "var(--warn)",
      items: [
        ["Uninstall", "Kaldır"],
        ["Optimize", "Optimize"],
        ["Startup", "Başlangıç"],
        ["Ports", "Portlar"],
        ["Processes", "İşlemler"],
        ["Maintenance", "Bakım"],
        ["Security", "Güvenlik Merkezi"],
      ],
    },
    { label: "Diğer", tone: "var(--muted)", items: [["Settings", "Ayarlar"], ["Help", "Yardım"]] },
  ];
</script>

<nav class="sidebar" aria-label={$t("Genel")}>
  {#each groups as g}
    <div class="group-label">{$t(g.label)}</div>
    {#each g.items as [id, label]}
      <button
        class:active={active === id}
        aria-current={active === id ? "page" : undefined}
        style="--tone:{g.tone}"
        onclick={() => onSelect(id)}
      >
        <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[id]} /></svg>
        {$t(label)}
      </button>
    {/each}
  {/each}
</nav>

<style>
  .sidebar {
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: calc(var(--pad) * 0.6);
    background: var(--panel);
    min-width: 168px;
    border-right: 1px solid var(--border);
    backdrop-filter: var(--panel-blur);
    overflow-y: auto;
  }
  .group-label {
    color: var(--faint);
    font-size: var(--fs-sm);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: calc(var(--gap) * 0.8) 12px 3px;
    font-family: var(--font);
  }
  button {
    position: relative;
    display: flex;
    align-items: center;
    gap: 9px;
    background: none;
    border: none;
    color: var(--muted);
    text-align: left;
    padding: calc(var(--row-h) * 0.16) 12px;
    font-family: var(--font);
    font-size: var(--fs);
    cursor: pointer;
    border-radius: var(--radius);
    transition: background 0.15s, color 0.15s;
  }
  .icon {
    width: 16px;
    height: 16px;
    flex: none;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.8;
    stroke-linecap: round;
    stroke-linejoin: round;
    opacity: 0.85;
  }
  button:hover { background: var(--border); color: var(--fg); }
  button.active { background: var(--btn); color: var(--fg); font-weight: 600; }
  button.active .icon { stroke: var(--tone); opacity: 1; }
  /* Module-coloured marker on the active item. */
  button.active::before {
    content: "";
    position: absolute;
    left: 0;
    top: 22%;
    bottom: 22%;
    width: 3px;
    border-radius: 2px;
    background: var(--tone);
  }
</style>
