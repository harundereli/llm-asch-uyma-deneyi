"""
Çalıştırıcı testleri. Gerçek EVREN'e bağlanmaz; her senaryo "sahte EVREN" ile denenir:
hız sınırı, kaldığı yerden devam, 403'te durma, teknik hatalar, B grupları, paralel çalışma.

Her test kendi geçici klasörünü kullanır; gerçek veri dosyalarına dokunulmaz.

Çalıştırma:  python -m pytest
"""

import json
import re
import threading
import time
from collections import Counter
from pathlib import Path

import pytest

from asch.calistir import (
    ART_ARDA_HATA_SINIRI, Calistirici, HizSinirlayici, kalan_denemeler, tamamlanan_gruplar,
)
from asch.kayit import TEKNIK_HATA, HamKayit
from asch.model import CagriSonucu
from asch.plan import ana_plan

SORULAR = json.loads(Path("veri/sorular.json").read_text(encoding="utf-8"))["sorular"]
SORU = {s["id"]: s for s in SORULAR}
PLAN = ana_plan(SORULAR)


class SahteEvren:
    """
    asch.model.cagir yerine geçer.
    - Varsayılan cevap: gruptaki ilk katılımcının cevabını taklit eder; grup yoksa "A" der.
    - hatalar: {çağrı_no: hata_türü} → o çağrıda teknik ya da durduran bir hata döndürür.
    - ham: (model, mesaj, çağrı_no) → ham cevap metni; varsayılan cevabın yerine geçer.
    - ayar: CagriSonucu'nun başka alanlarını değiştirmek için (ör. düşünme tokenı).
    """

    def __init__(self, hatalar=None, ham=None, ayar=None, gecikme=0.0):
        self.hatalar = hatalar or {}
        self.ham = ham
        self.ayar = ayar or (lambda no: {})
        self.gecikme = gecikme
        self.cagrilar = []
        self._kilit = threading.Lock()
        self._aktif = Counter()          # şu an her modele giden istek sayısı
        self.en_fazla_aktif = Counter()  # her model için görülen en yüksek eşzamanlı istek sayısı

    def __call__(self, istemci, model, mesaj, *, temperature, max_tokens, bekle):
        with self._kilit:
            self.cagrilar.append({"model": model, "mesaj": mesaj, "temperature": temperature, "max_tokens": max_tokens})
            no = len(self.cagrilar)
            self._aktif[model] += 1
            self.en_fazla_aktif[model] = max(self.en_fazla_aktif[model], self._aktif[model])
        try:
            if self.gecikme:
                time.sleep(self.gecikme)
            return self._sonuc(model, mesaj, no)
        finally:
            with self._kilit:
                self._aktif[model] -= 1

    def _sonuc(self, model, mesaj, no):
        if no in self.hatalar:
            tur = self.hatalar[no]
            return CagriSonucu(istenen_model=model, hata_turu=tur, hata_mesaji="sahte hata",
                               deneme_sayisi=4 if tur == "RateLimitError" else 1, sure_sn=0.0)
        if self.ham:
            ham = self.ham(model, mesaj, no)
        else:
            eslesme = re.search(r"(?:Katılımcı|Participant) 1: ([ABCD])", mesaj[1]["content"])
            ham = json.dumps({"cevap": eslesme.group(1) if eslesme else "A"})
        alanlar = dict(istenen_model=model, donen_model=model, ham_cevap=ham, bitis_nedeni="stop",
                       girdi_token=150, cikti_token=8, dusunme_token=0, deneme_sayisi=1, sure_sn=0.0)
        alanlar.update(self.ayar(no))
        return CagriSonucu(**alanlar)


def _calistirici(tmp_path, sahte, paralel=1, **ek):
    return Calistirici(None, HamKayit(tmp_path / "ham.jsonl"), SORULAR, rpm=1e9, paralel=paralel,
                       cagri_fonksiyonu=sahte, yeniden_deneme_bekle=lambda s: None, cikti=lambda s: None, **ek)


def _satirlar(tmp_path):
    return HamKayit(tmp_path / "ham.jsonl").oku()[0]


# ---------------------------------------------------------------- hız sınırlayıcı

class SahteSaat:
    def __init__(self):
        self.t = 1000.0
        self.uykular = []

    def zaman(self):
        return self.t

    def uyu(self, sure):
        self.uykular.append(sure)
        self.t += sure


