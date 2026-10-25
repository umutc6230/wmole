# Karantina kalıcılık tasarımı

wmole, karantina metadata'sını atomik değiştirilen kilitli bir JSON indeksi ve her öğenin
yanındaki `entry.json` işlem manifestiyle tutar. Windows dosya kilidi aynı anda çalışan
uygulama örneklerinin indeks güncellemelerini sıraya koyar.

Bir işlem `prepared -> moving -> committed` durumlarından geçer. Geri yükleme sırasında
durum `restoring` olur. Metadata kaydı başarısızsa kaynak konuma geri alma denenir; bu da
başarısızsa kasadaki kopya korunur ve yolu kullanıcıya bildirilir.

Metadata transaction'ı dosya sistemi taşımasını atomik hale getirmez. Bu nedenle uygulama
başlangıcındaki güvenlik özeti, kasa dizinleriyle indeksi uzlaştırır. Manifesti geçerli ve
dosyası kasada olan sahipsiz öğe `recoverable` olarak yeniden indekse alınır. Kaynağı geri
gelmiş ve kasadaki dosyası bulunmayan kayıt bayat kabul edilir. Geçersiz veya kasa dışını
gösteren manifest hiçbir dosyaya dokunmadan reddedilir.

İlk uzlaştırma değişikliğinde eski indeks `index.json.bak` olarak yedeklenir. İşlem yeniden
çalıştırılabilir; aynı kimlik ikinci bir kayıt veya ikinci bir dosya hareketi üretmez.

Kalan sınır: farklı diskler arasındaki klasör taşımasının içerik hash doğrulaması ayrıca
tamamlanmalıdır. Tekil dosyada veya aynı diskte mevcut güvenli davranış korunur.
