"""
EVREN bağlantısı.

Tasarım belgesi Bölüm 2: OpenAI uyumlu API, düşünme kapalı, JSON cevap biçimi.
Her çağrı, başarılı ya da hatalı, bir CagriSonucu olarak döner; hiçbir hata sessizce yutulmaz.
Teknik hatalar (bağlantı, zaman aşımı, hız limiti, sunucu hatası) en fazla 3 kez yeniden
denenir (Bölüm 6.1). 400, 401, 404 gibi hatalar yeniden denemekle düzelmeyeceği için denenmez.
"""

import os
import time
from collections.abc import Callable
from dataclasses import dataclass

import openai
from dotenv import load_dotenv
from openai import OpenAI

MODELLER = ["deepseek-v4.1-flash", "qwen3.8-flash-next", "gemma-4-31b"]

# Düşünmeyi her istekte kapatır (ikinci katman; birincisi API anahtarı ayarı).
DUSUNME_KAPALI = {"chat_template_kwargs": {"enable_thinking": False}}

EN_FAZLA_YENIDEN_DENEME = 3
BEKLEME_SANIYELERI = [5, 15, 45]  # 1., 2. ve 3. yeniden denemeden önce beklenen süre
ZAMAN_ASIMI_SANIYE = 60

# Sırası önemli: RateLimitError ve InternalServerError, APIStatusError'ın alt sınıflarıdır;
# bu yüzden önce bunlar yakalanır.
YENIDEN_DENENEBILIR = (
    openai.APIConnectionError,  # APITimeoutError da bunun alt sınıfıdır
    openai.RateLimitError,
    openai.InternalServerError,
)


@dataclass
class CagriSonucu:
    """Bir API çağrısının bütün sonucu. Tasarım belgesi Bölüm 6.2'deki kayıt alanlarının API kısmı."""

    istenen_model: str
    donen_model: str | None = None
    sistem_izi: str | None = None
    ham_cevap: str | None = None
    bitis_nedeni: str | None = None
    girdi_token: int | None = None
    cikti_token: int | None = None
    dusunme_token: int | None = None
    dusunme_metni_var: bool = False
    deneme_sayisi: int = 0
    sure_sn: float | None = None
    hata_turu: str | None = None
    hata_mesaji: str | None = None

    @property
    def basarili(self) -> bool:
        return self.hata_turu is None


def istemci_olustur() -> OpenAI:
    """`.env` dosyasındaki anahtar ve adresle bir EVREN istemcisi oluşturur."""
    load_dotenv()
    anahtar = os.environ.get("EVREN_API_KEY")
    adres = os.environ.get("EVREN_BASE_URL")
    if not anahtar or not adres:
        raise RuntimeError(".env dosyasında EVREN_API_KEY ve EVREN_BASE_URL tanımlı olmalı.")
    # Yeniden denemeyi kendimiz yapıyoruz (max_retries=0); böylece her deneme kayda geçer.
    return OpenAI(api_key=anahtar, base_url=adres, timeout=ZAMAN_ASIMI_SANIYE, max_retries=0)


def modelleri_listele(istemci: OpenAI) -> list[str]:
    """Platformda erişilebilen modellerin adları (/v1/models)."""
    return [m.id for m in istemci.models.list()]


def _yaniti_isle(sonuc: CagriSonucu, yanit) -> None:
    """API yanıtındaki bilgileri sonuca aktarır."""
    if not yanit.choices:
        sonuc.hata_turu, sonuc.hata_mesaji = "BosYanit", "API yanıtında hiç seçenek (choices) yok."
        return
    secim = yanit.choices[0]
    sonuc.donen_model = yanit.model
    sonuc.sistem_izi = getattr(yanit, "system_fingerprint", None)
    sonuc.ham_cevap = secim.message.content
    sonuc.bitis_nedeni = secim.finish_reason

    kullanim = yanit.usage
    if kullanim is not None:
        sonuc.girdi_token = kullanim.prompt_tokens
        sonuc.cikti_token = kullanim.completion_tokens
        ayrinti = getattr(kullanim, "completion_tokens_details", None)
        sonuc.dusunme_token = getattr(ayrinti, "reasoning_tokens", None) if ayrinti else None

    # Bazı sunucular düşünme metnini standart dışı bir alanda döndürür; varsa düşünme açık demektir.
    ek_alanlar = getattr(secim.message, "model_extra", None) or {}
    sonuc.dusunme_metni_var = bool(ek_alanlar.get("reasoning_content") or ek_alanlar.get("reasoning"))


def cagir(
    istemci: OpenAI,
    model: str,
    mesajlar: list[dict],
    *,
    temperature: float,
    max_tokens: int,
    bekle: Callable[[float], None] = time.sleep,
) -> CagriSonucu:
    """
    Modele tek bir istek gönderir. Teknik hatalarda en fazla 3 kez yeniden dener.
    `bekle` parametresi yalnızca testlerde beklemeyi atlamak için değiştirilir.
    """
    sonuc = CagriSonucu(istenen_model=model)
    baslangic = time.monotonic()

    for deneme in range(1, EN_FAZLA_YENIDEN_DENEME + 2):
        sonuc.deneme_sayisi = deneme
        try:
            yanit = istemci.chat.completions.create(
                model=model,
                messages=mesajlar,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                extra_body=DUSUNME_KAPALI,
            )
        except YENIDEN_DENENEBILIR as hata:
            sonuc.hata_turu, sonuc.hata_mesaji = type(hata).__name__, str(hata)
            if deneme > EN_FAZLA_YENIDEN_DENEME:
                break
            bekle(BEKLEME_SANIYELERI[deneme - 1])
        except openai.APIStatusError as hata:
            sonuc.hata_turu, sonuc.hata_mesaji = type(hata).__name__, str(hata)
            break
        else:
            sonuc.hata_turu = sonuc.hata_mesaji = None
            _yaniti_isle(sonuc, yanit)
            break

    sonuc.sure_sn = round(time.monotonic() - baslangic, 3)
    return sonuc
