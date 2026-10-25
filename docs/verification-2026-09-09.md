# wmole 10/10 planı doğrulama kaydı

Tarih: 9 Eylül 2026

## Başlangıç

- Dal: `feat/tauri-gui-core`
- Başlangıç commit'i: `f99364d8deeea9cae31b78dddbfe173582268cb7`
- Başlangıç çalışma ağacı: yalnız `WMOLE-10-10-PLAN.md` izlenmeyen dosyaydı.
- Python: 3.12.4
- Node.js: 24.18.0
- npm: 11.14.1
- Rust: 1.90.0
- Cargo: 1.90.0

## 1. doğrulama noktası

- `python -m unittest discover -s tests -q`: 83 test geçti, 31.939 saniye.
- `npm run check`: 0 hata, 0 uyarı.
- `npm run build`: başarılı; statik frontend çıktısı üretildi.
- `cargo check`: başarılı; Tauri/Rust katmanı 3 dakika 1 saniyede doğrulandı.
- `git diff --check`: whitespace hatası yok.

## Kapatılan riskler

- Karantina indeks yazımı hata verdiğinde taşınmış dosyanın silinmesi engellendi.
- Geri taşıma başarısızsa kasadaki tek kopya korunuyor ve konumu hata mesajında bildiriliyor.
- Karantina indeksi atomik dosya değişimiyle yazılıyor; thread ve Windows süreçleri arası kilit kullanılıyor.
- Kalıcı, karantina ve Geri Dönüşüm Kutusu silmeleri ortak yol/Git güvenlik kontrolünden geçiyor.
- Kalıcı silme onayı her işlemde sıfırlanıyor ve çift gönderim engelleniyor.
- Ana boyut, geliştirici klasörü ve büyük dosya taramalarına iptal sinyali ulaşıyor.
- Başarısız silme sonuçları Analyze, Dashboard, ScanView ve Duplicates listelerinde kalıyor.
- Duplicate grubu tam boyut ve tam içerik hash'iyle tanımlanıyor.
- Python dependency audit açıkça `requirements.txt` dosyasını hedefliyor.
- Güvenlik ekranı bulunmayan yol veya başarısız audit sonucunu temiz/başarılı göstermiyor.
- Varsayılan silme metinleri gerçek davranış olan geri alınabilir karantinayı söylüyor.
- Silme modalı dialog semantiği, odak yönetimi, Escape ve focus trap içeriyor.

## Açık doğrulamalar

- Paketlenmiş Tauri uygulamasının gerçek Windows kullanıcı akışları.
- Süreç kesintisinin her karantina aşamasında kurtarma testi.
- Yönetilen audit alt süreçlerinin iptali ve zaman aşımı.
- Performans bütçelerinin sabit fixture/donanım üzerinde ölçümü.
- İmzalı installer ve güvenilir yayın manifesti.

## 2. doğrulama noktası

- Uygulama sürümü yeni protokol ve kurtarma özellikleri nedeniyle `0.8.0` olarak tüm paket kaynaklarında eşitlendi.
- Son temiz turda `python -m unittest discover -s tests -q`: 93 test geçti, 36.012 saniye.
- `npm run check`: 0 hata, 0 uyarı.
- `npm run build`: başarılı; 213 istemci modülü işlendi.
- `cargo check --manifest-path gui/src-tauri/Cargo.toml`: başarılı; `gui v0.8.0` doğrulandı.
- Gerçek geçici Git deposu testi dirty ve untracked hedefleri güvenli, kalıcı ve dry-run silmede engelledi.
- Diskler arası karantina kopyası hash+boyut doğrulamasından önce kaynağı kaldırmıyor.
- Başarısız expiry silmesi indeks kaydını koruyor; eski indeks kaydı manifestli biçime tekrar çalıştırılabilir şekilde yükseltiliyor.
- Sidecar bağlantısı protokol sürümünü ve ping cevabını doğruluyor; tek terminal olay ve handler temizliği uygulanıyor.
- Güncelleme setup dosyası ayrı geçici adda tutuluyor, checksum içindeki varlık adı eşleşiyor ve kurulumdan önce yeniden hash'leniyor.

## Paketlenmiş uygulama kanıtı

- PyInstaller 6.19.0 ile `dist/wmole.exe` üretildi; SHA-256: `73636e754b4fc7130f91f59b1ae299114d04c0c694f7aeb85a9cec37465a985d`.
- Paketlenmiş EXE `wmole 0.8.0` döndürdü; gerçek stdin/stdout sürecinde protokol 1 `ready` ve başarılı `packaged-ping` terminal olayı üretti.
- Tauri release derlemesi `wmole_0.8.0_x64_en-US.msi` ve `wmole_0.8.0_x64-setup.exe` oluşturdu.
- `release/wmole-0.8.0-setup.exe` boyutu 20.828.019 bayt; SHA-256: `b309c9cc031c238efd78eb3da98518bdbadc90de3f1ee1cae6c168109584ac49`.
- NSIS sessiz kurulum çıkış kodu 0; Windows uninstall kaydı `wmole 0.8.0` ve `%LOCALAPPDATA%\\wmole` konumunu gösterdi.
- Kurulu `gui.exe` sekiz saniye sonra çalışır durumdaydı; WebView2 `--webview-exe-version=0.8.0` ile açıldı ve kurulu `wmole.exe serve` alt süreci başlatıldı.
- Bu tek makine kanıtı temiz VM, yükseltme geri alma, ölçek matrisi, imzalı installer veya pilot yerine sayılmadı.

## Bağımlılık taraması

- `python -m pip_audit -r requirements.txt`: bilinen açık bulunmadı.
- `npm audit --omit=dev`: 0 açık.
- `cargo-audit 0.21.2` kuruldu ancak güncel RustSec veritabanındaki CVSS 4.0 kaydını ayrıştıramadı. `0.22.2` bu Windows/Rust ortamında derlenemedi. CI taraması `0.22.2` ile Ubuntu işine ayrıldı; CI sonucu alınmadan Rust bağımlılık kriteri kapatılmayacak.
