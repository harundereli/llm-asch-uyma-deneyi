"""
Prompt şablonu testleri (tasarım belgesi, Bölüm 5).

Bu testlerin ana fikri: koşullar arasındaki fark, tasarımda belirtilen satırlardan ibaret
olmalı. Başka hiçbir satır koşuldan koşula değişmemeli.

Çalıştırma:  python -m pytest
"""

import pytest

from asch.promptlar import DILLER, SYSTEM, kullanici_mesaji, mesajlar
from asch.sorular import soru_havuzu_olustur

SORULAR = [
    {"id": s.id, "tur": s.tur, "soru_tr": s.soru_tr, "soru_en": s.soru_en,
     "secenekler": {h: {"tr": o.tr, "en": o.en, "rol": o.rol} for h, o in s.secenekler.items()},
     "harfler": s.harfler}
    for s in soru_havuzu_olustur()
]
ORNEK = SORULAR[0]


def _farkli_satirlar(birinci: str, ikinci: str) -> set[str]:
    """İki metinden yalnızca birinde bulunan satırlar."""
    return set(birinci.splitlines()) ^ set(ikinci.splitlines())


@pytest.mark.parametrize("soru", SORULAR, ids=[s["id"] for s in SORULAR])
@pytest.mark.parametrize("dil", DILLER)
def test_her_soru_her_dilde_prompt_uretir(soru, dil):
    metin = kullanici_mesaji(soru, dil, grup_cevaplari=["A"] * 3)
    for harf in "ABCD":
        assert f"{harf}) {soru['secenekler'][harf][dil]}" in metin


@pytest.mark.parametrize("dil", DILLER)
def test_system_prompt_butun_kosullarda_ayni(dil):
    kosullar = [
        {},
        {"grup_cevaplari": ["A"] * 3},
        {"grup_cevaplari": ["A"] * 3, "gorunurluk": "gizli"},
    ]
    if dil == "tr":
        kosullar.append({"kaynaksiz_cevaplar": ["A"] * 3})
    for kosul in kosullar:
        assert mesajlar(ORNEK, dil, **kosul)[0] == {"role": "system", "content": SYSTEM[dil]}


def test_acik_ve_gizli_yalnizca_gorunurluk_cumlesinde_farkli():
    acik = kullanici_mesaji(ORNEK, "tr", grup_cevaplari=["A"] * 3, gorunurluk="acik")
    gizli = kullanici_mesaji(ORNEK, "tr", grup_cevaplari=["A"] * 3, gorunurluk="gizli")
    fark = _farkli_satirlar(acik, gizli)
    assert len(fark) == 2  # her iki taraftan birer satır: "Senin katılımcı numaran: 4. ..."
    assert all(satir.startswith("Senin katılımcı numaran: 4.") for satir in fark)


def test_muttefik_yalnizca_bir_satir_ekler():
    normal = kullanici_mesaji(ORNEK, "tr", grup_cevaplari=["A", "A"])
    muttefik = kullanici_mesaji(ORNEK, "tr", grup_cevaplari=["A", "A", "B"])
    assert _farkli_satirlar(normal, muttefik) == {
        "Katılımcı 3: B",
        "Senin katılımcı numaran: 3. Cevabın diğer katılımcılara gösterilecek.",
        "Senin katılımcı numaran: 4. Cevabın diğer katılımcılara gösterilecek.",
    }


@pytest.mark.parametrize("k", [1, 2, 3, 5])
def test_katilimci_numarasi_onceki_cevap_sayisinin_bir_fazlasi(k):
    metin = kullanici_mesaji(ORNEK, "tr", grup_cevaplari=["C"] * k)
    assert f"Senin katılımcı numaran: {k + 1}." in metin
    assert f"Katılımcı {k}: C" in metin
    assert f"Katılımcı {k + 1}:" not in metin


def test_cevap_vermeyen_model_dogru_gosterilir():
    metin = kullanici_mesaji(ORNEK, "tr", grup_cevaplari=["C", None, "B"])
    assert "Katılımcı 2: (cevap vermedi)" in metin
    assert "Senin katılımcı numaran: 4." in metin


def test_b_duzeneginde_ilk_model():
    metin = kullanici_mesaji(ORNEK, "tr", grup_cevaplari=[])
    assert "Gruptaki ilk cevabı sen vereceksin." in metin
    assert "Senin katılımcı numaran: 1." in metin
    assert "Katılımcı 1:" not in metin


@pytest.mark.parametrize("dil", DILLER)
def test_tek_basina_kosulunda_grup_izi_yok(dil):
    metin = kullanici_mesaji(ORNEK, dil)
    assert ("Bu soruyu tek başına cevaplıyorsun." if dil == "tr" else "You are answering this question on your own.") in metin
    for yasak in ("Katılımcı", "Participant", "numaran", "participant number"):
        assert yasak not in metin


def test_kaynaksiz_kosulda_konusmaci_ve_gorunurluk_yok():
    metin = kullanici_mesaji(ORNEK, "tr", kaynaksiz_cevaplar=["C"] * 3)
    assert metin.count("Cevap: C") == 3
    for yasak in ("Katılımcı", "numaran", "gösterilecek", "gösterilmeyecek"):
        assert yasak not in metin


def test_kosullar_ayni_gorev_ve_soru_ile_baslar_ayni_bicimle_biter():
    """Grup bloğu dışındaki her şey koşuldan koşula aynı kalmalı."""
    metinler = [
        kullanici_mesaji(ORNEK, "tr"),
        kullanici_mesaji(ORNEK, "tr", grup_cevaplari=["A"] * 3),
        kullanici_mesaji(ORNEK, "tr", kaynaksiz_cevaplar=["A"] * 3),
    ]
    bolumler = [m.split("\n\n") for m in metinler]
    assert len({tuple(b[:2]) for b in bolumler}) == 1   # görev açıklaması + soru
    assert len({b[-1] for b in bolumler}) == 1          # cevap biçimi


def test_gerekce_bicimi_once_cevabi_ister_ve_ornek_deger_icermez():
    metin = kullanici_mesaji(ORNEK, "tr", grup_cevaplari=["A"] * 3, gerekce=True)
    son = metin.split("\n\n")[-1]
    assert son.index('"cevap"') < son.index('"guven"') < son.index('"neden"')
    assert '"cevap": "' not in son  # tek bir örnek harf gösterilmemeli (çapa etkisi)


@pytest.mark.parametrize("hatali", [
    {"dil": "de"},
    {"dil": "tr", "grup_cevaplari": ["A"], "kaynaksiz_cevaplar": ["A"]},
    {"dil": "tr", "grup_cevaplari": ["A"], "gorunurluk": "yari"},
    {"dil": "en", "grup_cevaplari": ["A"], "gerekce": True},
])
def test_hatali_kullanim_reddedilir(hatali):
    dil = hatali.pop("dil")
    with pytest.raises(ValueError):
        kullanici_mesaji(ORNEK, dil, **hatali)