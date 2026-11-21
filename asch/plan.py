"""
Deney planı (tasarım belgesi, Bölüm 4, 7 ve 8).

Tasarımdaki bütün denemeleri tek tek oluşturur. Her deneme; hangi parçaya ait olduğunu,
hangi soru, model, dil ve koşulda yapılacağını bilir ve kendine özgü, değişmeyen bir kimliğe
(deneme_id) sahiptir. Kaldığı yerden devam etme bu kimlikle yapılır.

- Tek modelli parçalarda bir deneme = bir API çağrısı.
- B düzeneğinde bir deneme = bir grup = sırayla üç API çağrısı.

Plan özetini görmek için:  python -m asch.plan
"""

import itertools
import random
from dataclasses import dataclass

from asch.model import MODELLER

TEKRAR = 2
K_GRUP = [1, 2, 3, 5]
K_HEPSI = [0, *K_GRUP]
HATALAR = ["kucuk", "buyuk"]
DILLER = ["tr", "en"]
GORUNURLUKLER = ["acik", "gizli"]
MUTTEFIK_KONUMLARI = ["basta", "sonda"]
SIRALAMALAR = list(itertools.permutations(MODELLER))  # 3! = 6 sıralama

MAX_TOKENS = 50
MAX_TOKENS_GEREKCE = 300
GEREKCE_SORU_SAYISI = 10        # gerekçe ek testinde her türden kullanılan soru sayısı
PILOT_TUTARLILIK_TEKRAR = 5
PILOT_TUTARLILIK_SORULARI = {"cizgi": 3, "bilgi": 4, "aritmetik": 3}  # toplam 10 soru

SIRA_TOHUMU = 20261121  # denemelerin çalıştırılma sırasını karıştırmak için


@dataclass(frozen=True)
class Deneme:
    parca: str
    soru_id: str
    dil: str
    k: int
    tekrar: int = 1
    model: str | None = None              # tek modelli parçalarda
    sira: tuple[str, ...] | None = None   # yalnızca B: modellerin konuşma sırası
    hata: str | None = None               # çoğunluğun seçtiği yanlış: "kucuk" | "buyuk"
    gorunurluk: str | None = None         # "acik" | "gizli"
    muttefik_konumu: str | None = None    # "basta" | "sonda"
    gerekce: bool = False

    @property
    def deneme_id(self) -> str:
        katilimci = self.model if self.model else ">".join(self.sira)
        alanlar = [
            self.parca, katilimci, self.soru_id, self.dil, f"k{self.k}",
            self.hata or "-", self.gorunurluk or "-", self.muttefik_konumu or "-", f"t{self.tekrar}",
        ]
        return "|".join(alanlar)

    @property
    def temperature(self) -> float:
        return 0.0 if self.parca in ("bilgi_testi", "pilot_kontrol") else 1.0

    @property
    def max_tokens(self) -> int:
        return MAX_TOKENS_GEREKCE if self.gerekce else MAX_TOKENS

    @property
    def cagri_sayisi(self) -> int:
        return len(self.sira) if self.sira else 1


# ---------------------------------------------------------------------------
# Parçalar (tasarım belgesi, Bölüm 4)
# ---------------------------------------------------------------------------

def _idler(sorular: list[dict]) -> list[str]:
    return [s["id"] for s in sorular]


def bilgi_testi(sorular: list[dict], parca: str = "bilgi_testi") -> list[Deneme]:
    """4.1: Her model, her soruyu, her dilde, temperature 0 ile bir kez, tek başına."""
    return [
        Deneme(parca, sid, dil, 0, model=m)
        for m, dil, sid in itertools.product(MODELLER, DILLER, _idler(sorular))
    ]


def a_normal(sorular: list[dict]) -> list[Deneme]:
    """4.2: k = 0 (tek başına) ve k = 1, 2, 3, 5 × hata × görünürlük; iki dil, iki tekrar."""
    denemeler = []
    for m, sid, dil, t in itertools.product(MODELLER, _idler(sorular), DILLER, range(1, TEKRAR + 1)):
        denemeler.append(Deneme("A_normal", sid, dil, 0, t, model=m))
        for k, hata, gor in itertools.product(K_GRUP, HATALAR, GORUNURLUKLER):
            denemeler.append(Deneme("A_normal", sid, dil, k, t, model=m, hata=hata, gorunurluk=gor))
    return denemeler


def a_muttefik(sorular: list[dict]) -> list[Deneme]:
    """4.3: Türkçe, küçük hata, açık; k = 1, 2, 3, 5; müttefik başta ya da sonda."""
    return [
        Deneme("A_muttefik", sid, "tr", k, t, model=m, hata="kucuk", gorunurluk="acik", muttefik_konumu=konum)
        for m, sid, k, konum, t in itertools.product(
            MODELLER, _idler(sorular), K_GRUP, MUTTEFIK_KONUMLARI, range(1, TEKRAR + 1))
    ]


def a_kaynaksiz(sorular: list[dict]) -> list[Deneme]:
    """4.4: Türkçe, küçük hata; aynı yanlış cevap k kez, konuşmacı olmadan."""
    return [
        Deneme("A_kaynaksiz", sid, "tr", k, t, model=m, hata="kucuk")
        for m, sid, k, t in itertools.product(MODELLER, _idler(sorular), K_GRUP, range(1, TEKRAR + 1))
    ]


