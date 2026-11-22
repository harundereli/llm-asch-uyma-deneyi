"""
Çalışma 2 testleri: plan, prompt, cevap ayrıştırma, API çağrısı ve çalıştırıcı. Gerçek EVREN'e bağlanmaz.

Çalıştırma:  python -m pytest testler/test_calisma2.py
"""

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import openai
import pytest

from asch.calisma2 import (
    CEVAP_TALEBI, PARCA, SYSTEM, Calistirici2, cagir_serbest, harf_ayikla, mesajlar2, plan,
)
from asch.calistir import Calistirici
from asch.kayit import HamKayit
from asch.model import MODELLER, CagriSonucu, cagir
from asch.plan import Deneme
from testler.test_model import SahteIstemci, _basarili_yanit, _durum_hatasi

SORULAR = json.loads(Path("veri/sorular.json").read_text(encoding="utf-8"))["sorular"]
SORU = {s["id"]: s for s in SORULAR}
PLAN = plan(SORULAR)
CIZGI_IDLERI = {s["id"] for s in SORULAR if s["tur"] == "cizgi"}


# ---------------------------------------------------------------- plan

def test_toplam_1080_deneme_ve_her_biri_tek_cagri():
    assert len(PLAN) == 6 * 20 * 3 * 3 == 1080
    assert all(d.cagri_sayisi == 1 for d in PLAN)


def test_deneme_kimlikleri_benzersiz_ve_calisma1_ile_cakismiyor():
    idler = [d.deneme_id for d in PLAN]
    assert len(set(idler)) == len(idler)
    assert all(i.startswith(f"{PARCA}|") for i in idler)


def test_yalnizca_cizgi_sorulari_hepsi():
    assert {d.soru_id for d in PLAN} == CIZGI_IDLERI and len(CIZGI_IDLERI) == 20


def test_her_hucre_dengeli():
    hucreler = Counter((d.model, d.k) for d in PLAN)
    assert set(hucreler) == {(m, k) for m in MODELLER for k in range(6)}
    assert set(hucreler.values()) == {20 * 3}
    assert {d.tekrar for d in PLAN} == {1, 2, 3}


def test_kosul_ayarlari():
    for d in PLAN:
        assert d.dil == "tr" and d.temperature == 1.0 and d.max_tokens == 50 and not d.gerekce
        assert d.gorunurluk is None and d.muttefik_konumu is None and d.sira is None
        assert d.hata == ("kucuk" if d.k else None)


# ---------------------------------------------------------------- prompt

def _ornek(k, sid="CZG-07"):
    return Deneme(PARCA, sid, "tr", k, model=MODELLER[0], hata="kucuk" if k else None), SORU[sid]


def test_prompt_prototip_bicimi_k3():
    system, user = (m["content"] for m in mesajlar2(*_ornek(3)))
    assert system == "Sen bir grup deneyine katılan bir kişisin."
    assert user == (
        "Referans çizgi 15 cm. Hangisi onunla aynı uzunlukta? A) 15 cm  B) 16 cm  C) 9 cm  D) 19 cm\n"
        "\n"
        "Diğer katılımcıların cevapları:\n"
        "- Ajan_1: B\n"
        "- Ajan_2: B\n"
        "- Ajan_3: B\n"
        "\n"
        "Senin cevabın nedir? Sadece harfi yaz (A, B, C veya D)."
    )


def test_prompt_k0_grup_bolumu_yok():
    user = mesajlar2(*_ornek(0))[1]["content"]
    assert user == (
        "Referans çizgi 15 cm. Hangisi onunla aynı uzunlukta? A) 15 cm  B) 16 cm  C) 9 cm  D) 19 cm\n"
        "\n"
        "Senin cevabın nedir? Sadece harfi yaz (A, B, C veya D)."
    )


