<script lang="ts">
  import { lang } from "$lib/i18n";
  import { openUrl } from "@tauri-apps/plugin-opener";

  const content = {
    tr: {
      title: "Yardım & Özellikler",
      intro:
        "wmole, Windows için bakım araç setidir. Sol menüden bir bölüm seç. Tüm yıkıcı işlemler uygulama-içi onay penceresiyle korunur.",
      sections: [
        {
          title: "Temizlik",
          items: [
            ["Gösterge Paneli", "Sistem özeti, temizlik analizi ve geçmiş. Tek tıkla 'Hızlı Temizle'."],
            ["Gezgin", "Dosya sistemini canlı boyutlarla gez; klasöre gir, yukarı çık, büyük dosyaları, sürücüleri ve treemap'i gör."],
            ["Kategoriler", "Disk kullanımını kategoriye göre (cache, tarayıcı, sistem) listele."],
            ["Temizle", "Güvenli temizlik kategorilerini tara ve Geri Dönüşüm Kutusu'na taşı."],
            ["Artıklar", "node_modules / build / dist gibi geliştirici artıklarını toplu sil."],
            ["Kurulumlar", "İndirilenler ve Masaüstü'ndeki eski kurulum dosyalarını bul."],
            ["Yinelenenler", "Boyut + MD5 ile yinelenen dosyaları bul."],
          ],
        },
        {
          title: "Sistem",
          items: [
            ["Kaldır", "Kurulu programları listele, kaldır, kalıntı dosya/registry'yi temizle."],
            ["Optimize", "DNS flush, Winsock/IP reset, Prefetch, Windows Update reset vb. (Dry-run destekli)."],
            ["Başlangıç", "Sistem açılışında çalışan programları yönet."],
            ["Portlar", "Dinleyen geliştirici portlarını listele ve süreçleri kapat."],
            ["İşlemler", "RAM kullanımına göre süreçleri listele ve kapat."],
            ["Bakım", "Güncelleme kontrolü/uygulama ve ~/.wmole durumunu kaldırma."],
          ],
        },
        {
          title: "Güvenlik",
          items: [
            ["Varsayılan: karantina", "Silmeler varsayılan olarak ~/.wmole/quarantine altına taşınır ve 30 gün boyunca Güvenlik Merkezi'nden geri alınabilir; disk alanı karantina süresi dolunca boşalır. Kalıcı silme ek onay gerektirir."],
            ["Korumalı yollar", "Sürücü kökleri, C:\\Windows, Program Files, kullanıcı profili ve .git içeren yollar engellenir."],
            ["İptal edilebilir", "Uzun işlemler alt şeritteki 'İptal' ile durdurulabilir; arayüz hiç donmaz."],
            ["İşlem günlüğü", "Tüm silmeler ~/.wmole/logs/operations.log dosyasına yazılır."],
          ],
        },
      ],
    },
    en: {
      title: "Help & Features",
      intro:
        "wmole is a maintenance toolkit for Windows. Pick a section from the left menu. All destructive actions are guarded by an in-app confirmation dialog.",
      sections: [
        {
          title: "Cleaning",
          items: [
            ["Dashboard", "System overview, cleanup analysis & history. One-click 'Quick Clean'."],
            ["Analyze", "Browse the filesystem with live sizes; enter folders, go up, view large files, drives and treemap."],
            ["Categories", "List disk usage by category (cache, browser, system)."],
            ["Clean", "Scan safe cleanup categories and move to Recycle Bin."],
            ["Purge", "Bulk-delete developer artifacts like node_modules / build / dist."],
            ["Installers", "Find old setup files in Downloads and Desktop."],
            ["Duplicates", "Find duplicate files by size + MD5."],
          ],
        },
        {
          title: "System",
          items: [
            ["Uninstall", "List installed programs, uninstall, and sweep leftover files/registry."],
            ["Optimize", "DNS flush, Winsock/IP reset, Prefetch, Windows Update reset, etc. (Dry-run supported)."],
            ["Startup", "Manage programs that run at system startup."],
            ["Ports", "List listening dev ports and kill processes."],
            ["Processes", "List processes by RAM usage and kill them."],
            ["Maintenance", "Check/apply updates and remove ~/.wmole state."],
          ],
        },
        {
          title: "Safety",
          items: [
            ["Default: quarantine", "Deletes are moved to ~/.wmole/quarantine by default and can be restored from the Security Center for 30 days; disk space is freed once the retention expires. Permanent delete needs extra confirmation."],
            ["Protected paths", "Drive roots, C:\\Windows, Program Files, user profile and paths containing .git are blocked."],
            ["Cancellable", "Long operations can be stopped via 'Cancel' in the status bar; the UI never freezes."],
            ["Operation log", "All deletions are written to ~/.wmole/logs/operations.log."],
          ],
        },
      ],
    },
  };
  let c = $derived(content[$lang]);
</script>

<div class="help">
  <h2>{c.title}</h2>
  <p class="intro">{c.intro}</p>
  {#each c.sections as sec}
    <section class="card">
      <h3>{sec.title}</h3>
      <dl>
        {#each sec.items as [name, desc]}
          <div class="item">
            <dt>{name}</dt>
            <dd>{desc}</dd>
          </div>
        {/each}
      </dl>
    </section>
  {/each}
  <p class="owner">
    {$lang === "tr" ? "Ürün sahibi" : "Product Owner"}: Umut Çelik ·
    <button onclick={() => openUrl("https://x.com/umutc6230")}>X</button> ·
    <button onclick={() => openUrl("https://github.com/umutc6230")}>GitHub</button>
  </p>
</div>

<style>
  .help { display: flex; flex-direction: column; gap: 14px; font-family: monospace; overflow: auto; }
  h2 { margin: 0; color: var(--fg); }
  .intro { color: var(--muted); margin: 0; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
  h3 { margin: 0 0 10px; color: #58d6a0; }
  dl { margin: 0; display: flex; flex-direction: column; gap: 8px; }
  .item { display: grid; grid-template-columns: 200px 1fr; gap: 12px; }
  dt { color: #d29922; }
  dd { margin: 0; color: var(--muted); }
  .owner { color: var(--faint); font-size: 12px; margin: 0; }
  .owner button { background: none; border: none; padding: 0; color: #58a6ff; cursor: pointer; font: inherit; text-decoration: underline; }
</style>
