<script lang="ts">
  import { checkForUpdate } from "$lib/updater";
  import { request } from "$lib/sidecar";
  import GenericConfirm from "./GenericConfirm.svelte";
  import { toast } from "$lib/toast";
  import { tr } from "$lib/i18n";
  import { t } from "$lib/i18n";

  let busy = $state(false);
  let updateOut = $state("");
  let removeConfirm = $state(false);

  async function checkUpdate() {
    busy = true;
    try { await checkForUpdate(false); } finally { busy = false; }
  }

  async function doRemove() {
    removeConfirm = false;
    busy = true;
    const done = await request({ op: "remove", dry_run: false });
    busy = false;
    const payload: any = done.payload ?? {};
    updateOut = JSON.stringify(payload, null, 2);
    if (done.ok) toast(tr("Ayarlar sıfırlandı; karantina ve kurtarma kayıtları korundu"), "ok");
  }
</script>

<div class="wrap">
  <section class="card">
    <h3>{$t("Güncelleme")}</h3>
    <p>{$t("GitHub'daki son sürümü kontrol et veya güncellemeyi uygula.")}</p>
    <div class="row">
      <button onclick={checkUpdate} disabled={busy}>{$t("Kontrol Et (dry-run)")}</button>

    </div>
  </section>

  <section class="card">
    <h3>{$t("Ayarları Sıfırla")}</h3>
    <p>
      <code>~/.wmole</code> — {$t("Ayarları ve önbelleği sıfırlar. Karantina, işlem günlüğü ve güvenlik kayıtları korunur.")}
    </p>
    <button class="danger" onclick={() => (removeConfirm = true)} disabled={busy}>
      {$t("Ayarları Sıfırla")}
    </button>
  </section>

  {#if updateOut}
    <pre class="out">{updateOut}</pre>
  {/if}
</div>

<GenericConfirm
  open={removeConfirm}
  danger
  title="Ayarları Sıfırla"
  message={tr("Ayarlar ve önbellek silinecek. Karantina ve kurtarma kayıtları korunacak. Devam?")}
  confirmLabel="Kalıcı Sil"
  onConfirm={doRemove}
  onCancel={() => (removeConfirm = false)}
/>

<style>
  .wrap { display: flex; flex-direction: column; gap: 16px; font-family: monospace; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  h3 { margin: 0 0 8px; color: #58d6a0; }
  p { color: var(--muted); }
  code { color: #d29922; }
  .row { display: flex; gap: 10px; }
  button {
    background: var(--btn); color: var(--fg); border: none; padding: 8px 16px;
    border-radius: 4px; cursor: pointer; font-family: monospace;
  }
  button:disabled { opacity: 0.5; cursor: default; }
  button.danger { background: #e5534b; color: white; }
  .out {
    background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
    padding: 12px; color: var(--muted); font-size: 12px; max-height: 280px; overflow: auto;
  }
</style>
