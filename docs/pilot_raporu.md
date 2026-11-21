# Pilot Raporu

**Tarih:** 21 Kasım 2026, 11.32–12.15 (Türkiye saati) · **Durum:** Ana deneyden önce, OSF ön
kaydından önce yazılmıştır.

- Ham veri: `veri/ham/pilot.jsonl` (518 satır)
- Bu rapordaki bütün sayılar: `python -m analiz.pilot_analizi`
- Pilot verisi ana analize **dahil edilmez** (tasarım belgesi, Bölüm 8).

## 1. Amaç

Tasarım belgesi Bölüm 8'e göre pilotun amacı teknik kontroldür: soruların modeller tarafından
tek başına doğru bilinip bilinmediği, cevapların tekrarlar arasındaki tutarlılığı, çağrı başına
token kullanımı ve altyapının (JSON cevap biçimi, düşünmenin kapalı olması, hata yönetimi)
gerçek ortamda çalışması.

## 2. Yürütme

| | |
|---|---|
| Kontrol ön testi | 60 soru × 2 dil × 3 model = 360 çağrı (temperature 0, tek başına) |
| Tutarlılık testi | 10 soru × 5 tekrar × 3 model = 150 çağrı (k = 3, Türkçe, küçük hata, açık) |
| Ayarlar | 180 RPM, 16 paralel iş parçacığı; düşünme kapalı, JSON cevap biçimi |
| EVREN durumu | Pilot sırasında platform panelinde DeepSeek ve Gemma "Yoğun", Qwen "Orta" görünüyordu. |

Pilot üç oturumda yürütüldü: 6 çağrılık bir duman testi, ardından pilotun geri kalanı ve son
olarak teknik hata nedeniyle tamamlanamayan 8 denemenin tamamlanması.

## 3. Sonuçlar

### 3.1 Kontrol ön testi

Üç modelin üçü de her iki dilde ve her üç soru türünde soruların **%100'ünü** doğru cevapladı
(her model × dil × tür hücresinde 20/20; toplam 360/360). Bölüm 8'deki karar kuralı (%90 eşiği)
**tetiklenmedi.**

### 3.2 Tutarlılık testi

| Model | Bağımsız | Uydu | Tekrarlar arasında cevabı değişen soru |
|---|---|---|---|
| deepseek-v4.1-flash | 50 | 0 | 0/10 |
| gemma-4-31b | 50 | 0 | 0/10 |
| qwen3.8-flash-next | 49 | 1 | 1/10 (ART-03) |

Cevaplar tekrarlar arasında büyük ölçüde aynı kaldı. En az bir modelde cevabın değişmesi ve
çağrı sürelerinin tekrarlar arasında saniyelerce farklılaşması, cevapların önbellekten
döndürülmediğini gösterir.

### 3.3 Teknik kontroller

| Kontrol | Sonuç |
|---|---|
| Düşünme tokenı ya da düşünme metni | 0 çağrıda |
| Sorunlu (okunamayan) cevap | 0 |
| Bitiş nedeni | Bütün geçerli çağrılarda "stop" |
| API'nin döndürdüğü model adı | Bütün çağrılarda istenen adla aynı |
| Teknik hata | 8 çağrı (hepsi DeepSeek, 429); sonraki oturumda tamamlandı |
| Yeniden deneme gerektiren çağrı | 64 (hepsi aynı nedenle) |

**429 hatalarının nedeni:** EVREN'in hata mesajı: *"Model şu an yoğun; hesabınız bu modelde en
fazla 2 eşzamanlı istek açabilir."* Pilot, aynı modele 2'den fazla eşzamanlı istek gönderiyordu.

**Sistem izi:** Aynı model adına farklı sunucu örnekleri cevap verdi (DeepSeek ve Gemma için
ikişer farklı sistem izi). Bu, platformun yük dengelemesinin doğal bir sonucudur; model adı
değişmemiştir.

### 3.4 Token ve süre

| | |
|---|---|
| Ortalama girdi tokenı | 144 (tek başına), 213 (3 suç ortağıyla) |
| Ortalama çıktı tokenı | ~8 |
| Pilotun toplam tokenı | 87.668 |
| **Ana deney tahmini** | **~5,9 milyon token** |

Ana deney tahmini, pilotta her model ve dil için ölçülen token/karakter oranının ana deneydeki
her denemenin promptuna tek tek uygulanmasıyla hesaplanmıştır.

| Model | Cevap süresi medyanı | %90 | En fazla |
|---|---|---|---|
| deepseek-v4.1-flash | 6,9 sn | 36,3 sn | 94,6 sn |
| gemma-4-31b | 2,2 sn | 6,7 sn | 35,2 sn |
| qwen3.8-flash-next | 0,9 sn | 2,5 sn | 7,6 sn |

## 4. Pilota dayanarak alınan kararlar

| Konu | Karar |
|---|---|
| Soru havuzu | Değişmedi (karar kuralı tetiklenmedi). |
| Tekrar sayısı | 2'de kalıyor (daha önce sabitlenmişti). |
| Eşzamanlılık | Çalıştırıcıya **model başına en fazla 2 eşzamanlı istek** sınırı eklendi; paralel iş parçacığı sayısı 16 oldu. |
| Token tahmini | Tasarım belgesi Bölüm 7'de ~8,4 milyondan ~5,9 milyona güncellendi. |
| Durdurma kuralı | Bölüm 2'deki kural netleştirildi: Model adı değişirse deney durur; sistem izinin değişmesi (yük dengeleme) durdurma nedeni sayılmaz, her satırda kaydedilir. |
| Çalıştırma zamanı | Ana deney, EVREN'in modelleri yoğun olmadığı bir saatte başlatılacak (DeepSeek darboğaz). |

## 5. Tasarımın korunması

Tutarlılık testinde modeller 3 suç ortağına neredeyse hiç uymadı (150 denemede 1). Bu sonuç
yalnızca 10 soru ve tek bir koşuldan gelir; **pilotun amacı teknik kontroldür.** Pilotun uyma
sonuçlarına bakılarak hipotezlerde, deney koşullarında, soru havuzunda ya da analiz planında
**hiçbir değişiklik yapılmamıştır.** Yukarıdaki kararların hepsi teknik niteliktedir.