def b_karma(sorular: list[dict]) -> list[Deneme]:
    """4.5: Türkçe, küçük hata, açık; k = 0–5; üç modelin 6 sıralamasının hepsi."""
    return [
        Deneme("B", sid, "tr", k, t, sira=sira, hata="kucuk" if k else None, gorunurluk="acik")
        for sira, sid, k, t in itertools.product(SIRALAMALAR, _idler(sorular), K_HEPSI, range(1, TEKRAR + 1))
    ]


def _turden_ilk(sorular: list[dict], adetler: dict[str, int]) -> list[str]:
    """Her türün ilk n sorusunun kimlikleri (soru sırası zaten rastgele üretilmiştir)."""
    return [s["id"] for tur, n in adetler.items() for s in [x for x in sorular if x["tur"] == tur][:n]]


def gerekce_testi(sorular: list[dict]) -> list[Deneme]:
    """4.6: k = 3, küçük hata, Türkçe; açık ve gizli; her türden 10 soru; bir kez."""
    secilen = _turden_ilk(sorular, {tur: GEREKCE_SORU_SAYISI for tur in ("cizgi", "bilgi", "aritmetik")})
    return [
        Deneme("gerekce", sid, "tr", 3, model=m, hata="kucuk", gorunurluk=gor, gerekce=True)
        for m, sid, gor in itertools.product(MODELLER, secilen, GORUNURLUKLER)
    ]


def ana_plan(sorular: list[dict]) -> dict[str, list[Deneme]]:
    """Bütün ana deney, tasarımdaki çalıştırma sırasıyla (Bölüm 7)."""
    return {
        "bilgi_testi": bilgi_testi(sorular),
        "A_normal": a_normal(sorular),
        "A_muttefik": a_muttefik(sorular),
        "A_kaynaksiz": a_kaynaksiz(sorular),
        "B": b_karma(sorular),
        "gerekce": gerekce_testi(sorular),
    }


def pilot_plani(sorular: list[dict]) -> dict[str, list[Deneme]]:
    """Bölüm 8: kontrol ön testi (60 soru × 2 dil × 3 model) ve tutarlılık testi (10 soru × 5 tekrar)."""
    secilen = _turden_ilk(sorular, PILOT_TUTARLILIK_SORULARI)
    tutarlilik = [
        Deneme("pilot_tutarlilik", sid, "tr", 3, t, model=m, hata="kucuk", gorunurluk="acik")
        for m, sid, t in itertools.product(MODELLER, secilen, range(1, PILOT_TUTARLILIK_TEKRAR + 1))
    ]
    return {"pilot_kontrol": bilgi_testi(sorular, parca="pilot_kontrol"), "pilot_tutarlilik": tutarlilik}


# ---------------------------------------------------------------------------
# Bir denemenin promptu ve sınıflandırması için gereken bilgiler
# ---------------------------------------------------------------------------

def prompt_kosulu(deneme: Deneme, soru: dict, onceki_model_harfleri: list[str | None] = ()) -> dict:
    """
    asch.promptlar.kullanici_mesaji fonksiyonuna verilecek koşul parametrelerini döndürür.
    onceki_model_harfleri yalnızca B'de kullanılır: kendinden önce konuşan modellerin cevapları
    (okunamayan cevap None).
    """
    harf = soru["harfler"]
    if deneme.parca != "B" and deneme.k == 0:
        return {}  # tek başına: bilgi testi, pilot kontrol ve A: Normal k = 0
    yanlislar = [harf[deneme.hata]] * deneme.k if deneme.k > 0 else []  # B'de k = 0: suç ortağı yok
    if deneme.parca == "A_kaynaksiz":
        return {"kaynaksiz_cevaplar": yanlislar}
    if deneme.parca == "A_muttefik":
        grup = [harf["dogru"], *yanlislar] if deneme.muttefik_konumu == "basta" else [*yanlislar, harf["dogru"]]
    elif deneme.parca == "B":
        grup = [*yanlislar, *onceki_model_harfleri]
    else:
        grup = yanlislar
    return {"grup_cevaplari": grup, "gorunurluk": deneme.gorunurluk, "gerekce": deneme.gerekce}


def cogunluk_rolu(deneme: Deneme) -> str | None:
    """Sınıflandırma için çoğunluğun seçtiği şıkkın rolü; çoğunluk yoksa (k = 0) None."""
    return deneme.hata if deneme.k > 0 else None


def karistir(denemeler: list[Deneme], tohum: int = SIRA_TOHUMU) -> list[Deneme]:
    """Bir parçanın denemelerini sabit bir tohumla karıştırır (Bölüm 7: rastgele çalıştırma sırası)."""
    karisik = list(denemeler)
    random.Random(tohum).shuffle(karisik)
    return karisik


if __name__ == "__main__":
    import json
    from pathlib import Path

    sorular = json.loads(Path("veri/sorular.json").read_text(encoding="utf-8"))["sorular"]

    def tablo(baslik: str, plan: dict[str, list[Deneme]]) -> None:
        print(f"\n{baslik}")
        print(f"   {'Parça':<18}{'Deneme':>8}{'Çağrı':>9}")
        toplam_deneme = toplam_cagri = 0
        for parca, denemeler in plan.items():
            cagri = sum(d.cagri_sayisi for d in denemeler)
            toplam_deneme, toplam_cagri = toplam_deneme + len(denemeler), toplam_cagri + cagri
            print(f"   {parca:<18}{len(denemeler):>8,}{cagri:>9,}".replace(",", "."))
        print(f"   {'TOPLAM':<18}{toplam_deneme:>8,}{toplam_cagri:>9,}".replace(",", "."))

    tablo("Ana deney", ana_plan(sorular))
    tablo("Pilot", pilot_plani(sorular))