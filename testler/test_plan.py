"""
Deney planı testleri: plan, tasarım belgesindeki (Bölüm 4, 7, 8) sayılarla ve dengeyle birebir uyuşmalı.

Çalıştırma:  python -m pytest
"""

import itertools
import json
from collections import Counter
from pathlib import Path

import pytest

from asch.model import MODELLER
from asch.plan import (
    K_GRUP, K_HEPSI, Deneme, ana_plan, cogunluk_rolu, karistir, pilot_plani, prompt_kosulu,
)
from asch.promptlar import kullanici_mesaji

SORULAR = json.loads(Path("veri/sorular.json").read_text(encoding="utf-8"))["sorular"]
SORU = {s["id"]: s for s in SORULAR}
PLAN = ana_plan(SORULAR)
PILOT = pilot_plani(SORULAR)

# Tasarım belgesi, Bölüm 7'deki tablo
BEKLENEN_CAGRI = {
    "bilgi_testi": 360,
    "A_normal": 720 + 11_520,
    "A_muttefik": 2_880,
    "A_kaynaksiz": 1_440,
    "B": 10_800,
    "gerekce": 180,
}


def _cagri(denemeler):
    return sum(d.cagri_sayisi for d in denemeler)


# ---------------------------------------------------------------- sayılar

@pytest.mark.parametrize("parca, beklenen", BEKLENEN_CAGRI.items())
def test_cagri_sayilari_tasarim_tablosuyla_ayni(parca, beklenen):
    assert _cagri(PLAN[parca]) == beklenen


def test_toplam_cagri_sayisi():
    assert sum(_cagri(d) for d in PLAN.values()) == 27_900  # + pilot (~600) ≈ tasarımdaki ~28.500


def test_pilot_cagri_sayilari():
    assert _cagri(PILOT["pilot_kontrol"]) == 360      # 60 soru × 2 dil × 3 model
    assert _cagri(PILOT["pilot_tutarlilik"]) == 150   # 10 soru × 5 tekrar × 3 model


def test_parcalar_tasarimdaki_calistirma_sirasinda():
    assert list(PLAN) == ["bilgi_testi", "A_normal", "A_muttefik", "A_kaynaksiz", "B", "gerekce"]


def test_deneme_kimlikleri_benzersiz():
    butun = [d.deneme_id for denemeler in [*PLAN.values(), *PILOT.values()] for d in denemeler]
    assert len(butun) == len(set(butun))


# ---------------------------------------------------------------- denge: her hücrede 60 soru × 2 tekrar

def _hucreler(denemeler, *alanlar):
    return Counter(tuple(getattr(d, a) for a in alanlar) for d in denemeler)


def test_a_normal_her_hucrede_120_deneme():
    hucre = _hucreler(PLAN["A_normal"], "model", "dil", "k", "hata", "gorunurluk")
    assert len(hucre) == 3 * 2 * (1 + 4 * 2 * 2)       # model × dil × (k=0 + k × hata × görünürlük)
    assert set(hucre.values()) == {60 * 2}


@pytest.mark.parametrize("parca, alanlar, hucre_sayisi", [
    ("A_muttefik", ("model", "k", "muttefik_konumu"), 3 * 4 * 2),
    ("A_kaynaksiz", ("model", "k"), 3 * 4),
    ("B", ("sira", "k"), 6 * 5),
])
def test_diger_parcalarda_her_hucrede_120_deneme(parca, alanlar, hucre_sayisi):
    hucre = _hucreler(PLAN[parca], *alanlar)
    assert len(hucre) == hucre_sayisi
    assert set(hucre.values()) == {60 * 2}


def test_b_her_model_her_sirada_esit_sayida():
    sayim = Counter((model, i) for d in PLAN["B"] for i, model in enumerate(d.sira))
    assert len(sayim) == 3 * 3 and len(set(sayim.values())) == 1


def test_b_butun_siralamalar_var():
    assert {d.sira for d in PLAN["B"]} == set(itertools.permutations(MODELLER))


def test_sabit_kosullar_dogru():
    for d in PLAN["A_muttefik"] + PLAN["A_kaynaksiz"] + PLAN["B"] + PLAN["gerekce"]:
        assert d.dil == "tr"
        assert d.hata == ("kucuk" if d.k > 0 else None)
    for d in PLAN["A_muttefik"] + PLAN["B"]:
        assert d.gorunurluk == "acik"
    assert all(d.gorunurluk is None for d in PLAN["A_kaynaksiz"])
    assert {d.k for d in PLAN["B"]} == set(K_HEPSI) and {d.k for d in PLAN["A_muttefik"]} == set(K_GRUP)


