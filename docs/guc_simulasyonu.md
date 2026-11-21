# Güç Simülasyonu Raporu

**Tarih:** 21 Kasım 2026 · **Durum:** Ana deney verisi toplanmadan önce yapılmıştır.
**Ön kayıt:** https://osf.io/y45rq (tasarım belgesi, Bölüm 10: "Ana deneyden önce, 60 soru × 2
tekrarın beklenen etki büyüklüklerini yakalamaya yetip yetmediği simülasyonla kontrol edilir.")

## 1. Amaç

Doğrulayıcı hipotezlerdeki (H1–H3) etkiler gerçekten varsa, 60 soru × 2 tekrarlık tasarımın
bunları hangi olasılıkla yakalayacağını (istatistiksel güç) önceden belirlemek. Sonuçlar
tasarımı değiştirmek için değil, ana deneyin sonuçlarını doğru yorumlamak için kullanılır:
Bir hipotez desteklenmezse, bunun "etki yok ya da küçük" mü yoksa "tasarımın gücü yetmedi" mi
anlamına geldiği bu tabloya göre değerlendirilir.

## 2. Yöntem

- **Veri yapısı:** Ana deneyle aynı. A: Normal (k = 1, 2, 3, 5 × küçük/büyük hata × Türkçe/
  İngilizce × açık/gizli × 60 soru × 2 tekrar × 3 model = 11.520 cevap) ve A: Müttefik
  (k = 1, 2, 3, 5 × başta/sonda × 60 soru × 2 tekrar × 3 model = 2.880 cevap).
- **Veri üretimi:** Her cevap için uyma olasılığı lojistik bir modelden üretilir:
  taban oran + k etkisi (k sayısal) + büyük hata etkisi + müttefik etkisi + model etkisi +
  soru etkisi.
- **Analiz:** Ön kayıttaki modeller aynen kurulur (Bölüm 10):
  - H1, H2: `uydu ~ k + hata + dil + görünürlük + model + tür + (1 | soru)`
  - H3: `uydu ~ müttefik + k + model + tür + (1 | soru)`, A: Müttefik ile eşleşen A: Normal
    koşulları (Türkçe, küçük, açık)
- **Karar kuralı:** Ön kayıttaki gibi: Üç p değerine Holm düzeltmesi, α = 0,05, etkinin yönü
  hipotezle uyumlu. Model kurulamazsa etki "yakalanamadı" sayılır.
- **Güç:** Etkinin yakalandığı simülasyonların oranı. %80 ve üstü yeterli kabul edilir.
- **Tekrar:** Her senaryoda 500 simülasyon. Monte Carlo hatası: Güç %80 iken ±%3,5
  (%95 aralık).
- **Yazılım:** R 4.6.2, lme4 2.1-0 (`glmer`, binom ailesi, varsayılan optimizer ayarı),
  p değerleri Wald z testinden. Her simülasyon kendi tohumuyla (20261122 + simülasyon no)
  çalışır; sonuç kullanılan çekirdek sayısından bağımsızdır.

### 2.1 Varsayımlar

| Varsayım | Değer | Gerekçe |
|---|---|---|
| Etki büyüklüğü, **orta** | k: her ek suç ortağı için OR 1,20 · büyük hata: OR 0,67 · müttefik: OR 0,67 | k = 1'den 5'e yaklaşık 2 kat; hata ve müttefikte odds'ta üçte bir azalma |
| Etki büyüklüğü, **küçük** | k: OR 1,10 · büyük hata: OR 0,80 · müttefik: OR 0,80 | Pratik olarak anlamlı sayılabilecek en küçük etkilere yakın |
| **Taban uyma oranı** | %2, %5, %20, %40 | Tipik bir soruda, ortalama modelde, k = 3, küçük hata, Türkçe, açık koşulda. %2, pilottaki tutarlılık testinde gözlenen düzeye yakındır (150 cevapta 1 uyma); %20–40, dil modelleri literatüründeki düzeylere yakındır |
| Sorular arası fark | Logit ölçeğinde SS = 1,0 | Soruların uymaya yatkınlığı belirgin biçimde farklı olabilir |
| Model farkı | −0,5 / 0 / +0,5 (logit) | Modeller arasında orta düzeyde fark |
| Dil, görünürlük, tür etkisi | 0 | Doğrulayıcı hipotezlerin parçası değil |
| **Sıfır etki** (doğrulama) | Bütün OR'ler 1, taban %20 | Etki yokken yanlış alarm oranı %5'i aşmamalı |

