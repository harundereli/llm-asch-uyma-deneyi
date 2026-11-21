# Dil Modeli Ajanlarında Asch Paradigmasıyla Çoğunluk Etkisi

> **Durum:** Altyapı tamamlandı ve otomatik testlerle doğrulandı. Pilot çalışma tamamlandı
> ([pilot raporu](docs/pilot_raporu.md)); henüz ana veri toplanmadı. Araştırma tasarımı ve
> hipotezler veri toplanmadan önce OSF'de ön kayda alınmıştır: https://osf.io/y45rq

Bu proje, Solomon Asch'ın klasik uyma deneylerini (1951, 1956) büyük dil modellerine uyarlar.
Temel soru: Bir dil modeli, doğru cevabı bildiği hâlde, yanlış cevap veren bir çoğunluğa uyar mı?
Birden fazla model aynı gruptayken birbirlerini nasıl etkiler?

## Araştırma soruları

1. Dil modelleri yanlış bir çoğunluğa uyar mı? Uyma, çoğunluğun büyüklüğüyle nasıl değişir?
2. Bu davranış modelden modele ve soru türünden soru türüne farklılaşır mı?
3. Gerçek modellerin birlikte bulunduğu bir grupta etkileşim nasıl işler?
4. Uymanın ne kadarı sosyal çerçeveye bağlıdır?

## Deney düzeni (özet)

| Parça | İçerik |
|---|---|
| **A: Normal** | Model, aynı yanlış cevabı veren 0–5 sabit ajanla (suç ortağı) aynı grupta |
| **A: Müttefik** | Gruba doğru cevabı veren bir sabit ajan eklenir |
| **A: Kaynaksız kontrol** | Aynı yanlış cevap, hiçbir konuşmacı olmadan metin olarak tekrarlanır |
| **B: Karma grup** | Sabit ajanlardan sonra üç model sırayla cevaplar ve birbirini görür |

- **Modeller:** `deepseek-v4.1-flash`, `qwen3.8-flash-next`, `gemma-4-31b`
  (Savunma Sanayii Başkanlığı'nın EVREN platformu üzerinden, düşünme kapalı)
- **Sorular:** 60 soru: 20 sembolik çizgi, 20 bilgi, 20 aritmetik; her birinde 4 şık
- **Değişkenler:** Suç ortağı sayısı, hata büyüklüğü, dil (Türkçe/İngilizce), cevabın görünürlüğü
- **Hacim:** ~28.500 API çağrısı

Tasarımın tamamı (hipotezler, analiz planı, sınırlılıklar): [`docs/tasarim.md`](docs/tasarim.md)

Ön kayıt (OSF, 21.11.2026): https://osf.io/y45rq

## Proje yapısı

| Yol | İçerik |
|---|---|
| `docs/tasarim.md` | Araştırma tasarımı ve hipotezler |
| `docs/pilot_raporu.md` | Pilot çalışmanın raporu |
| `asch/sorular.py` | Soru havuzunun üretilmesi ve doğrulanması |
| `asch/promptlar.py` | Her deney koşulu için prompt şablonları |
| `asch/model.py` | EVREN bağlantısı (yeniden deneme ve hata kaydı) |
| `asch/siniflandirma.py` | Cevapların ayrıştırılması ve sınıflandırılması |
| `asch/kayit.py` | Ham veri kaydı (yalnızca ekleme, kaldığı yerden devam) |
| `asch/plan.py` | Deney planı: bütün denemeler (27.900 ana, 510 pilot çağrısı) |
| `asch/calistir.py` | Çalıştırıcı: hız sınırı, B grupları, durdurma kuralları, kaldığı yerden devam |
| `asch/baglanti_testi.py` | EVREN bağlantı testi |
| `veri/sorular.json` | Deneyde kullanılan 60 soru |
| `veri/ham/` | Ham veri (her API çağrısı bir satır, JSONL) |
| `analiz/pilot_analizi.py` | Pilot raporundaki sayıları üreten analiz |
| `testler/` | Otomatik testler |

## Kurulum

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

`.env.example` dosyasını `.env` adıyla kopyalayın ve kendi EVREN API anahtarınızı girin.

```bash
python -m pytest                  # Otomatik testler
python -m asch.sorular            # Soru havuzunu üretir ve doğrular
python -m asch.promptlar          # Örnek promptları gösterir
python -m asch.baglanti_testi     # EVREN bağlantısını test eder (3 API çağrısı)
python -m asch.plan               # Deney planının özeti
python -m asch.calistir ana --kuru   # API'ye gitmeden yapılacakları gösterir
python -m asch.calistir pilot     # Pilot çalışma (510 çağrı)
python -m analiz.pilot_analizi    # Pilot raporundaki sayıları üretir
python -m asch.calistir ana       # Ana deney (kaldığı yerden devam eder)
```

## Prototip

Bu çalışma, daha önce hazırlanmış bir prototipin genişletilmiş ve yeniden tasarlanmış sürümüdür:
[llm-ajan-uyma-deneyi](https://github.com/harundereli/llm-ajan-uyma-deneyi)

## Lisans

- **Kod:** [MIT](LICENSE)
- **Veri ve belgeler** (`veri/`, `docs/`): [CC BY 4.0](LICENSE-DATA)

## Teşekkür

Deneyde kullanılan modellere Savunma Sanayii Başkanlığı'nın EVREN platformu üzerinden erişilmiştir.

---

Harun Dereli · Sakarya Üniversitesi, Yönetim Bilişim Sistemleri