def test_hiz_sinirlayici_istekleri_esit_araliga_yayar():
    saat = SahteSaat()
    hiz = HizSinirlayici(60, zaman=saat.zaman, uyu=saat.uyu)  # dakikada 60 = saniyede 1
    baslangiclar = []
    for _ in range(5):
        hiz.bekle()
        baslangiclar.append(saat.t)
    assert baslangiclar == [1000.0, 1001.0, 1002.0, 1003.0, 1004.0]


def test_hiz_sinirlayici_yavaslar_ve_toparlanir():
    hiz = HizSinirlayici(60)
    for _ in range(10):
        hiz.yavasla()
    assert hiz.carpan == HizSinirlayici.EN_FAZLA_YAVASLAMA
    for _ in range(1000):
        hiz.toparla()
    assert hiz.carpan == 1.0


# ---------------------------------------------------------------- temel çalışma

def test_butun_denemeler_calisir_ve_dogru_siniflandirilir(tmp_path):
    denemeler = PLAN["A_normal"][:40]
    sahte = SahteEvren()
    assert _calistirici(tmp_path, sahte).calistir(denemeler, "A_normal")
    satirlar = _satirlar(tmp_path)
    assert len(satirlar) == len(sahte.cagrilar) == 40
    assert {s["deneme_id"] for s in satirlar} == {d.deneme_id for d in denemeler}
    for s in satirlar:
        if s["k"] > 0:  # sahte EVREN grubu taklit ediyor → hepsi uymuş olmalı
            assert s["harf"] == s["cogunluk_harfi"] and s["kategori"] == "uydu"


def test_kayit_satiri_gerekli_bilgileri_icerir(tmp_path):
    d = next(d for d in PLAN["A_normal"] if d.k == 3)
    _calistirici(tmp_path, SahteEvren()).calistir([d], "A_normal")
    satir = _satirlar(tmp_path)[0]
    for alan in ("zaman", "deneme_id", "durum", "parca", "soru_id", "tur", "dil", "k", "model",
                 "dogru_harf", "cogunluk_harfi", "temperature", "max_tokens", "extra_body",
                 "system_prompt", "user_prompt", "ham_cevap", "harf", "kategori",
                 "istenen_model", "donen_model", "girdi_token", "cikti_token", "dusunme_token"):
        assert alan in satir
    assert "Katılımcı 3:" in satir["user_prompt"]


def test_istek_ayarlari_denemeden_gelir(tmp_path):
    sahte = SahteEvren()
    _calistirici(tmp_path, sahte).calistir(PLAN["bilgi_testi"][:2] + PLAN["gerekce"][:2], "karisik")
    ayarlar = {(c["temperature"], c["max_tokens"]) for c in sahte.cagrilar}
    assert ayarlar == {(0.0, 50), (1.0, 300)}


# ---------------------------------------------------------------- kaldığı yerden devam

def test_kaldigi_yerden_devam_eder(tmp_path):
    denemeler = PLAN["A_normal"][:30]
    _calistirici(tmp_path, SahteEvren()).calistir(denemeler[:10], "A_normal")
    ikinci = SahteEvren()
    _calistirici(tmp_path, ikinci).calistir(denemeler, "A_normal")
    assert len(ikinci.cagrilar) == 20
    kimlikler = [s["deneme_id"] for s in _satirlar(tmp_path)]
    assert len(kimlikler) == len(set(kimlikler)) == 30


def test_tamamlanmis_parca_hic_cagri_yapmaz(tmp_path):
    denemeler = PLAN["A_kaynaksiz"][:5]
    _calistirici(tmp_path, SahteEvren()).calistir(denemeler, "x")
    ikinci = SahteEvren()
    assert _calistirici(tmp_path, ikinci).calistir(denemeler, "x")
    assert ikinci.cagrilar == []


# ---------------------------------------------------------------- hatalar ve durdurma

