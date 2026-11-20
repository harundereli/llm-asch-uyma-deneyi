"""
Ham veri kaydı testleri (tasarım belgesi, Bölüm 6.2).

Her test kendi geçici klasörünü kullanır (pytest'in tmp_path'i); gerçek veri dosyalarına dokunulmaz.

Çalıştırma:  python -m pytest
"""

import json
import threading

import pytest

from asch.kayit import TEKNIK_HATA, HamKayit, simdi


def _satir(deneme_id, durum="tamam", **ek):
    return {"deneme_id": deneme_id, "durum": durum, **ek}


def test_eklenen_satirlar_okunur(tmp_path):
    kayit = HamKayit(tmp_path / "ham.jsonl")
    kayit.ekle(_satir("d1", ham_cevap='{"cevap": "B"}'))
    kayit.ekle(_satir("d2", ham_cevap="Üzgünüm, cevaplayamam."))
    satirlar, bozuk = kayit.oku()
    assert bozuk == 0
    assert [s["deneme_id"] for s in satirlar] == ["d1", "d2"]
    assert satirlar[1]["ham_cevap"] == "Üzgünüm, cevaplayamam."  # Türkçe karakterler korunur


def test_yalnizca_ekleme_yapilir_eski_satirlar_degismez(tmp_path):
    dosya = tmp_path / "ham.jsonl"
    kayit = HamKayit(dosya)
    kayit.ekle(_satir("d1"))
    onceki = dosya.read_bytes()
    kayit.ekle(_satir("d2"))
    assert dosya.read_bytes().startswith(onceki)


def test_yeni_nesne_ayni_dosyaya_devam_eder(tmp_path):
    dosya = tmp_path / "ham.jsonl"
    HamKayit(dosya).ekle(_satir("d1"))
    HamKayit(dosya).ekle(_satir("d2"))  # programın yeniden başlatılması gibi
    assert [s["deneme_id"] for s in HamKayit(dosya).oku()[0]] == ["d1", "d2"]


def test_tamamlananlar_teknik_hatalari_icermez(tmp_path):
    kayit = HamKayit(tmp_path / "ham.jsonl")
    kayit.ekle(_satir("d1", "tamam"))
    kayit.ekle(_satir("d2", TEKNIK_HATA))
    kayit.ekle(_satir("d3", "sorunlu"))     # okunamayan cevap da bir sonuçtur; tekrar sorulmaz
    assert kayit.tamamlanan_idler() == {"d1", "d3"}


def test_teknik_hatadan_sonra_basarili_deneme_tamamlanmis_sayilir(tmp_path):
    kayit = HamKayit(tmp_path / "ham.jsonl")
    kayit.ekle(_satir("d1", TEKNIK_HATA))
    kayit.ekle(_satir("d1", "tamam"))
    assert kayit.tamamlanan_idler() == {"d1"}
    assert len(kayit.oku()[0]) == 2  # hata satırı silinmez


def test_yarida_kalmis_satir_sonraki_kaydi_bozmaz(tmp_path):
    """Elektrik kesilip son satır yarım kaldıysa: yarım satır bozuk sayılır, yeni satır sağlam yazılır."""
    dosya = tmp_path / "ham.jsonl"
    HamKayit(dosya).ekle(_satir("d1"))
    with open(dosya, "a", encoding="utf-8") as f:
        f.write('{"deneme_id": "d2", "durum": "ta')  # yarım satır, satır sonu yok
    kayit = HamKayit(dosya)
    kayit.ekle(_satir("d3"))
    satirlar, bozuk = kayit.oku()
    assert [s["deneme_id"] for s in satirlar] == ["d1", "d3"]
    assert bozuk == 1
    assert kayit.tamamlanan_idler() == {"d1", "d3"}  # d2 yeniden denenecek


def test_dosya_yoksa_bos_doner(tmp_path):
    kayit = HamKayit(tmp_path / "yok" / "ham.jsonl")
    assert kayit.oku() == ([], 0)
    assert kayit.tamamlanan_idler() == set()


def test_paralel_yazma_satirlari_karistirmaz(tmp_path):
    kayit = HamKayit(tmp_path / "ham.jsonl")
    uzun_metin = "x" * 5000  # satırların iç içe geçmesini görünür kılmak için uzun
    is_parcaciklari = [
        threading.Thread(target=kayit.ekle, args=(_satir(f"d{i}", metin=uzun_metin),))
        for i in range(200)
    ]
    for t in is_parcaciklari:
        t.start()
    for t in is_parcaciklari:
        t.join()
    satirlar, bozuk = kayit.oku()
    assert bozuk == 0
    assert {s["deneme_id"] for s in satirlar} == {f"d{i}" for i in range(200)}


@pytest.mark.parametrize("eksik", [{"durum": "tamam"}, {"deneme_id": "d1"}])
def test_zorunlu_alanlar_olmadan_yazilmaz(tmp_path, eksik):
    with pytest.raises(ValueError):
        HamKayit(tmp_path / "ham.jsonl").ekle(eksik)


def test_her_satir_gecerli_tek_satirlik_json(tmp_path):
    dosya = tmp_path / "ham.jsonl"
    HamKayit(dosya).ekle(_satir("d1", metin="çok\nsatırlı\ncevap"))
    satirlar = dosya.read_text(encoding="utf-8").splitlines()
    assert len(satirlar) == 1
    assert json.loads(satirlar[0])["metin"] == "çok\nsatırlı\ncevap"


def test_zaman_damgasi_utc():
    assert simdi().endswith("+00:00")
    