## 3. Sonuçlar

| Etki | Taban | Ortalama uyma (A: Normal) | Güç H1 | Güç H2 | Güç H3 | Uyarılı kurulum |
|---|---|---|---|---|---|---|
| Orta | %2 | %2,8 | %99 | %84 | **%52** | %12 |
| Orta | %5 | %6,4 | %100 | %100 | %82 | %5 |
| Orta | %20 | %21,1 | %100 | %100 | %100 | %2 |
| Orta | %40 | %37,4 | %100 | %100 | %100 | %0 |
| Küçük | %2 | %3,0 | **%59** | **%35** | **%13** | %14 |
| Küçük | %5 | %6,9 | %89 | **%75** | **%34** | %6 |
| Küçük | %20 | %22,5 | %100 | %99 | **%77** | %2 |
| Küçük | %40 | %39,4 | %100 | %100 | %88 | %0 |
| Sıfır | %20 | %24,4 | %1 | %2 | %1 | %1 |

Kalın değerler %80'in altındadır. "Uyarılı kurulum": Modelin yakınsama uyarısı verdiği ya da
tekil (singular) çıktığı simülasyonların oranı; bu simülasyonlar da analize dahildir.

**Kodun doğrulanması:** Bütün senaryolarda ortalama tahminler gerçek değerlere çok yakındır
(ör. orta etkide k için gerçek 0,182, tahminler 0,179–0,183; küçük etkide gerçek 0,095,
tahminler 0,093–0,096). Sıfır etki senaryosunda yanlış alarm oranı %1–2'dir; Holm düzeltmesi
ve yön şartı nedeniyle %5'in altında kalması beklenir. Ayrıntılar:
`analiz/sonuclar/guc_simulasyonu.csv`.

## 4. Yorum

- **H1 (suç ortağı sayısı):** Taban uyma %5 ve üstündeyse küçük etki için bile güç yeterlidir
  (%89–100). Yalnızca çok düşük uyma (%2) ile küçük etki bir arada olursa güç düşer (%59).
- **H2 (hata büyüklüğü):** Orta etki için her senaryoda yeterli (%84–100). Küçük etki için
  taban %20 ve üstünde yeterli, %5'te sınırda (%75), %2'de yetersiz (%35).
- **H3 (müttefik):** En zayıf halka. Daha az veriye dayanır (yalnızca Türkçe, küçük hata,
  açık) ve müttefiğin azaltabileceği bir uyma olmasını gerektirir. Orta etki için taban %5 ve
  üstünde yeterli (%82–100), %2'de yetersiz (%52). Küçük etki için yalnızca taban %40'ta
  yeterli (%88).

**Ana deneyin yorumu için kural:** Bir doğrulayıcı hipotez desteklenmezse, ana deneyde
gözlenen taban uyma düzeyine en yakın senaryonun gücüne bakılır. Güç %80 ve üstündeyse sonuç
"bu büyüklükte bir etki muhtemelen yok" olarak yorumlanır; %80'in altındaysa "tasarımın bu
etkiyi saptama gücü sınırlıydı; etkinin yokluğu hakkında sonuç çıkarılamaz" olarak raporlanır.

Bu sonuçlar tasarımı değiştirmemiştir; tekrar sayısı ve koşullar ön kayıttaki gibidir.

## 5. Sınırlılıklar

- Sonuçlar varsayımlara bağlıdır. Gerçek soru farkı (SS) daha büyükse güç daha düşük olabilir.
- Dışlama kuralı (Bölüm 9.1) ve sorunlu cevaplar simülasyona dahil edilmemiştir; ana deneyde
  bunlar veri sayısını azaltırsa güç biraz düşebilir.
- k'nin etkisi doğrusal varsayılmıştır (ön kayıttaki analizle aynı). Gerçekte etki k = 3'ten
  sonra düzleşirse H1'in gücü buradakinden farklı olabilir.
- Model × soru etkileşimi (bir sorunun bir modelde zor, diğerinde kolay olması) modellenmemiştir.

## 6. Yeniden üretme

```bash
Rscript analiz/guc_simulasyonu.R 500
```

Süre: 12 işçiyle yaklaşık 2,5 saat (Intel i7-13700HX). Aynı tohumlar kullanıldığı için
güç değerleri birebir aynı çıkar.