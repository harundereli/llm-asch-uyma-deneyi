"""
EVREN bağlantı kodunun testleri. Gerçek API'ye bağlanmaz; sahte bir istemci kullanır.

Çalıştırma:  python -m pytest
"""

from types import SimpleNamespace

import httpx2
import openai
import pytest

from asch.model import DUSUNME_KAPALI, EN_FAZLA_YENIDEN_DENEME, cagir

ISTEK = httpx2.Request("POST", "https://ornek.test/v1/chat/completions")


def _durum_hatasi(sinif, kod):
    return sinif("hata", response=httpx2.Response(kod, request=ISTEK), body=None)


def _basarili_yanit(icerik='{"cevap": "B"}', ek_alanlar=None):
    mesaj = SimpleNamespace(content=icerik, model_extra=ek_alanlar or {})
    kullanim = SimpleNamespace(
        prompt_tokens=120, completion_tokens=6,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
    )
    return SimpleNamespace(
        model="deepseek-v4.1-flash", system_fingerprint="iz-1",
        choices=[SimpleNamespace(message=mesaj, finish_reason="stop")], usage=kullanim,
    )


class SahteIstemci:
    """Sırayla verilen sonuçları döndüren (ya da hata fırlatan) sahte istemci."""

    def __init__(self, *sonuclar):
        self.sonuclar = list(sonuclar)
        self.istekler = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **istek):
        self.istekler.append(istek)
        sonuc = self.sonuclar.pop(0)
        if isinstance(sonuc, Exception):
            raise sonuc
        return sonuc


def _cagir(istemci, beklemeler=None):
    beklemeler = [] if beklemeler is None else beklemeler
    return cagir(istemci, "deepseek-v4.1-flash", [{"role": "user", "content": "x"}],
                 temperature=1.0, max_tokens=50, bekle=beklemeler.append)


def test_basarili_cagri_bilgileri_kaydeder():
    sonuc = _cagir(SahteIstemci(_basarili_yanit()))
    assert sonuc.basarili
    assert sonuc.ham_cevap == '{"cevap": "B"}'
    assert (sonuc.girdi_token, sonuc.cikti_token, sonuc.dusunme_token) == (120, 6, 0)
    assert sonuc.donen_model == "deepseek-v4.1-flash" and sonuc.bitis_nedeni == "stop"
    assert sonuc.deneme_sayisi == 1 and not sonuc.dusunme_metni_var


def test_istek_tasarimdaki_ayarlarla_gonderilir():
    istemci = SahteIstemci(_basarili_yanit())
    _cagir(istemci)
    istek = istemci.istekler[0]
    assert istek["response_format"] == {"type": "json_object"}
    assert istek["extra_body"] == DUSUNME_KAPALI
    assert istek["temperature"] == 1.0 and istek["max_tokens"] == 50


@pytest.mark.parametrize("hata", [
    _durum_hatasi(openai.RateLimitError, 429),
    _durum_hatasi(openai.InternalServerError, 503),
    openai.APIConnectionError(request=ISTEK),
    openai.APITimeoutError(request=ISTEK),
])
def test_teknik_hata_yeniden_denenir_ve_sonra_basarir(hata):
    beklemeler = []
    sonuc = _cagir(SahteIstemci(hata, _basarili_yanit()), beklemeler)
    assert sonuc.basarili and sonuc.deneme_sayisi == 2
    assert beklemeler == [5]


def test_en_fazla_uc_kez_yeniden_denenir():
    hatalar = [_durum_hatasi(openai.RateLimitError, 429) for _ in range(EN_FAZLA_YENIDEN_DENEME + 1)]
    beklemeler = []
    istemci = SahteIstemci(*hatalar)
    sonuc = _cagir(istemci, beklemeler)
    assert not sonuc.basarili and sonuc.hata_turu == "RateLimitError"
    assert len(istemci.istekler) == EN_FAZLA_YENIDEN_DENEME + 1
    assert beklemeler == [5, 15, 45]


@pytest.mark.parametrize("sinif, kod", [
    (openai.BadRequestError, 400),
    (openai.AuthenticationError, 401),
    (openai.NotFoundError, 404),
])
def test_istemci_hatasi_yeniden_denenmez(sinif, kod):
    istemci = SahteIstemci(_durum_hatasi(sinif, kod))
    sonuc = _cagir(istemci)
    assert not sonuc.basarili and sonuc.hata_turu == sinif.__name__
    assert len(istemci.istekler) == 1


def test_dusunme_metni_fark_edilir():
    sonuc = _cagir(SahteIstemci(_basarili_yanit(ek_alanlar={"reasoning_content": "Hmm..."})))
    assert sonuc.basarili and sonuc.dusunme_metni_var


def test_bos_yanit_hata_olarak_kaydedilir():
    yanit = _basarili_yanit()
    yanit.choices = []
    sonuc = _cagir(SahteIstemci(yanit))
    assert not sonuc.basarili and sonuc.hata_turu == "BosYanit"
    