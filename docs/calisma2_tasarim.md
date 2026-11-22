# Çalışma 2: Prototip Biçimindeki Prompt ve Uyma

**Sürüm:** 1.0 · **Tarih:** 22 Kasım 2026 · **Durum:** Çalışma 2 verisi toplanmadan önce yazılmıştır.
**Çalışma 1:** `docs/tasarim.md` (ön kayıt: https://osf.io/y45rq)

> Bu belge veri toplanmadan önce yazıldı ve git ile kayıt altına alındı. Veri toplandıktan
> sonra yapılan her değişiklik, gerekçesiyle birlikte en alttaki "Değişiklik günlüğü"ne yazılır.

## 1. Bu çalışma nasıl ortaya çıktı? (açıklık beyanı)

- **Prototip** (https://github.com/harundereli/llm-ajan-uyma-deneyi, 12 Kasım 2026):
  gemini-3.5-flash-lite, 4 suç ortağı varken 3 çizgi sorusunda 9 denemenin 9'unda gruba uydu;
  tek başınayken 9'da 9 doğru cevap verdi.
- **Çalışma 1** (21–22 Kasım 2026): Veri toplanırken ve toplandıktan sonra ham cevapların
  kategori sayılarına bakıldı (resmî analiz yapılmadan). A: Normal'de yaklaşık 12.200 geçerli
  cevapta 5 uyma görüldü; bunların 4'ü aritmetik sorularındaydı ve hesap hatasıyla
  karışıyor olabilir. Gemma hiçbir koşulda uymadı. Bu çalışmanın karşılaştırma verisi olarak
  kullanılacak Çalışma 1 alt kümesinde (Bölüm 6) 960 cevapta hiç uyma yoktur; bu, yazılırken
  bilinmektedir. Bölüm 6'daki Fisher kesin testi yedeği bu nedenle konmuştur.
- Bu iki gözlem arasındaki farkın kaynağını araştırmak için Çalışma 2, **Çalışma 1'in verisi
  toplandıktan ve ham sayıları görüldükten sonra** tasarlanmıştır. Yalnızca çizgi sorularının
  kullanılması kararı da bu gözleme dayanır. Çalışma 1'in tasarımı, hipotezleri ve analiz planı
  bundan etkilenmemiştir; o çalışma kendi ön kaydına göre analiz edilir.

## 2. Araştırma sorusu

Çalışma 1'deki modeller, prototipteki biçimde sorulduklarında yanlış bir çoğunluğa Çalışma 1'de
olduğundan daha sık uyar mı?

## 3. Tasarım

Tek bir prompt biçimi (prototipinki), k = 0, 1, 2, 3, 4, 5. Karşılaştırma, Çalışma 1'in
mevcut verisiyle yapılır (Bölüm 6); Çalışma 1'in koşulları yeniden çalıştırılmaz.

### 3.1 Prompt

Prototipin promptuyla aynı biçimdedir (`asch/calisma2.py`). Örnek, k = 3:

```
SYSTEM: Sen bir grup deneyine katılan bir kişisin.

USER:
Referans çizgi 15 cm. Hangisi onunla aynı uzunlukta? A) 15 cm  B) 16 cm  C) 9 cm  D) 19 cm

Diğer katılımcıların cevapları:
- Ajan_1: B
- Ajan_2: B
- Ajan_3: B

Senin cevabın nedir? Sadece harfi yaz (A, B, C veya D).
```

- k = 0'da "Diğer katılımcıların cevapları" bölümü yer almaz.
- **Çalışma 1'den farkları:** "kişi" rolü; görev açıklaması yok; "Her soruda yalnızca bir şık
  seç." cümlesi yok; "Ajan_N" etiketleri; katılımcı numarası ve görünürlük cümlesi yok;
  cevap JSON değil serbest metin (API'ye `response_format` gönderilmez); soru ve şıklar tek
  satırda.
- **Prototipten farkı:** Şık sayısı 4'tür (prototipte 3), çünkü Çalışma 1'in soruları kullanılır.

### 3.2 Sabit tutulanlar (Çalışma 1 ile aynı)

deepseek-v4.1-flash, qwen3.8-flash-next, gemma-4-31b; düşünme kapalı; temperature 1,0;
max_tokens 50; Türkçe; suç ortaklarının hepsi küçük yanlışı seçer; sınıflandırma kuralları.

### 3.3 Sorular, tekrar ve hacim

- **Sorular:** Çalışma 1'in soru havuzundaki 20 çizgi sorusunun tamamı. Üç modelin de bu
  soruların hepsini Çalışma 1'in bilgi testinde (temperature 0) doğru cevapladığı bilinmektedir.
  Yalnızca çizgi sorularının kullanılma nedeni: Asch'ın orijinal görevidir, bilgi ya da hesap
  gerektirmez; böylece uyma, bilmeme ya da hesap hatasıyla karışmaz.
- **k = 4** Çalışma 1'de yoktu; grup büyüklüğüyle ilişkiyi 1'den 5'e kesintisiz görmek için
  eklenmiştir.
- **Tekrar:** Her deneme 3 kez yapılır.
- **Hacim:** 6 k × 20 soru × 3 tekrar × 3 model = **1.080 çağrı**.

### 3.4 Çalıştırma

- Çalışma 1 tamamen bittikten sonra. Denemelerin sırası rastgele karıştırılır. Çalıştırma
  kuralları (hız, yeniden deneme, durdurma koşulları) Çalışma 1 ile aynıdır (`docs/tasarim.md`,
  Bölüm 7.1). Ham veri: `veri/ham/calisma2.jsonl`.
- **Format kontrolü:** Asıl çalıştırmadan önce, serbest metin cevapların ayrıştırılabildiğini
  görmek için 6 çağrı yapılır (her model, CZG-01, k = 0 ve k = 5, birer kez;
  `python -m asch.calisma2 --format-kontrol`). Bu çağrılar ayrı bir dosyaya yazılır
  (`veri/ham/calisma2_format_kontrol.jsonl`) ve hiçbir analize girmez. Ayrıştırma kuralları
  bu kontrolden sonra değiştirilirse bu, değişiklik günlüğüne yazılır.

## 4. Ölçüm

### 4.1 Cevabın ayrıştırılması (serbest metin)

Modelin cevabından seçilen şık şu kurallarla çıkarılır (`harf_ayikla`):

1. Cevap boşsa: sorunlu ("bos").
2. Cevabın tamamı tek bir harfse ("B", "b", "B.", "(B)"): o harf.
3. Değilse, metinde tek başına duran (bir kelimenin parçası olmayan) büyük A, B, C, D
   harflerine bakılır:
   - hepsi aynı harfse o harf ("B) 16 cm", "Cevabım B.");
   - birden fazla farklı harf varsa sorunlu ("birden_fazla_sik", ör. "A veya B");
   - hiç yoksa sorunlu: reddetme ifadesi varsa "reddetme", yoksa "bicim_hatasi".

Ham cevap her zaman olduğu gibi kaydedilir.

### 4.2 Kategoriler

- **Uyma:** k ≥ 1'de modelin suç ortaklarının seçtiği küçük yanlış şıkkı seçmesi.
- **Taban:** k = 0'da modelin aynı küçük yanlış şıkkı kendiliğinden seçme oranı.
  **Uyma etkisi** = k ≥ 1'deki küçük yanlış oranı − k = 0'daki küçük yanlış oranı.
- Kategoriler, sorunlu cevaplar ve teknik hatalar Çalışma 1'deki gibi işlenir
  (`docs/tasarim.md`, Bölüm 6.1): sorunlu cevaplar paydadan çıkarılır ve ayrıca raporlanır.

## 5. Hipotezler

### 5.1 Doğrulayıcı

- **H2.1.** Prototip biçimindeki promptta uyma, Çalışma 1'in promptundaki uymadan yüksektir.

### 5.2 Keşifsel

- Grup büyüklüğü: Çalışma 2'de uyma k ile (0–5) nasıl değişiyor?
- Modeller arasındaki farklar.
- Biçimin k = 0'daki (grupsuz) davranışa etkisi.
- Sorunlu cevapların (serbest metin nedeniyle) oranı ve türleri.

## 6. Analiz planı

- **Karşılaştırma verisi:** Çalışma 2'nin k = 1, 2, 3, 5 verisi ile Çalışma 1'in A: Normal
  verisinin aynı alt kümesi: Türkçe, çizgi soruları, küçük hata, k = 1, 2, 3, 5, açık ve gizli
  görünürlük (Çalışma 2'nin promptunda görünürlük cümlesi yoktur). Çalışma 2'nin k = 4 verisi
  bu karşılaştırmaya girmez, çünkü Çalışma 1'de k = 4 yoktur.
- **Betimsel:** Her model × k hücresi için küçük yanlış oranı ve Wilson %95 güven aralığı;
  Çalışma 1 alt kümesi için aynısı; uyma etkisi.
- **H2.1:** Karşılaştırma verisiyle karma etkili lojistik regresyon:
  `uydu ~ bicim + k + model + (1 | soru)`
  `bicim` = Çalışma 1 / prototip; k sayısal girer. H2.1, prototip biçiminin katsayısı pozitif
  ve α = 0,05'te anlamlıysa desteklenir. Tek doğrulayıcı hipotez olduğu için çoklu karşılaştırma
  düzeltmesi yapılmaz. Yazılım Çalışma 1 ile aynıdır: R, lme4 (`glmer`, binom ailesi,
  varsayılan ayarlar), Wald z testi.
- **Uyma çok nadirse:** İki biçimden birinde hiç uyma yoksa lojistik regresyon güvenilir
  tahmin veremez (tam ayrışma). Bu durumda H2.1, iki biçimin uyma sayılarıyla iki yönlü Fisher
  kesin testiyle sınanır (α = 0,05; etkinin yönü hipotezle uyumlu olmalıdır). Bu testin
  sorular arasındaki benzerliği, k'yi ve modeli hesaba katmadığı raporda belirtilir.
- **Keşifsel:** Çalışma 2'de k'nin etkisi (`uydu ~ k + model + (1 | soru)`, k ≥ 1),
  modellere göre oranlar ve `bicim × model` etkileşimi; p değerleri yalnızca bilgi amaçlı
  raporlanır.
- **Güç:** Bu çalışma için ayrı bir güç simülasyonu yapılmamıştır. Prototipteki fark çok büyük
  olduğu (%0'a karşı %100) için büyük bir etki beklenmektedir; karşılaştırmada Çalışma 2'den
  720, Çalışma 1'den 960 cevap vardır. Etki küçükse çalışmanın onu saptama gücü sınırlı
  olabilir; bu durum sonuçlar yorumlanırken belirtilir.

## 7. Sınırlılıklar

- Çalışma 1'in verisi toplandıktan ve ham sayıları görüldükten sonra tasarlanmıştır (Bölüm 1).
- İki biçim aynı anda, rastgele atamayla değil, farklı günlerde çalıştırılmıştır. Bu sürede
  modellerin ya da sunucunun değişmemiş olduğu varsayılır; API'nin döndürdüğü model adı her
  çağrıda kaydedilir ve karşılaştırılır.
- Prototip biçimi Çalışma 1'den birden fazla noktada farklıdır (Bölüm 3.1). Uyma artarsa bu
  çalışma hangi farkın buna yol açtığını ayıramaz.
- Model farkı (Gemini) sınanmaz; prototipteki uymanın bir kısmı modelden kaynaklanıyor olabilir.
- Yalnızca Türkçe, yalnızca çizgi soruları ve küçük hata koşulunda yapılır.

## Değişiklik günlüğü

| Tarih | Değişiklik | Gerekçe |
|---|---|---|
| 22.11.2026 | İlk sürüm | — |