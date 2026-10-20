# YuROM Ultra One UI 9 — {{VERSION}} Beta paketi

Bu sürüm yalnızca **Exynos SM-G970F, SM-G973F ve SM-G975F** içindir.
S10 5G, Snapdragon ve Kore `N` modelleri desteklenmez. Her model için kendi
iki ZIP dosyasını kullanın. Paket bölüm tablosunu değiştirmez.

## Ekran profilleri

| Model | Cihaz | Varsayılan ekran | Yoğunluk | Kamera tarafı boşluğu |
|---|---|---|---|---|
| SM-G970F | S10e | 1080×2280, 60 Hz | 480 DPI | 56 dp |
| SM-G973F | S10 | 1080×2280, 60 Hz | 420 DPI | 64 dp |
| SM-G975F | S10+ | 1080×2280, 60 Hz | 420 DPI | 100 dp |

Kamera geometrisi her modelin Samsung stock vendor kaynakları ve
[ExtremeROM cihaz profilleri](https://github.com/ExtremeXT/ExtremeROM/tree/2056320784b7d1d88f9e7025f86f7bbd39945d6b/target)
ile karşılaştırıldı. S10+ çift kamera boşluğu, S10e/S10 tek kamera boşluğundan
farklıdır. Ekran ayarları ROM içinden ilk kurulumda oluşturulur; sonradan
seçtiğiniz çözünürlük her açılışta zorla değiştirilmez.

## Kurulum — veri silinir

1. Uygulamaları, hesapları, fotoğrafları ve dahili depolamayı başka bir yere
   yedekleyin. Mevcut çalışan sistem için geri dönüş yedeğini saklayın.
2. Kilidi açık bootloader ve modele uygun HWC1/HWC2 tabanı gerekir.
   Paket bootloader, modem, EFS veya recovery kurmaz.
3. TWRP'de **Format Data → yes** uygulayın. Bu işlem uygulamaları, hesapları
   ve dahili depolamayı siler. Ardından recovery'yi yeniden başlatın.
4. Modelinize ait `*_TWRP.zip` ve `*_INSTALLER_r4.zip` dosyalarını aynı
   klasöre kopyalayın. exFAT microSD/OTG veya format sonrası dahili depolama
   kullanın. Büyük dosya FAT32'ye sığmaz.
5. `SHA256SUMS.txt` ile dosyaları doğrulayın. TWRP'den **küçük
   `*_INSTALLER_r4.zip`** dosyasını kurun. TWRP 3.7.0_9-1 büyük ZIP64 dosyasını
   doğrudan açamaz; iki dosyalı başlatıcı bu recovery ile uyumluluk sağlar.
6. Kurucunun **“Installation and block-device readback passed.”** mesajını
   bekleyin; ardından System'e yeniden başlatın. İlk açılış birkaç dakika sürebilir.

Bu iki dosyalı yöntem ADB sideload ile kullanılamaz; iki dosya da normal
bağlanmış depolamada aynı klasörde olmalıdır. Format veya kurulum hata verirse
başarı mesajı alınmadan Android'e yeniden başlatmayın. Eski TWRP, Android'in
FBE verisini çözemez ve EROFS system'i dosya olarak bağlayamaz; imaj kurucusu
ham bölüm yazımı ve geri okuma kullanır.

## Özellikler ve gizlilik

Native YuROM ayarları; modele özel kernel ve donanım girdileri; kamera
uyumluluk katmanı; CE kilit açma düzeltmesi; ekran/kamera boşluğu profilleri;
tek dokunuşlu yerel öğrenme destekli OC/undervolt kontrolü bulunur.
OC/undervolt donanıma ve sıcaklığa bağlıdır; uzun süreli kararlılık her cihaz
için garanti edilmez. Telemetri varsayılan kapalıdır ve açık katılım gerektirir.
Rapor önizleme ve gönderilen kurulum kaydını silme seçenekleri vardır.

YuROM ayarlarındaki **YuROM Ultra · GitHub** satırı ve
**Telefon hakkında → Yazılım bilgileri** altındaki aynı bağlantı
[projenin GitHub profiline](https://github.com/yuefdev) açılır. ROM adı,
derleme etiketi ve kurulum ekranı YuROM Ultra olarak gösterilir. Donör ve
kernelin gerçek teknik kimlikleri kaynak/kredi bilgisi olarak korunur.

## Doğrulama kapsamı

Bu bir **Beta sürümüdür**. Her modelin
ayrıntılı durumu yanındaki `VALIDATION.json` dosyasındadır. S10e ve S10+
paketleri gerçek cihazda henüz sınanmadı. S10'daki imaj güncellemesi ve önceki
temiz kurulum kanıtları, diğer modellerin veya aynı ZIP'in temiz kurulum
kabulü yerine geçmez.

SELinux doğrulanan yapılandırmada **Permissive**; Enforcing kabulü yok. TV'den duyulur
HDMI sesi/DeX çıkar-tak, tüm modem/kamera/parmak izi işlevleri ve uzun süreli
OC/undervolt kararlılığı tamamlanmış kabul edilmez. Personal/Moneta için
özellik destek kapıları eklenmiştir; cihaz regresyon sonucu `VALIDATION.json`
içinde ayrı belirtilir. Testleri geçmeyen alanlar çalışıyor diye sunulmaz.

## Kaynak ve katkılar

Model geometrisi ve port yaklaşımı için ExtremeXT/ExtremeROM ve bağımsız
karşılaştırma için LineageOS cihaz ağaçları kullanıldı. Vendor, kernel,
boot/DTBO ve parmak izi uyarlamaları her modele özeldir. Değişiklikler için
projenin GPL-3.0-or-later ve ilgili upstream lisans bildirimleri geçerlidir.
