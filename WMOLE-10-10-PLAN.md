# wmole: Tüm değerlendirme alanlarını 10/10'a taşıma planı

Tarih: 8 Eylül 2026  
Başlangıç sürümü: 0.7.0  
Durum: Uygulama devam ediyor; tamamlanan maddeler test kanıtıyla işaretleniyor  
Ürün sahibi: Umut Çelik | [X](https://x.com/palamut62) | [GitHub](https://github.com/palamut62)

## 1. Hedef ve değerlendirme yaklaşımı

Hedef, wmole'u Windows üzerinde dosya kaybettirmeyen, işlemlerini doğru açıklayan, hızlı ve testlerle doğrulanmış bir bakım uygulamasına dönüştürmek.

10/10 mutlak kusursuzluk garantisi değildir. Bu belgede tanımlanan ürün kapsamı, desteklenen ortamlar ve kabul kriterleri içinde tüm kanıtların tamamlanması anlamına gelir. Bir işin kodunun yazılması puanı otomatik yükseltmez; test, ölçüm ve gerektiğinde gerçek kullanıcı doğrulaması gerekir.

Başlangıç puanları 8 Eylül incelemesinden alınmıştır. O incelemede 72 Python testi, Svelte kontrolü ve frontend üretim derlemesi başarılıydı; kurulu Tauri uygulaması, büyük disk performansı ve kapsamlı bağımlılık güvenliği doğrulanmamıştı.

| Alan | Başlangıç | Hedef | Hedef için temel kanıt |
|---|---:|---:|---|
| Kod kalitesi | 6 | 10 | Açık sorumluluklar, tipli sözleşmeler, temiz statik kontroller ve davranış testleri |
| Mimari | 6 | 10 | Kurtarılabilir dosya işlemleri, tek güvenlik katmanı, sınırları belirli servisler |
| UI/UX | 6 | 10 | Doğru durumlar, klavye erişimi, anlaşılır onay ve başarılı kullanıcı görevleri |
| Performans | 5 | 10 | Sabit test ortamında karşılanan gecikme, kaynak ve tarama bütçeleri |
| Güvenlik | 4 | 10 | Silme sınırları, hedef doğrulama, güvenli güncelleme ve açık tehdit modeli |
| Testler | 5 | 10 | Kritik hata, eşzamanlılık, kesinti, masaüstü ve kurulum senaryolarının kanıtı |
| Bakım kolaylığı | 5 | 10 | Tekrarlanabilir geliştirme, anlaşılır modüller, tanılama ve release akışı |
| Ürün değeri | 8 | 10 | Hedef kullanıcıların temel görevleri yardımsız ve güvenle tamamlaması |
| Özellik bütünlüğü | 7 | 10 | Mevcut her ekranın başarı, hata, iptal ve kurtarma akışlarının tamamlanması |
| Üretime hazırlık | 3 | 10 | Temiz kurulum/yükseltme, doğrulanmış artefakt ve geçen release kapıları |

## 2. Kapsam ve çalışma kuralları

- Önce veri kaybı ve güvenlik tutarsızlıkları, ardından kullanım ve performans, son olarak yapısal iyileştirmeler ele alınacak.
- Mevcut tasarım dili ve temel özellikler korunacak. Genel bir yeniden yazım yapılmayacak.
- Kod düzeltmeleriyle yeni özellikler ayrı iş paketlerinde tutulacak.
- Bug-fix ve küçük UI düzeltmelerinde sürüm aynı kalacak. Yeni özellik veya büyük değişiklikte uygun minor/major artışı yapılacak.
- Sürüm `gui/package.json`, `gui/src-tauri/tauri.conf.json`, `gui/src-tauri/Cargo.toml` ile sidecar ve installer metadata'sında eşleşecek.
- Native alert/confirm/prompt kullanılmayacak. Ürün sahibi atfı ve profil bağlantıları korunacak.
- Gerçek kullanıcı dosyalarında yıkıcı test yapılmayacak. Silme, disk doluluğu, süreç öldürme ve kurulum testleri ayrılmış fixture/VM üzerinde yürütülecek.
- İncelemedeki LIKELY bulgular önce tekrarlanacak; yanlış çıkan hipotez kapatılacak, varsayıma göre düzeltme yapılmayacak.
- Bu belge geliştirme, push, release veya kurulum başlatmaz. Yayın aşamasına gelindiğinde mevcut kullanıcı yetkilendirmesi esas alınacak.

## 3. İş paketleri ve bağımlılık sırası

Eforlar göreli büyüklüktür: küçük = sınırlı değişiklik, orta = birden fazla katman, büyük = kalıcılık/yaşam döngüsü veya ortam matrisi. Takvim taahhüdü değildir.

| Paket | Öncelik | İçerik | Efor | Bağımlılık |
|---|---|---|---|---|
| A | P0 | Başlangıç kanıtı ve hata senaryoları | Küçük | Yok |
| B | P0 | Karantinada veri kaybını durdurma | Orta | A |
| C | P1 | Ortak silme koruması ve yeni işlem onayı | Orta | A |
| D | P1 | Atomik karantina ve kesintiden kurtarma | Büyük | B |
| E | P1 | İstek yaşam döngüsü, iptal ve canlı tarama | Büyük | A; D ile sözleşme uyumu |
| F | P1 | Doğru sonuçlar ve güvenlik denetimi | Orta | C, E |
| G | P1/P2 | Erişilebilirlik ve özellik akışlarının tamamlanması | Orta | C, E, F |
| H | P2 | Ölçümlü performans | Orta | D, E |
| I | P2 | Modülerleştirme ve bakım kolaylığı | Büyük | B-F davranış testleri |
| J | P1 | Güvenli güncelleme ve dağıtım | Büyük | D, E |
| K | P1 | Son test matrisi ve yeniden puanlama | Büyük | B-J |

**İlk teslim:** B ve C. Büyük refaktör veya yeni özellik beklenmeden veri kaybı ve onay kusurları kapatılacak. Test altyapısı her paketin içinde gelişecek; bütün testler son aşamaya bırakılmayacak.

## 4. A: Başlangıç kanıtı ve hata senaryoları

- [x] İncelenen commit, çalışma ağacı, araç sürümleri ve mevcut test sonuçlarını `docs/verification-2026-09-09.md` dosyasına kaydet.
- [x] Karantina indeks yazma hatasını kalıcı regresyon testine dönüştür.
- [x] Geçici gerçek Git deposuyla dirty/untracked dosyayı tüm silme modlarında dene.
- [ ] Modalı iki farklı silme işlemi için arka arkaya açan bileşen testi ekle.
- [x] Eşzamanlı karantina kaydını kontrollü thread ve Windows süreç senaryolarıyla tekrarla.
- [ ] Sidecar cevap vermeme, tarama iptali ve sayfa değişimi senaryolarını kaydet.
- [x] Kısaltılmış duplicate grup kimliği riskini kaldıran tam hash+boyut fixture testini ekle.
- [x] Desteklenen Windows sürümleri, mimari, dosya sistemleri ve standart/yönetici oturum kapsamını açıkça belirle.

**Kabul:** Her bulgunun yeniden üretimi, beklenen davranışı, önceliği ve kapanış testi var. Yeni testler ilgili mevcut hatayı yakalıyor; yalnızca uygulamanın mevcut çıktısını tekrar etmiyor.

## 5. B: Karantinada veri kaybını durdurma

Başlıca alan: `mole.py` içindeki quarantine_path ve kayıt yazımı.

- [x] Başarılı taşıma sonrası hata temizliğinin taşınmış veriyi silmesini kaldır.
- [x] İndeks hatasında dosyanın mevcut konumunu koru ve kurtarılabilir hata döndür.
- [x] Kaynağa geri taşıma başarısızsa kasadaki tek kopyayı koru; başarı mesajı üretme.
- [x] Bozuk/okunamayan indeks ile gerçekten boş indeks durumunu ayır.
- [x] Hata mesajında kullanıcıya dosyanın korunduğunu ve kurtarma yolunu göster.

**Kabul:** İndeks yazma, izin ve disk dolu hatalarının her birinde dosyanın en az bir eksiksiz kopyası bulunuyor. Sonuç yeniden başlatma sonrasında da geçerli. Kaynak ve korunan kopya hash'leri eşleşiyor.

## 6. C: Ortak silme koruması ve işlem başına onay

Başlıca alanlar: delete_path, trash_paths_batch, Git/path kontrolleri, ConfirmModal.svelte ve silme çağıran ekranlar.

- [x] GUI, TUI, CLI, zamanlanmış iş ve toplu silmeyi ortak `delete_path`/`deletion_block_reason` politikası üzerinden geçir.
- [x] Git değişiklik kontrolünü karantina, Geri Dönüşüm Kutusu ve kalıcı silmeye uygula.
- [ ] Korunan kök, denylist, junction/symlink ve çözülmüş hedef sınırlarını işlem öncesinde doğrula.
- [x] Git durumu belirlenemediğinde korumayı sessizce atlama; açık bloklama nedeni göster.
- [x] Her modal açılışında kalıcı silme tercihini ve ikinci onayı sıfırla.
- [ ] Onayı görüntülenen hedef listesi ve silme moduna bağla; seçim değişirse yeniden onay iste.
- [x] Devam eden silme için çift tıklamanın ikinci yıkıcı işlem başlatmasını engelle.
- [x] Dry-run'ın içerik taşımadığını/silmediğini ve gerçek işlemle aynı koruma kararlarını verdiğini doğrula.

**Kabul:** Test matrisindeki korunan hedefler hiçbir giriş yolunda silinmiyor. İki ardışık kalıcı silme birbirinden bağımsız onay gerektiriyor. Engellenen işlemin nedeni öğe bazında görülebiliyor.

## 7. D: Atomik karantina ve kesintiden kurtarma

- [x] Dosya hareketleri için prepared, moving, committed, restoring ve recoverable durumlarını tanımla.
- [x] Aynı süreç ve birden fazla Windows uygulama örneği için karantina yazma koordinasyonu oluştur.
- [x] Kilitli atomik JSON indeks ve öğe manifesti kararını `docs/quarantine-architecture.md` içinde gerekçelendir.
- [x] Metadata transaction'ının dosya sistemi taşımasını tek başına atomik yapmadığını tasarımda ele al.
- [x] Aynı disk taşıması ile diskler arası kopyala/doğrula/kaynağı kaldır adımlarını ayrı yönet.
- [x] Kesinti sonrasında kasa ile indeks arasında uzlaştırma yap; sahipsiz geçerli kaydı recoverable olarak koru.
- [x] Uzlaştırmayı aynı işlem kimliği ikinci kayıt veya dosya hareketi yaratmayacak şekilde tekrar çalıştırılabilir yap.
- [ ] Geri yüklemede mevcut hedefi ezme; çakışma çözümünü kullanıcıya sun.
- [x] Süresi dolan öğeyi ancak silme başarıyla tamamlandıktan sonra kayıttan düşür.
- [x] Bozuk indeks alanlarını, kasa dışındaki stored yolunu ve geçersiz entry_id değerlerini reddet.
- [x] Eski karantina kayıtlarını ilk değişiklikte yedekleyen, yeniden çalıştırılabilir uzlaştırma oluştur.

**Kabul:** Taşımanın her aşamasında süreç durdurularak yeniden başlatma testi geçiyor. Paralel silme/restore/expiry çalışmasında eksik kayıt, üzerine yazma veya kayıp kopya oluşmuyor. Tek süreç kilidiyle yetinilmiyor; iki süreç senaryosu da geçiyor.

## 8. E: İstek yaşam döngüsü ve canlı tarama

Başlıca alanlar: sidecar.ts, Rust sidecar yönetimi, Python serve/Scanner ve tarama ekranları.

- [x] Sürümlenmiş istek/olay sözleşmesi tanımla: id, op, durum, ilerleme, öğe sonucu ve terminal sonuç.
- [x] Gelen JSON'u çalışma zamanında doğrula; yanlış tip, bilinmeyen işlem ve aşırı büyük isteği sınırlı hatayla reddet.
- [x] Her istek için tek terminal sonuç ve her terminal durumda handler temizliği sağla.
- [x] İlk bağlantı için ready/ping el sıkışması; kopma için görünür bağlantı durumu ekle.
- [ ] İş türüne uygun zaman aşımı ve ilerlemesiz kalma takibi ekle.
- [x] Timeout'u işlem başarısızlığıyla eşitleme. Yıkıcı işlem sonucu belirsizse durum sorgulaması/kurtarma kullan; otomatik tekrar gönderme.
- [x] İptali ana dizin yürüyüşüne, boyut işçilerine, geliştirici klasörü ve büyük dosya taramasına aktar. Yönetilen audit alt süreçleri açık.
- [x] İptalde yeni tarama görevlerinin dosya yürüyüşüne devam etmesini durdur; başlamış silmeler öğe sonucunu yayınlıyor.
- [ ] Sonuçları bounded buffer ile küçük gruplar halinde arayüze aktar.
- [ ] Sayaçlar için toplam bilinmiyorsa sahte yüzde yerine taranan öğe/boyut ve geçen süre göster.
- [ ] Ekran değişince işin devam mı iptal mi edeceğini açıklaştır; devam eden işi merkezi iş durumunda tut.
- [x] ScanView ve Güvenlik Merkezi isteklerinde try/catch/finally ile busy/loading durumlarını kapat. Diğer ekranların denetimi açık.
- [x] Sidecar işçi sayısını CPU'ya göre en fazla 8 ile sınırla; Rust yeniden başlatma denemesi zaten 3 başarısız spawn ile sınırlı.

**Kabul:** Cevap vermeyen/kapanan sidecar sonsuz spinner bırakmıyor. İptalden sonra yeni dosya işi başlamıyor. Sonucu belirsiz yıkıcı işlem yeniden yürütülmüyor. UTF-8 ve büyük olaylar protokol bütünlüğünü bozmuyor.

## 9. F: Sonuç doğruluğu ve güvenlik denetimi

- [x] Analyze, Dashboard, ScanView ve Duplicates listelerinden yalnızca başarılı item_result öğelerini kaldır.
- [x] Başarısız ve işlenmeyen öğeleri listede koru. Öğe üzerinde hata nedeni ve tekrar deneme sunumu açık.
- [ ] Karantinaya taşınan, kalıcı silinen, geri yüklenen ve ölçülen boş alan miktarını ayır.
- [ ] Karantina hareketlerini geçmişe ekle; aynı diskte taşınan baytı boşalan alan olarak sayma.
- [x] Duplicate gruplarında tam içerik kimliği ve boyut kullan; kısa görsel etiket için ayrıca önek üret.
- [x] Otomatik fazlalık seçiminde tam grup kimliğiyle her gerçek grupta en az bir kopya koru.
- [ ] Silme öncesi dosyanın taramadan sonra değişip değişmediğini doğrula; değişeni yeniden taramaya yönlendir.
- [x] Python audit komutuna seçilen requirements.txt manifestini açıkça ver. Yalnız pyproject.toml varsa yanlış ortam yerine unsupported göster.
- [ ] Windows üzerinde npm/cargo/pip-audit araç bulma ve çağırma davranışını gerçek araçlarla doğrula.
- [ ] Audit sonuçlarını clean, findings, partial, cancelled, unavailable ve error olarak ayır.
- [ ] Manifest listesi/hash çıktısını gerçek SBOM olarak adlandırma; kapsamı yeniden adlandır veya standart bileşen/sürüm/bağımlılık içeren SBOM üret.
- [ ] Secret taramasında dosya sınırı, atlanan dosyalar, erişim hataları ve iptal bilgisini göster.
- [ ] Denetimin ağ kullanımı ve manifest çözümleme davranışını anlaşılır şekilde belirt; inceleme işlemi kullanıcı projesini değiştirmesin.

**Kabul:** Var olmayan yol temiz sonuç üretmiyor. İki farklı gereksinim fixture'ı doğru proje girdileriyle denetleniyor. Kısmi silmede başarısız dosya ekranda kalıyor. Her duplicate grubunda korunan kopya testi geçiyor.

## 10. G: UI/UX ve özellik bütünlüğü

- [x] Onboarding, silme modalı ve yardım ekranında varsayılan hedefi geri alınabilir karantina olarak düzelt.
- [x] Silme modalına dialog semantiği, başlık ilişkisi, başlangıç odağı, focus trap, Escape ve odağı geri verme ekle.
- [ ] Klavyeyle menü, seçim, tarama, iptal ve geri yükleme akışını tamamla.
- [ ] Ekran okuyucuya işlem durumunu ölçülü canlı bildirimle duyur.
- [ ] Hata mesajlarını Türkçe/İngilizce tutarlı hale getir; ham stack trace yerine eyleme dönük açıklama sun.
- [ ] 1100x720 başlangıç boyutu, daraltılmış pencere ve %100/%150/%200 ölçeklerde kırpılma testi yap.
- [ ] Açık/koyu temada kontrast, odak ve seçili durumları doğrula; anlamı yalnızca renkle anlatma.
- [ ] Kaydırılabilir alanları anlaşılır kıl; uzun dosya yoluna klavyeyle erişim/kopyalama sağla.
- [ ] UAC iptalinde mevcut örneği açık tut; yeni örneğin başladığı doğrulanmadan eski örnekten çıkma.
- [ ] Başlangıç girdisi yönetimi için geri alma; optimizasyon için risk/izin/sonuç açıklaması; bakım için son çalışma ve hata bilgisi sağla.
- [ ] Port/süreç sonlandırmada PID yeniden kullanımı ve korunan süreç denetimini işlem anında yap.

**Kabul:** Her ekran için boş, yükleniyor, başarı, kısmi başarı, hata ve uygulanabildiği yerde iptal/yeniden deneme akışları doğrulanıyor. Fare olmadan temel görevler tamamlanıyor. Native dialog kullanılmıyor.

## 11. H: Performans bütçeleri ve ölçüm

Önce aynı makinede başlangıç ölçümü alınacak. Aşağıdaki değerler önerilen kabul hedefleridir; gerçekleşmiş ölçüm değildir. Referans makine, Windows/WebView2 sürümü, SSD/HDD türü ve fixture içeriği kayıt altına alınacak. Desteklenen en düşük donanımda ayrıca ölçülecek; hedef değişirse gerekçesi kaydedilecek.

| Ölçüm | Hedef | Doğrulama |
|---|---|---|
| Yerel SSD'de soğuk açılış | p95 <= 3 saniye | 20 bağımsız açılış; kullanılabilir ekran + sidecar hazır |
| UI tıklama/klavye yanıtı | p95 <= 100 ms | Tarama sürerken etkileşim ölçümü |
| İlk ilerleme/öğe | <= 1 saniye | Yerel, erişilebilir test dizini |
| İptalin UI'da görünmesi | <= 200 ms | Büyük tarama ve hash işi |
| Yerel tarama işçisinin iptal sınırına ulaşması | p95 <= 2 saniye | Yeni iş yok; açık kaynaklar serbest |
| 100 bin dosya taramasında ek toplam süreç belleği | <= 250 MiB | GUI + sidecar, boşta duruma göre fark |
| 10 bin sonuçta liste kaydırma | p95 frame <= 32 ms | Sonuç akışı sürerken |
| Sabit fixture'da tarama regresyonu | Başlangıca göre <= %10 | Aynı donanım, sıcak/soğuk cache ayrı |
| 100 görev sonrası kaynak birikimi | Monoton büyüme yok | Handler/thread/handle başlangıca döner; bellek eğrisi incelenir |

- [ ] İlerleme olaylarını makul sıklıkta birleştir; frontend her dosyada tüm listeyi kopyalamasın.
- [ ] İşçi sayısı ve kuyruk boyutunu sınırla; HDD/SSD üzerinde ölçerek ayarla.
- [ ] Önbellek doğruluk politikasını açıklaştır; bayat/tahmini boyutu işaretle, kullanıcıya yeniden ölçüm sun.
- [ ] Günlük rotasyonu ve sayfalı okuma ekle; bütün geçmişi belleğe yükleme.
- [ ] Ağ sürücüsü/çıkarılabilir disk ve bloke OS çağrılarında UI'yı açık tut; gerçek sonlanma bekleniyorsa bunu doğru göster.

**Kabul:** Ölçüm raporunda başlangıç, son durum, donanım ve ham sonuçlar bulunuyor. Bir defalık hızlı koşu yerine tekrarlı dağılım raporlanıyor. Güvenlik kontrollerini kapatarak hız kazanılmıyor.

## 12. I: Kod kalitesi, mimari ve bakım kolaylığı

Önerilen sorumluluk ayrımı; kesin klasör adları uygulama sırasında mevcut yapıya göre seçilebilir:

| Sorumluluk | Kapsam |
|---|---|
| Dosya güvenliği | Yol/Git korumaları ve silme kararı |
| Karantina deposu | İşlem durumu, indeks, kurtarma, restore/expiry |
| Tarama motoru | İptal, ilerleme, cache, duplicate ve dosya keşfi |
| Windows adaptörleri | Süreç, registry, başlangıç, görev zamanlayıcı |
| Güvenlik denetimleri | Secret ve manifest denetimleri |
| Servis protokolü | Doğrulama, dispatch, olaylar ve istek yaşam döngüsü |
| CLI/TUI | Kullanıcı etkileşimi; çekirdek güvenlik mantığı içermez |

- [ ] Bu ayrımı küçük, davranışı koruyan değişikliklerle yap; mole.py uyumlu giriş noktası olarak kalabilsin.
- [ ] Dosya kalıcılığı ve Windows çağrılarını test edilebilir açık sınırlara taşı.
- [ ] Request/SidecarEvent için ayrıştırılabilir tipler kullan; kritik akışlardaki any ve kör cast'leri kaldır.
- [ ] Python public sınırlarını tiple, beklenen hata türlerini tanımla; yutulan hataları görünür sonuçlara dönüştür.
- [ ] Yalnızca kanıtlanmış tekrarları ortaklaştır; genel plugin/framework katmanı kurma.
- [x] Python test, Svelte check/build ve Rust check kontrollerini Windows CI'a ekle.
- [x] Geliştirme ve paketleme bağımlılıklarını sürümlü/tekrarlanabilir tanımla.
- [x] README'yi masaüstü akışı, Python destek sürümü, karantina davranışı ve gerçek komutlarla güncelle.
- [ ] Hassas veri içermeyen tanılama çıktısı oluştur; kullanıcı paylaşmadan önce içeriği görebilsin.
- [x] Bozuk durum dosyası, eksik sidecar ve başarısız güncelleme için kısa destek rehberi yaz.

**Kabul:** Çekirdek işlevler TUI açmadan test ediliyor. Arayüzler aynı güvenlik kararını kullanıyor. Temiz checkout'tan belgelenmiş komutlarla check/test/build tamamlanıyor. Modül sınırları ve kalıcı durum geçişi belgeli.

## 13. J: Güvenli güncelleme ve release

- [ ] Yayın manifestini uygulamada güvenilen anahtarla doğrulanabilir hale getir; hash'i yalnızca aynı indirme konumundan almakla yetinme.
- [ ] Windows installer imzası ve imzalama anahtarının dağıtım sürecini tanımla. Sertifika/anahtar yoksa bu kriteri tamamlandı sayma.
- [x] Her indirme için ayrı geçici yol kullan; paralel indirmeyi seri hale getir veya ayrı kimlikle yönet.
- [x] Kurulum öncesi dosyayı yeniden doğrula; doğrulama ile çalıştırma arasındaki dosya değiştirme riskini sınırla.
- [x] Setup ve ona ait checksum/manifesti dosya adına göre eşleştir.
- [ ] Ağ zaman aşımı, HTTP hatası, eksik indirme, bozuk imza ve disk doluluğu durumlarını test et.
- [x] Güncelleme kontrolünün devam eden indirme/kurulum durumunu ezmesini engelle.
- [ ] CLI ve GUI güncelleme yollarını aynı artefakt güvenlik politikasına bağla.
- [x] Release script'inde sıralamayı kontrol -> test -> build -> artefakt doğrulama -> push/yayın olarak düzenle.
- [x] Kritik git/gh/npm/Rust/build komutlarının çıkış kodunu kontrol et; hata sonrası sonraki aşamaya geçme.
- [ ] Yayınlanan artefaktı doğrulanan commit'e bağla; manifest/lockfile ve sürüm tutarlılığını kontrol et.
- [x] Aynı sürüm yeniden yayınında mevcut release'i silmeden doğrulanmış varlıkları `--clobber` ile değiştir.
- [x] Release sırasında yalnız açık kaynak yollarını stage et; AI araç dosyalarını kapsam dışında tut.

**Kabul:** Bozuk/değiştirilmiş installer çalışmıyor. Kesilen güncelleme mevcut kullanılabilir kurulumu bozmaz. Standart kullanıcıyla kurulum/yükseltme çalışır. Yayın varlıkları ve kurulu uygulama sürümü eşleşir.

## 14. K: Test matrisi ve son doğrulama

| Katman | Zorunlu senaryolar | Kanıt |
|---|---|---|
| Dosya güvenliği | Protected, denylist, Git dirty/untracked, junction, kök, uzun/Unicode yol | Fixture testleri ve dosya hash'leri |
| Karantina | Disk dolu, izin hatası, bozuk indeks, restart, eşzamanlı işlem, restore çakışması | Kesinti noktaları ve kayıp veri kontrolü |
| Protokol | Bozuk JSON, eksik tip, duplicate id, büyük mesaj, UTF-8, sidecar ölümü | Gerçek süreç entegrasyon testi |
| Tarama | Boş/büyük dizin, erişim engeli, değişen dosya, iptal, cache | İş/sonuç/iptal doğruluğu |
| Frontend | Yeni işlem onayı, kısmi hata, sayfa değişimi, yeniden bağlanma, klavye | Bileşen ve akış testleri |
| Windows | UAC iptali, PID değişimi, başlangıç geri alma, scheduled task sonucu | Ayrılmış Windows ortamı |
| Güvenlik taraması | Yanlış yol, eksik araç, yanlış manifest, ağ kesintisi, partial | Hedef ve sonuç durumu doğrulaması |
| Güncelleme | İmza/hash hatası, indirirken kapanma, paralel istek, kurulum hatası | Doğrulanmış setup + eski kurulum kontrolü |
| Dağıtım | Temiz kurulum, yükseltme, kaldırma, yeniden başlatma | Gerçek paketlenmiş uygulama |
| Kullanılabilirlik | Tara, seç, güvenli sil, geri yükle, iptal | Yardımsız görev sonuçları |

- [ ] Python genel anlamlı kod kapsamı en az %80; silme/karantina/protokol kritik modüllerinde branch coverage en az %95.
- [ ] Yüzdeye ek olarak tüm kritik karar ve kesinti noktaları için senaryo kanıtı bulunuyor.
- [ ] Güvenlik kontrolünü devre dışı bırakan kasıtlı test mutasyonları ilgili testleri gerçekten düşürüyor.
- [ ] Desteklenen Windows ortamlarında gerçek Tauri + paketlenmiş sidecar testleri geçiyor; browser mock testi bunun yerine sayılmıyor.
- [ ] Erişilebilirlik ve görsel kontroller başlangıç pencere boyutunda ve ölçek matrisinde geçiyor.
- [ ] Bağımlılık taraması tüm kullanılan ekosistemleri kapsıyor; açık kritik/yüksek bulgular giderilmiş veya uygulanamazlığı kanıtlanmış.
- [ ] Hedef kullanıcı profilinden en az 5 kişiyle temel görevler deneniyor; kritik görevlerde yardımsız başarı hedefi %100, ciddi kullanım hatası sıfır.
- [ ] En az 7 günlük kontrollü pilotta çökme, kayıp dosya, belirsiz işlem sonucu ve kaynak birikimi kayıtları inceleniyor. Pilotun sonucu tek başına hata yok garantisi sayılmıyor.

## 15. Alan bazında 10/10 kapanış ölçütleri

| Alan | Tamamlanmadan 10 verilmeyecek kriterler |
|---|---|
| Kod kalitesi | I tamam; kritik sınırlar tipli; kontroller temiz; doğrulanmış kusurlar regresyon testli; açıklanmamış hata yutma yok |
| Mimari | C/D/E/I tamam; tek güvenlik politikası; dosya işlemleri kurtarılabilir; sınırlı iş kuyruğu; kalıcı durum geçişi testli |
| UI/UX | G tamam; tüm temel durumlar doğru; erişilebilir modal/klavye; ölçek/tema testleri; kullanıcı görevlerinde ciddi hata yok |
| Performans | H tablosunun tüm hedefleri kayıtlı ortamda sağlanıyor; referans dışı sınırlar açıklanmış; tekrar testleri regresyon göstermiyor |
| Güvenlik | B/C/D/J tamam; tehdit modeli, dependency taraması ve yetki sınırı testleri var; çözülmemiş kritik/yüksek risk yok |
| Testler | K matrisi eksiksiz; anlamlı coverage hedefleri; gerçek paketli masaüstü testleri; testler ilgili hatayı yakalıyor |
| Bakım kolaylığı | I ve release otomasyonu tamam; temiz ortamda tekrar üretilebilir; tanılama ve destek rehberi kullanılabilir |
| Ürün değeri | Kullanıcılar doğru dosyayı seçip güvenle geri alabiliyor; ölçülen fayda doğru sunuluyor; temel görevler yardımsız tamamlanıyor |
| Özellik bütünlüğü | Envanterdeki her özellik için başarı/hata/kısmi/iptal/izin/geri alma kararları testli; yanlış başarı veya gizli yarım özellik yok |
| Üretime hazırlık | Tüm release kapıları geçiyor; installer/güncelleme/kurulu uygulama kanıtı var; pilot tamam; açık P0/P1 yok |

Bir alanın kanıtı eksikse o alan için 10/10 verilmez. Ortalama puan, güvenlik veya veri kaybı açığını örtemez. Ürün kapsamı büyürse değerlendirme yeniden açılır.

## 16. Teslim edilecek çıktılar

- [ ] Bulgu -> değişiklik -> test -> kanıt eşleştirme tablosu.
- [x] Karantina kurtarma ve veri kaybı regresyon testleri.
- [x] GUI/CLI ortak güvenlik politikası ve protokol sözleşmesi.
- [ ] Tamamlanmış ekran durumları ve erişilebilirlik kontrol kaydı.
- [ ] Performans başlangıç/sonuç raporu.
- [x] CI ve yayın öncesi doğrulama akışı.
- [ ] Paketlenmiş uygulama kurulum/yükseltme/geri alma test raporu.
- [x] Desteklenen ortamlar, bilinen sınırlamalar ve kullanıcı yardım metni.
- [ ] Aynı puanlama kriterleriyle yeni application-deep-review raporu.

## 17. Uygulama takip şablonu

Her iş bu kayıtla kapanacak:

```text
İş kimliği:
İlgili inceleme bulgusu:
Öncelik ve etkilenen puanlar:
Değişen dosyalar:
Ön koşullar:
Beklenen kullanıcı davranışı:
Başarı/hata/iptal/kurtarma testleri:
Gerçek ortam doğrulaması:
Kanıt dosyası veya test çıktısı:
Bilinen sınırlar:
Durum: bekliyor / devam ediyor / doğrulandı / engelli
```

**Bitiş koşulu:** Bütün zorunlu kutular kanıtla kapatılmış, açık P0/P1 kalmamış, performans ve kullanılabilirlik hedefleri doğrulanmış, gerçek kurulu uygulama test edilmiş ve on alanın her biri bağımsız olarak yeniden değerlendirilmiş olmalı.