@pytest.mark.parametrize("k", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("sid", sorted(CIZGI_IDLERI))
def test_k_ajanin_hepsi_kucuk_yanlis(k, sid):
    deneme, soru = _ornek(k, sid)
    user = mesajlar2(deneme, soru)[1]["content"]
    yanlis = soru["harfler"]["kucuk"]
    ajanlar = [s for s in user.splitlines() if s.startswith("- Ajan_")]
    assert ajanlar == [f"- Ajan_{no}: {yanlis}" for no in range(1, k + 1)]


@pytest.mark.parametrize("sid", sorted(CIZGI_IDLERI))
def test_her_cizgi_sorusu_dogru_donusturuluyor(sid):
    soru = SORU[sid]
    ilk = mesajlar2(*_ornek(0, sid))[1]["content"].splitlines()[0]
    uzunluk = soru["soru_tr"].removeprefix("Referans çizgi: ")
    assert ilk.startswith(f"Referans çizgi {uzunluk}. Hangisi onunla aynı uzunlukta? ")
    for h in "ABCD":
        assert f"{h}) {soru['secenekler'][h]['tr']}" in ilk


def test_calisma1_ogeleri_yok():
    system, user = (m["content"] for m in mesajlar2(*_ornek(5)))
    for ifade in ("Bu görevde", "gerekiyor", "Katılımcı", "katılımcı numaran", "gösterilecek",
                  "cevap\"", "{", "Her soruda"):
        assert ifade not in system + user
    assert user.endswith(CEVAP_TALEBI) and system == SYSTEM


# ---------------------------------------------------------------- harf ayıklama

@pytest.mark.parametrize("ham, harf", [
    ("B", "B"), ("b", "B"), (" B\n", "B"), ("B.", "B"), ("(B)", "B"), ("B)", "B"), ("b)", "B"),
    ("B) 16 cm", "B"), ("Cevabım B.", "B"), ("Cevap: B", "B"), ("**B**", "B"), ('{"cevap": "B"}', "B"),
    ("D", "D"), ("Bence doğru cevap A şıkkı.", "A"),
])
def test_harf_ayiklanir(ham, harf):
    a = harf_ayikla(ham)
    assert a.harf == harf and a.sorun is None


@pytest.mark.parametrize("ham, sorun", [
    (None, "bos"), ("", "bos"), ("   ", "bos"),
    ("A veya B", "birden_fazla_sik"), ("A) 15 cm  B) 16 cm", "birden_fazla_sik"),
    ("E", "bicim_hatasi"), ("15 cm", "bicim_hatasi"), ("bilmiyorum", "bicim_hatasi"),
    ("Üzgünüm, cevap veremem.", "reddetme"),
])
def test_sorunlu_cevaplar(ham, sorun):
    a = harf_ayikla(ham)
    assert a.harf is None and a.sorun == sorun


def test_kelime_icindeki_harfler_sayilmaz():
    # "Ajan_1", "cm", "Bence", "Doğru" gibi kelimelerin içindeki büyük harfler şık sayılmaz.
    assert harf_ayikla("Ajan_1 ile aynı: C").harf == "C"
    assert harf_ayikla("Doğru cevap D").harf == "D"
    assert harf_ayikla("BU SORUDA B").harf == "B"  # "SORUDA"nın sonundaki A sayılmaz


# ---------------------------------------------------------------- API çağrısı

def _iki_cagri(*sonuclar):
    """Aynı sahte yanıtlarla Çalışma 1'in `cagir` ve Çalışma 2'nin `cagir_serbest` fonksiyonunu çalıştırır."""
    sonuc = []
    for fonksiyon in (cagir, cagir_serbest):
        istemci, beklemeler = SahteIstemci(*sonuclar), []
        s = fonksiyon(istemci, "deepseek-v4.1-flash", [{"role": "user", "content": "x"}],
                      temperature=1.0, max_tokens=50, bekle=beklemeler.append)
        s.sure_sn = 0
        sonuc.append((s, istemci.istekler, beklemeler))
    return sonuc


def test_istek_json_zorunlulugu_olmadan_gider_gerisi_ayni():
    (s1, i1, _), (s2, i2, _) = _iki_cagri(_basarili_yanit("B"))
    assert "response_format" not in i2[0]
    assert {k: v for k, v in i1[0].items() if k != "response_format"} == i2[0]
    assert asdict(s1) == asdict(s2) and s2.ham_cevap == "B"


@pytest.mark.parametrize("sonuclar", [
    [_durum_hatasi(openai.RateLimitError, 429), _basarili_yanit("B")],
    [_durum_hatasi(openai.InternalServerError, 503)] * 4,
    [_durum_hatasi(openai.AuthenticationError, 401)],
    [openai.APITimeoutError(request=None), _basarili_yanit("C")],
])
def test_yeniden_deneme_ve_hatalar_calisma1_ile_ayni(sonuclar):
    (s1, i1, b1), (s2, i2, b2) = _iki_cagri(*sonuclar)
    assert asdict(s1) == asdict(s2) and b1 == b2 and len(i1) == len(i2)


# ---------------------------------------------------------------- çalıştırıcı

class SahteEvren:
    def __init__(self, cevap="B"):
        self.cagrilar, self.cevap = [], cevap

    def __call__(self, istemci, model, mesaj, *, temperature, max_tokens, bekle):
        self.cagrilar.append(mesaj)
        return CagriSonucu(istenen_model=model, donen_model=model, ham_cevap=self.cevap,
                           bitis_nedeni="stop", girdi_token=90, cikti_token=1, dusunme_token=0,
                           deneme_sayisi=1, sure_sn=0.0)


def _calistir(tmp_path, denemeler, cevap="B"):
    sahte = SahteEvren(cevap)
    c = Calistirici2(None, HamKayit(tmp_path / "c2.jsonl"), SORULAR, rpm=1e9, paralel=4,
                     cagri_fonksiyonu=sahte, yeniden_deneme_bekle=lambda s: None, cikti=lambda s: None)
    assert c.calistir(denemeler, PARCA)
    return sahte, HamKayit(tmp_path / "c2.jsonl").oku()[0]


def test_varsayilan_cagri_fonksiyonu_json_siz():
    c = Calistirici2(None, None, SORULAR)
    assert c._cagir is cagir_serbest


def test_calistirici_mesajlar_kayit_ve_siniflandirma(tmp_path):
    secilen = [d for d in PLAN if d.model == MODELLER[0] and d.soru_id == "CZG-07"]
    assert len(secilen) == 18
    sahte, satirlar = _calistir(tmp_path, secilen, cevap="B")  # CZG-07'de B = küçük yanlış
    assert len(satirlar) == 18 == len(sahte.cagrilar)
    beklenen = {d.deneme_id: mesajlar2(d, SORU[d.soru_id]) for d in secilen}
    for s in satirlar:
        mesaj = beklenen[s["deneme_id"]]
        assert (s["system_prompt"], s["user_prompt"]) == (mesaj[0]["content"], mesaj[1]["content"])
        assert s["parca"] == PARCA and s["response_format"] is None and s["harf"] == "B"
        assert s["durum"] == "tamam"
        if s["k"]:
            assert (s["kategori"], s["cogunluk_harfi"]) == ("uydu", "B")
        else:
            assert (s["kategori"], s["alt_kategori"], s["cogunluk_harfi"]) == ("diger", "kucuk", None)


def test_kayit_alanlari_calisma1_ile_ayni(tmp_path):
    # Çalışma 1'in çalıştırıcısıyla aynı denemenin kaydı: alan adları birebir aynı olmalı.
    deneme = Deneme("A_normal", "CZG-07", "tr", 3, model=MODELLER[0], hata="kucuk", gorunurluk="acik")
    c1 = Calistirici(None, HamKayit(tmp_path / "c1.jsonl"), SORULAR, rpm=1e9,
                     cagri_fonksiyonu=SahteEvren('{"cevap": "B"}'), cikti=lambda s: None)
    assert c1.calistir([deneme], "A_normal")
    _, c2 = _calistir(tmp_path, PLAN[:1])
    s1 = HamKayit(tmp_path / "c1.jsonl").oku()[0][0]
    assert list(s1) == list(c2[0])


def test_sorunlu_cevap_kaydedilir(tmp_path):
    _, satirlar = _calistir(tmp_path, PLAN[:5], cevap="A veya B")
    assert all(s["durum"] == "sorunlu" and s["kategori"] == "sorunlu" for s in satirlar)
    assert all(s["sorun"] == "birden_fazla_sik" and s["ham_cevap"] == "A veya B" for s in satirlar)


def test_kaldigi_yerden_devam(tmp_path):
    secilen = PLAN[:30]
    _calistir(tmp_path, secilen[:10])
    sahte, satirlar = _calistir(tmp_path, secilen)
    assert len(sahte.cagrilar) == 20 and len(satirlar) == 30


# ---------------------------------------------------------------- format kontrolü

def test_format_kontrolu_ayri_dosyaya_yazar_ve_asil_kayda_dokunmaz(tmp_path, monkeypatch, capsys):
    import asch.calisma2 as c2
    sahte = SahteEvren("B")
    monkeypatch.setattr(c2, "cagir_serbest", sahte)
    monkeypatch.setattr(c2, "istemci_olustur", lambda: None)
    monkeypatch.setattr(c2, "calisma1_kalan", lambda sorular: 0)
    monkeypatch.setattr(c2, "KAYIT_DOSYASI", tmp_path / "calisma2.jsonl")
    monkeypatch.setattr(c2, "FORMAT_KONTROL_DOSYASI", tmp_path / "format.jsonl")
    assert c2.main(["--format-kontrol", "--rpm", "1e9"]) == 0
    satirlar = HamKayit(tmp_path / "format.jsonl").oku()[0]
    assert len(satirlar) == len(sahte.cagrilar) == 6
    assert {(s["model"], s["k"]) for s in satirlar} == {(m, k) for m in MODELLER for k in (0, 5)}
    assert all(s["parca"] == c2.FORMAT_KONTROL_PARCA and s["soru_id"] == "CZG-01" for s in satirlar)
    assert not (tmp_path / "calisma2.jsonl").exists()
    assert "ham='B'" in capsys.readouterr().out


def test_format_kontrolu_kimlikleri_asil_planla_cakismiyor():
    from asch.calisma2 import format_kontrol_plani
    assert not {d.deneme_id for d in format_kontrol_plani()} & {d.deneme_id for d in PLAN}


def test_calisma1_bitmeden_calismaz(tmp_path, monkeypatch):
    import asch.calisma2 as c2
    monkeypatch.setattr(c2, "calisma1_kalan", lambda sorular: 5)
    monkeypatch.setattr(c2, "istemci_olustur", lambda: pytest.fail("API'ye bağlanmamalıydı"))
    monkeypatch.setattr(c2, "KAYIT_DOSYASI", tmp_path / "calisma2.jsonl")
    assert c2.main([]) == 1 and c2.main(["--format-kontrol"]) == 1