def test_gerekce_her_turden_10_soru():
    turler = Counter(SORU[sid]["tur"] for sid in {d.soru_id for d in PLAN["gerekce"]})
    assert turler == {"cizgi": 10, "bilgi": 10, "aritmetik": 10}
    assert all(d.gerekce and d.k == 3 for d in PLAN["gerekce"])


def test_temperature_ve_max_tokens():
    assert all(d.temperature == 0.0 for d in PLAN["bilgi_testi"] + PILOT["pilot_kontrol"])
    for parca in ("A_normal", "A_muttefik", "A_kaynaksiz", "B", "gerekce"):
        assert all(d.temperature == 1.0 for d in PLAN[parca])
    assert all(d.max_tokens == 300 for d in PLAN["gerekce"])
    assert all(d.max_tokens == 50 for p in ("bilgi_testi", "A_normal", "B") for d in PLAN[p])


# ---------------------------------------------------------------- prompt koşulları

def _ornek(parca, **alanlar):
    return next(d for d in PLAN[parca] if all(getattr(d, a) == v for a, v in alanlar.items()))


def test_a_normal_grup_dogru_harfle_kurulur():
    d = _ornek("A_normal", k=3, hata="buyuk", gorunurluk="gizli")
    harf = SORU[d.soru_id]["harfler"]
    assert prompt_kosulu(d, SORU[d.soru_id]) == {
        "grup_cevaplari": [harf["buyuk"]] * 3, "gorunurluk": "gizli", "gerekce": False}


def test_tek_basina_kosullarda_grup_yok():
    for d in (_ornek("A_normal", k=0), PLAN["bilgi_testi"][0], PILOT["pilot_kontrol"][0]):
        assert prompt_kosulu(d, SORU[d.soru_id]) == {}


@pytest.mark.parametrize("konum", ["basta", "sonda"])
def test_muttefik_konumu(konum):
    d = _ornek("A_muttefik", k=2, muttefik_konumu=konum)
    harf = SORU[d.soru_id]["harfler"]
    grup = prompt_kosulu(d, SORU[d.soru_id])["grup_cevaplari"]
    beklenen = [harf["dogru"], harf["kucuk"], harf["kucuk"]] if konum == "basta" else \
               [harf["kucuk"], harf["kucuk"], harf["dogru"]]
    assert grup == beklenen


def test_kaynaksiz_kosulda_konusmaci_yok():
    d = _ornek("A_kaynaksiz", k=5)
    assert prompt_kosulu(d, SORU[d.soru_id]) == {"kaynaksiz_cevaplar": [SORU[d.soru_id]["harfler"]["kucuk"]] * 5}


def test_b_onceki_modellerin_cevaplari_eklenir():
    d = _ornek("B", k=2)
    harf = SORU[d.soru_id]["harfler"]
    kosul = prompt_kosulu(d, SORU[d.soru_id], ["A", None])
    assert kosul["grup_cevaplari"] == [harf["kucuk"], harf["kucuk"], "A", None]


def test_b_k0_ilk_model_bos_grup():
    d = _ornek("B", k=0)
    assert prompt_kosulu(d, SORU[d.soru_id])["grup_cevaplari"] == []


@pytest.mark.parametrize("parca, k, beklenen", [
    ("A_normal", 0, None), ("A_normal", 3, "kucuk"), ("A_kaynaksiz", 2, "kucuk"),
    ("B", 0, None), ("B", 1, "kucuk"), ("bilgi_testi", 0, None),
])
def test_cogunluk_rolu(parca, k, beklenen):
    assert cogunluk_rolu(_ornek(parca, k=k)) == beklenen


def test_butun_denemeler_icin_prompt_uretilebilir():
    """27.900 çağrının her birinin promptu hatasız oluşturulabilmeli."""
    for denemeler in [*PLAN.values(), *PILOT.values()]:
        for d in denemeler:
            soru = SORU[d.soru_id]
            onceki = []
            for _ in range(d.cagri_sayisi):  # B'de her model kendinden öncekilerin cevabını görür
                kullanici_mesaji(soru, d.dil, **prompt_kosulu(d, soru, onceki))
                onceki.append("A")


# ---------------------------------------------------------------- karıştırma

def test_karistirma_tekrarlanabilir_ve_eleman_kaybetmez():
    denemeler = PLAN["A_normal"]
    birinci, ikinci = karistir(denemeler), karistir(denemeler)
    assert birinci == ikinci
    assert birinci != denemeler
    assert Counter(birinci) == Counter(denemeler)


def test_deneme_kimligi_okunabilir():
    d = Deneme("A_muttefik", "BLG-01", "tr", 2, 1, model="gemma-4-31b",
               hata="kucuk", gorunurluk="acik", muttefik_konumu="basta")
    assert d.deneme_id == "A_muttefik|gemma-4-31b|BLG-01|tr|k2|kucuk|acik|basta|t1"