@pytest.mark.parametrize("hata", ["PermissionDeniedError", "AuthenticationError", "BadRequestError"])
def test_durduran_hata_calistirmayi_durdurur_sonra_devam_edilir(tmp_path, hata):
    denemeler = PLAN["A_normal"][:10]
    c = _calistirici(tmp_path, SahteEvren(hatalar={3: hata}))
    assert c.calistir(denemeler, "A_normal") is False
    assert hata in c.durma_nedeni
    assert len(_satirlar(tmp_path)) == 3  # 3. çağrıdan sonra yeni çağrı yapılmadı
    # Sorun giderildi (ör. şartlar onaylandı): aynı komut kaldığı yerden devam eder
    assert _calistirici(tmp_path, SahteEvren()).calistir(denemeler, "A_normal")
    tamam = {s["deneme_id"] for s in _satirlar(tmp_path) if s["durum"] != TEKNIK_HATA}
    assert tamam == {d.deneme_id for d in denemeler}


def test_teknik_hata_kaydedilir_calisma_surer_sonra_yeniden_denenir(tmp_path):
    denemeler = PLAN["A_normal"][:5]
    assert _calistirici(tmp_path, SahteEvren(hatalar={2: "RateLimitError"})).calistir(denemeler, "x")
    assert [s["durum"] for s in _satirlar(tmp_path)].count(TEKNIK_HATA) == 1
    ikinci = SahteEvren()
    _calistirici(tmp_path, ikinci).calistir(denemeler, "x")
    assert len(ikinci.cagrilar) == 1  # yalnızca hatalı olan yeniden denendi


def test_art_arda_teknik_hatalar_durdurur(tmp_path):
    denemeler = PLAN["A_normal"][:50]
    hatalar = {i: "InternalServerError" for i in range(1, 100)}
    c = _calistirici(tmp_path, SahteEvren(hatalar=hatalar))
    assert c.calistir(denemeler, "x") is False
    assert "Art arda" in c.durma_nedeni
    assert len(_satirlar(tmp_path)) == ART_ARDA_HATA_SINIRI


def test_dusunme_acik_gorunurse_durur(tmp_path):
    c = _calistirici(tmp_path, SahteEvren(ayar=lambda no: {"dusunme_token": 40} if no == 2 else {}))
    assert c.calistir(PLAN["A_normal"][:10], "x") is False
    assert "düşünme" in c.durma_nedeni


def test_model_adi_degisirse_durur(tmp_path):
    denemeler = [d for d in PLAN["A_normal"] if d.model == "gemma-4-31b"][:10]
    sahte = SahteEvren(ayar=lambda no: {"donen_model": "gemma-5"} if no == 4 else {})
    c = _calistirici(tmp_path, sahte)
    assert c.calistir(denemeler, "x") is False
    assert "model adı değişti" in c.durma_nedeni


def test_token_siniri_durdurur(tmp_path):
    c = _calistirici(tmp_path, SahteEvren(), token_siniri=1000)  # her çağrı 158 token
    assert c.calistir(PLAN["A_normal"][:50], "x") is False
    assert "token" in c.durma_nedeni
    assert len(_satirlar(tmp_path)) == 7  # 7 × 158 = 1.106 ≥ 1.000


# ---------------------------------------------------------------- B düzeneği

def _b(k):
    return next(d for d in PLAN["B"] if d.k == k)


def test_b_modeller_sirayla_ve_oncekileri_gorerek_cevaplar(tmp_path):
    d = _b(2)
    dogru = SORU[d.soru_id]["harfler"]["dogru"]
    cevaplar = {1: json.dumps({"cevap": dogru}), 2: "bozuk cevap", 3: json.dumps({"cevap": "A"})}
    sahte = SahteEvren(ham=lambda model, mesaj, no: cevaplar[no])
    assert _calistirici(tmp_path, sahte).calistir([d], "B")
    assert [c["model"] for c in sahte.cagrilar] == list(d.sira)
    ucuncu = sahte.cagrilar[2]["mesaj"][1]["content"]
    assert f"Katılımcı 3: {dogru}" in ucuncu            # 1. model doğru cevap verdi (müttefik)
    assert "Katılımcı 4: (cevap vermedi)" in ucuncu     # 2. modelin cevabı okunamadı
    assert "Senin katılımcı numaran: 5." in ucuncu
    satirlar = _satirlar(tmp_path)
    assert [s["konusma_sirasi"] for s in satirlar] == [1, 2, 3]
    assert satirlar[1]["durum"] == "sorunlu"
    assert len({s["calistirma_id"] for s in satirlar}) == 1
    assert tamamlanan_gruplar(satirlar) == {d.deneme_id}


