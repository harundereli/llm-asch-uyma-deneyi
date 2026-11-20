"""
Soru havuzu testleri (tasarım belgesi, Bölüm 3).

Çalıştırma:  python -m pytest
"""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from asch.sorular import CIKTI_DOSYASI, TOHUM, dogrula, soru_havuzu_olustur


def test_havuz_tasarim_kurallarina_uyar():
    dogrula(soru_havuzu_olustur())


def test_ayni_tohum_ayni_sorulari_uretir():
    birinci = [asdict(s) for s in soru_havuzu_olustur()]
    ikinci = [asdict(s) for s in soru_havuzu_olustur()]
    assert birinci == ikinci


def test_kayitli_dosya_kodun_urettigiyle_ayni():
    """veri/sorular.json elle değiştirilmiş ya da kod değişip dosya yenilenmemişse yakalar."""
    kayitli = json.loads(Path(CIKTI_DOSYASI).read_text(encoding="utf-8"))
    assert kayitli["tohum"] == TOHUM
    assert kayitli["sorular"] == [asdict(s) for s in soru_havuzu_olustur()]


@pytest.mark.parametrize("tohum", range(50))
def test_farkli_tohumlarda_da_kurallara_uyar(tohum):
    dogrula(soru_havuzu_olustur(tohum))


def test_dogrulayici_bozuk_soruyu_yakalar():
    sorular = soru_havuzu_olustur()
    aritmetik = next(s for s in sorular if s.tur == "aritmetik")
    aritmetik.secenekler[aritmetik.harfler["dogru"]].tr = "999"
    with pytest.raises(AssertionError):
        dogrula(sorular)


def test_dogrulayici_dengesiz_konumu_yakalar():
    sorular = soru_havuzu_olustur()
    cizgi = next(s for s in sorular if s.tur == "cizgi")
    # Doğru şık ile küçük yanlışın yerini değiştir: konum dengesi bozulur.
    d, k = cizgi.harfler["dogru"], cizgi.harfler["kucuk"]
    cizgi.secenekler[d], cizgi.secenekler[k] = cizgi.secenekler[k], cizgi.secenekler[d]
    cizgi.harfler["dogru"], cizgi.harfler["kucuk"] = k, d
    with pytest.raises(AssertionError):
        dogrula(sorular)