def test_b_k0_ilk_model_grubun_ilki(tmp_path):
    sahte = SahteEvren()
    _calistirici(tmp_path, sahte).calistir([_b(0)], "B")
    assert "Gruptaki ilk cevabı sen vereceksin." in sahte.cagrilar[0]["mesaj"][1]["content"]


def test_b_yarim_kalan_grup_bastan_yapilir(tmp_path):
    d = _b(1)
    _calistirici(tmp_path, SahteEvren(hatalar={2: "RateLimitError"})).calistir([d], "B")
    assert tamamlanan_gruplar(_satirlar(tmp_path)) == set()
    ikinci = SahteEvren()
    _calistirici(tmp_path, ikinci).calistir([d], "B")
    assert len(ikinci.cagrilar) == 3  # grup baştan
    satirlar = _satirlar(tmp_path)
    assert tamamlanan_gruplar(satirlar) == {d.deneme_id}
    assert len({s["calistirma_id"] for s in satirlar}) == 2


def test_b_durdurulursa_grup_yarida_kalir_ve_bastan_yapilir(tmp_path):
    d = _b(3)
    c = _calistirici(tmp_path, SahteEvren(hatalar={2: "PermissionDeniedError"}))
    assert c.calistir([d], "B") is False
    assert len(_satirlar(tmp_path)) == 2
    assert kalan_denemeler([d], _satirlar(tmp_path)) == [d]


# ---------------------------------------------------------------- paralel çalışma

def test_paralel_calismada_her_deneme_bir_kez_yapilir(tmp_path):
    denemeler = PLAN["A_normal"][:150] + PLAN["B"][:20]
    sahte = SahteEvren(gecikme=0.001)
    assert _calistirici(tmp_path, sahte, paralel=8).calistir(denemeler, "karisik")
    satirlar = _satirlar(tmp_path)
    assert len(sahte.cagrilar) == len(satirlar) == 150 + 20 * 3
    assert len({s["deneme_id"] for s in satirlar}) == len(satirlar)
    assert kalan_denemeler(denemeler, satirlar) == []


class SahteToplamEsz(SahteEvren):
    """Bütün modellere giden toplam eşzamanlı istek sayısını da ölçer."""

    def __init__(self, **ek):
        super().__init__(**ek)
        self._toplam = 0
        self.en_fazla_toplam = 0
        self._toplam_kilit = threading.Lock()

    def __call__(self, *a, **k):
        with self._toplam_kilit:
            self._toplam += 1
            self.en_fazla_toplam = max(self.en_fazla_toplam, self._toplam)
        try:
            return super().__call__(*a, **k)
        finally:
            with self._toplam_kilit:
                self._toplam -= 1


@pytest.mark.parametrize("sinir", [1, 2, 3])
def test_ayni_modele_sinirdan_fazla_eszamanli_istek_gitmez(tmp_path, sinir):
    denemeler = PLAN["A_normal"][:120] + PLAN["B"][:10]
    sahte = SahteEvren(gecikme=0.01)
    assert _calistirici(tmp_path, sahte, paralel=16, model_esz=sinir).calistir(denemeler, "karisik")
    assert len(_satirlar(tmp_path)) == 120 + 10 * 3
    assert max(sahte.en_fazla_aktif.values()) == sinir   # sınıra ulaşılıyor ama asla aşılmıyor
    assert set(sahte.en_fazla_aktif) == {"deepseek-v4.1-flash", "qwen3.8-flash-next", "gemma-4-31b"}


def test_bir_modelin_siniri_digerlerini_durdurmaz(tmp_path):
    """Her modele aynı anda en fazla 1 istek gitse de farklı modellere aynı anda istek gidebilmeli."""
    modeller = ("deepseek-v4.1-flash", "qwen3.8-flash-next", "gemma-4-31b")
    denemeler = [d for m in modeller for d in [x for x in PLAN["A_normal"] if x.model == m][:30]]
    sahte = SahteToplamEsz(gecikme=0.01)
    _calistirici(tmp_path, sahte, paralel=16, model_esz=1).calistir(denemeler, "x")
    assert max(sahte.en_fazla_aktif.values()) == 1
    assert sahte.en_fazla_toplam >= 2