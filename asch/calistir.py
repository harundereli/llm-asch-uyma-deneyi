"""
Deney çalıştırıcı (tasarım belgesi, Bölüm 6, 7 ve 8).

Planı (asch.plan) alır; her deneme için promptu oluşturur (asch.promptlar), EVREN'e gönderir
(asch.model), cevabı sınıflandırır (asch.siniflandirma) ve sonucu hemen diske yazar (asch.kayit).

- Hız: İstekler dakikada en fazla `rpm` olacak şekilde eşit aralıklarla, `paralel` iş parçacığıyla
  gönderilir. Aynı modele aynı anda en fazla `model_esz` istek gider (EVREN, yoğun modellerde hesap
  başına eşzamanlı isteği sınırlıyor). Sunucu zorlanırsa (429, yeniden denemeler) hız otomatik düşer,
  toparlanınca geri gelir.
- Kaldığı yerden devam: Tamamlanmış denemeler kayıttan okunur ve atlanır.
- B düzeneği: Bir grup, üç modelin sırayla cevapladığı tek bir denemedir. Grup yarıda kalırsa
  (teknik hata ya da durdurma) bir sonraki çalıştırmada baştan yapılır.
- Durdurma: Aşağıdaki durumlarda çalıştırma güvenli şekilde durur ve nedenini yazar; sorun
  giderildikten sonra aynı komut kaldığı yerden devam eder:
    * 401/403 (anahtar sorunu, kullanım şartlarının yeniden onaylanması gerekmesi) ve 400/404/422
    * art arda çok sayıda teknik hata (sunucu sorunu)
    * düşünmenin açık olduğunun fark edilmesi
    * API'nin döndürdüğü model adının değişmesi (tasarım belgesi, Bölüm 2: durdurma kuralı)
    * bu çalıştırmadaki token sınırına ulaşılması
    * Ctrl+C

Kullanım:
    python -m asch.calistir pilot                    Pilot (510 çağrı)
    python -m asch.calistir ana                      Ana deney (kaldığı yerden)
    python -m asch.calistir ana --parca A_normal     Yalnızca bir parça
    python -m asch.calistir pilot --sinir 5          Her parçadan yalnızca ilk 5 deneme
    python -m asch.calistir ana --kuru               API'ye gitmeden ne yapılacağını gösterir
    python -m asch.calistir ana --model-esz 3        Model başına eşzamanlı istek sınırını değiştirir
"""

import argparse
import json
import random
import threading
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict
from pathlib import Path

from asch.kayit import TEKNIK_HATA, HamKayit, simdi
from asch.model import DUSUNME_KAPALI, CagriSonucu, cagir, istemci_olustur
from asch.plan import Deneme, ana_plan, cogunluk_rolu, karistir, pilot_plani, prompt_kosulu
from asch.promptlar import mesajlar
from asch.siniflandirma import Ayristirma, cevabi_ayristir, siniflandir

VARSAYILAN_RPM = 180        # anahtarın tavanı 200; biraz pay bırakılır
VARSAYILAN_PARALEL = 16
VARSAYILAN_MODEL_ESZ = 2    # pilotta EVREN: "hesabınız bu modelde en fazla 2 eşzamanlı istek açabilir"
TOKEN_SINIRI = 9_000_000    # bir çalıştırmada; anahtarın günlük 10 milyon tavanının altında
ART_ARDA_HATA_SINIRI = 20
DURDURAN_HATALAR = {
    "AuthenticationError", "PermissionDeniedError",                   # 401, 403
    "BadRequestError", "NotFoundError", "UnprocessableEntityError",   # 400, 404, 422
}
HAM_KLASOR = Path("veri") / "ham"
SORU_DOSYASI = Path("veri") / "sorular.json"


def _sayi(n: float) -> str:
    """Türkçe binlik ayırıcıyla yazar: 12240 -> 12.240."""
    return f"{n:,}".replace(",", ".")


# ---------------------------------------------------------------------------
# Hız sınırlayıcı
# ---------------------------------------------------------------------------

class HizSinirlayici:
    """
    İsteklerin başlangıçlarını eşit aralıklara yayar: dakikada en fazla `rpm` istek.
    Sunucu zorlandığında aralık geçici olarak büyür (en fazla 4 kat), toparlanınca yavaşça küçülür.
    """

    EN_FAZLA_YAVASLAMA = 4.0

    def __init__(self, rpm: float, zaman: Callable[[], float] = time.monotonic,
                 uyu: Callable[[float], None] = time.sleep):
        if rpm <= 0:
            raise ValueError("rpm pozitif olmalı")
        self.aralik = 60.0 / rpm
        self.carpan = 1.0
        self._siradaki = float("-inf")
        self._kilit = threading.Lock()
        self._zaman, self._uyu = zaman, uyu

    def bekle(self) -> None:
        """Sıradaki isteğin zamanı gelene kadar bekler."""
        with self._kilit:
            simdi_ = self._zaman()
            baslangic = max(simdi_, self._siradaki)
            self._siradaki = baslangic + self.aralik * self.carpan
        if baslangic > simdi_:
            self._uyu(baslangic - simdi_)

    def yavasla(self) -> None:
        with self._kilit:
            self.carpan = min(self.carpan * 1.5, self.EN_FAZLA_YAVASLAMA)

    def toparla(self) -> None:
        with self._kilit:
            self.carpan = max(1.0, self.carpan * 0.98)


# ---------------------------------------------------------------------------
# Hangi denemeler kaldı?
# ---------------------------------------------------------------------------

def tamamlanan_gruplar(satirlar: list[dict]) -> set[str]:
    """B'de bütün modelleri aynı çalıştırmada teknik hatasız cevaplamış grupların kimlikleri."""
    sira_bitti = defaultdict(set)
    grup_boyutu = {}
    for s in satirlar:
        if s.get("grup_id") and s.get("durum") != TEKNIK_HATA:
            sira_bitti[(s["grup_id"], s["calistirma_id"])].add(s["konusma_sirasi"])
            grup_boyutu[s["grup_id"]] = len(s["sira"])
    return {g for (g, _), siralar in sira_bitti.items() if len(siralar) == grup_boyutu[g]}


def kalan_denemeler(denemeler: list[Deneme], satirlar: list[dict]) -> list[Deneme]:
    """Kayıtta tamamlanmış görünmeyen denemeler."""
    tekli_bitti = {s["deneme_id"] for s in satirlar if s.get("durum") != TEKNIK_HATA and not s.get("grup_id")}
    grup_bitti = tamamlanan_gruplar(satirlar)
    return [d for d in denemeler if d.deneme_id not in (grup_bitti if d.sira else tekli_bitti)]


# ---------------------------------------------------------------------------
# Çalıştırıcı
# ---------------------------------------------------------------------------

class Calistirici:
    def __init__(
        self,
        istemci,
        kayit: HamKayit,
        sorular: list[dict],
        *,
        rpm: float = VARSAYILAN_RPM,
        paralel: int = VARSAYILAN_PARALEL,
        model_esz: int = VARSAYILAN_MODEL_ESZ,
        token_siniri: int = TOKEN_SINIRI,
        cagri_fonksiyonu: Callable[..., CagriSonucu] = cagir,
        yeniden_deneme_bekle: Callable[[float], None] | None = None,
        cikti: Callable[[str], None] = print,
    ):
        self.istemci = istemci
        self.kayit = kayit
        self.sorular = {s["id"]: s for s in sorular}
        self.hiz = HizSinirlayici(rpm)
        self.paralel = paralel
        self.model_esz = model_esz
        self._model_kapilari: dict[str, threading.Semaphore] = {}
        self.token_siniri = token_siniri
        self._cagir = cagri_fonksiyonu
        # Yeniden denemeler arasında beklerken küçük bir rastgele sapma (iş parçacıkları aynı anda dönmesin)
        self._yeniden_deneme_bekle = yeniden_deneme_bekle or (lambda s: time.sleep(s * random.uniform(0.8, 1.2)))
        self._yaz = cikti

        self.durdur = threading.Event()
        self.durma_nedeni: str | None = None
        self._kilit = threading.Lock()
        self.token = 0
        self._art_arda_hata = 0
        self._donen_model: dict[str, str] = {}
        self.sayac = Counter()

    # -------------------------------------------------- durdurma ve denetim

    def _dur(self, neden: str) -> None:
        with self._kilit:
            if self.durma_nedeni is None:
                self.durma_nedeni = neden
        self.durdur.set()

    def _denetle(self, sonuc: CagriSonucu) -> None:
        """Her çağrıdan sonra: hız ayarı, token sayacı ve durdurma kuralları."""
        with self._kilit:
            self.token += (sonuc.girdi_token or 0) + (sonuc.cikti_token or 0)
            token = self.token
            self._art_arda_hata = 0 if sonuc.basarili else self._art_arda_hata + 1
            art_arda = self._art_arda_hata
            ilk_donen = None
            if sonuc.donen_model:
                ilk_donen = self._donen_model.setdefault(sonuc.istenen_model, sonuc.donen_model)

        if sonuc.deneme_sayisi > 1 or sonuc.hata_turu == "RateLimitError":
            self.hiz.yavasla()
        else:
            self.hiz.toparla()

        if sonuc.hata_turu in DURDURAN_HATALAR:
            self._dur(f"{sonuc.hata_turu}: {sonuc.hata_mesaji}")
        elif art_arda >= ART_ARDA_HATA_SINIRI:
            self._dur(f"Art arda {art_arda} teknik hata (son: {sonuc.hata_turu}). Sunucu sorunlu olabilir.")
        if sonuc.basarili and (sonuc.dusunme_metni_var or (sonuc.dusunme_token or 0) > 0):
            self._dur(f"{sonuc.istenen_model}: düşünme açık görünüyor (düşünme tokenı: {sonuc.dusunme_token}).")
        if ilk_donen is not None and ilk_donen != sonuc.donen_model:
            self._dur(f"{sonuc.istenen_model}: API'nin döndürdüğü model adı değişti "
                      f"({ilk_donen} → {sonuc.donen_model}).")
        if token >= self.token_siniri:
            self._dur(f"Bu çalıştırmadaki token sınırına ulaşıldı ({_sayi(token)} token).")

    # -------------------------------------------------- tek çağrı ve kayıt

    def _model_kapisi(self, model: str) -> threading.Semaphore:
        """Her model için aynı anda en fazla `model_esz` isteğe izin veren kapı."""
        with self._kilit:
            if model not in self._model_kapilari:
                self._model_kapilari[model] = threading.Semaphore(self.model_esz)
            return self._model_kapilari[model]

    def _cagri(self, deneme: Deneme, model: str, mesaj: list[dict]) -> CagriSonucu | None:
        if self.durdur.is_set():
            return None
        with self._model_kapisi(model):  # bu modele giden istek sayısı sınırın altına inene kadar bekler
            if self.durdur.is_set():
                return None
            self.hiz.bekle()
            if self.durdur.is_set():
                return None
            sonuc = self._cagir(self.istemci, model, mesaj, temperature=deneme.temperature,
                                max_tokens=deneme.max_tokens, bekle=self._yeniden_deneme_bekle)
        self._denetle(sonuc)
        return sonuc

    def _kaydet(self, deneme: Deneme, deneme_id: str, soru: dict, model: str, mesaj: list[dict],
                sonuc: CagriSonucu, ek: dict) -> Ayristirma:
        if sonuc.basarili:
            ayristirma = cevabi_ayristir(sonuc.ham_cevap)
            kategori, alt = siniflandir(ayristirma, soru, cogunluk_rolu(deneme))
            durum = "tamam" if ayristirma.harf else "sorunlu"
        else:
            ayristirma, kategori, alt, durum = Ayristirma(harf=None), None, None, TEKNIK_HATA

        self.kayit.ekle({
            "zaman": simdi(),
            "deneme_id": deneme_id,
            "durum": durum,
            "parca": deneme.parca,
            "soru_id": deneme.soru_id,
            "tur": soru["tur"],
            "dil": deneme.dil,
            "k": deneme.k,
            "hata": deneme.hata,
            "gorunurluk": deneme.gorunurluk,
            "muttefik_konumu": deneme.muttefik_konumu,
            "tekrar": deneme.tekrar,
            "gerekce": deneme.gerekce,
            "model": model,
            "dogru_harf": soru["harfler"]["dogru"],
            "cogunluk_harfi": soru["harfler"][deneme.hata] if deneme.hata else None,
            "temperature": deneme.temperature,
            "max_tokens": deneme.max_tokens,
            "response_format": "json_object",
            "extra_body": DUSUNME_KAPALI,
            "system_prompt": mesaj[0]["content"],
            "user_prompt": mesaj[1]["content"],
            "harf": ayristirma.harf,
            "sorun": ayristirma.sorun,
            "guven": ayristirma.guven,
            "neden": ayristirma.neden,
            "kategori": kategori,
            "alt_kategori": alt,
            **ek,
            **asdict(sonuc),
        })
        with self._kilit:
            self.sayac["cagri"] += 1
            self.sayac[f"durum:{durum}"] += 1
            if kategori:
                self.sayac[f"kategori:{kategori}"] += 1
        return ayristirma

    # -------------------------------------------------- denemeler

    def _tekli(self, deneme: Deneme) -> None:
        soru = self.sorular[deneme.soru_id]
        mesaj = mesajlar(soru, deneme.dil, **prompt_kosulu(deneme, soru))
        sonuc = self._cagri(deneme, deneme.model, mesaj)
        if sonuc is not None:
            self._kaydet(deneme, deneme.deneme_id, soru, deneme.model, mesaj, sonuc, {})

    def _grup(self, deneme: Deneme) -> None:
        """B: modeller sırayla cevaplar; her biri öncekilerin cevabını görür."""
        soru = self.sorular[deneme.soru_id]
        calistirma_id = uuid.uuid4().hex[:12]
        onceki: list[str | None] = []
        for konusma_sirasi, model in enumerate(deneme.sira, 1):
            mesaj = mesajlar(soru, deneme.dil, **prompt_kosulu(deneme, soru, onceki))
            sonuc = self._cagri(deneme, model, mesaj)
            if sonuc is None:
                return  # durduruldu: grup yarım kalır, sonraki çalıştırmada baştan yapılır
            ayristirma = self._kaydet(deneme, f"{deneme.deneme_id}|p{konusma_sirasi}", soru, model, mesaj, sonuc, {
                "grup_id": deneme.deneme_id,
                "calistirma_id": calistirma_id,
                "sira": list(deneme.sira),
                "konusma_sirasi": konusma_sirasi,
                "onceki_model_cevaplari": list(onceki),
            })
            if not sonuc.basarili:
                return  # teknik hata: grup sonraki çalıştırmada baştan yapılır
            onceki.append(ayristirma.harf)  # okunamayan cevap None → "(cevap vermedi)"

    def _is(self, deneme: Deneme) -> None:
        try:
            (self._grup if deneme.sira else self._tekli)(deneme)
        except Exception as hata:  # beklenmeyen bir kod hatası: hemen dur, hatayı göster
            self._dur(f"Beklenmeyen hata: {hata!r}")
            raise

    # -------------------------------------------------- bir parçayı çalıştırma

    def calistir(self, denemeler: list[Deneme], baslik: str) -> bool:
        """Bir parçanın kalan denemelerini çalıştırır. Durdurulmadan bittiyse True döner."""
        satirlar, bozuk = self.kayit.oku()
        kalan = kalan_denemeler(denemeler, satirlar)
        self._yaz(f"\n[{baslik}] toplam {_sayi(len(denemeler))} deneme · tamamlanmış {_sayi(len(denemeler) - len(kalan))}"
                  f" · kalan {_sayi(len(kalan))}")
        if bozuk:
            self._yaz(f"   Uyarı: kayıt dosyasında okunamayan {bozuk} satır var (yarıda kalmış yazım).")
        if not kalan:
            return True

        toplam_cagri = sum(d.cagri_sayisi for d in kalan)
        baslangic, onceki_cagri = time.monotonic(), self.sayac["cagri"]
        adim = max(1, len(kalan) // 20)
        biten = 0
        havuz = ThreadPoolExecutor(max_workers=self.paralel)
        bekleyen = {havuz.submit(self._is, d) for d in karistir(kalan)}
        try:
            while bekleyen:
                bitenler, bekleyen = wait(bekleyen, timeout=1.0, return_when=FIRST_COMPLETED)
                for gelecek in bitenler:
                    gelecek.result()
                    biten += 1
                    if biten % adim == 0 or not bekleyen:
                        self._ilerleme(baslik, biten, len(kalan), toplam_cagri, baslangic, onceki_cagri)
        except KeyboardInterrupt:
            self._dur("Kullanıcı durdurdu (Ctrl+C).")
            self._yaz("   Durduruluyor; süren istekler bitince çıkılacak...")
        finally:
            havuz.shutdown(wait=True, cancel_futures=True)

        if self.durdur.is_set():
            self._yaz(f"\n   DURDURULDU: {self.durma_nedeni}")
            self._yaz("   Sorunu giderip aynı komutu tekrar çalıştırın; kaldığı yerden devam eder.")
            return False
        return True

    def _ilerleme(self, baslik: str, biten: int, toplam: int, toplam_cagri: int,
                  baslangic: float, onceki_cagri: int) -> None:
        gecen = max(time.monotonic() - baslangic, 1e-9)
        cagri = self.sayac["cagri"] - onceki_cagri
        hiz = cagri / gecen * 60
        kalan_dk = (toplam_cagri - cagri) / hiz if hiz else 0
        self._yaz(f"   [{baslik}] {_sayi(biten)}/{_sayi(toplam)} deneme · {_sayi(round(hiz))} çağrı/dk · "
                  f"token {_sayi(self.token)} · kalan ~{_sayi(round(kalan_dk))} dk")

    def ozet(self) -> str:
        satirlar = [f"   çağrı: {_sayi(self.sayac['cagri'])} · token: {_sayi(self.token)}"]
        for anahtar in sorted(k for k in self.sayac if ":" in k):
            satirlar.append(f"   {anahtar:<22}{_sayi(self.sayac[anahtar])}")
        return "\n".join(satirlar)


# ---------------------------------------------------------------------------
# Komut satırı
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ayrac = argparse.ArgumentParser(description="Asch deneyi çalıştırıcı")
    ayrac.add_argument("hangisi", choices=["pilot", "ana"])
    ayrac.add_argument("--parca", help="yalnızca bu parçayı çalıştırır")
    ayrac.add_argument("--sinir", type=int, help="her parçadan en fazla bu kadar deneme (deneme amaçlı)")
    ayrac.add_argument("--rpm", type=float, default=VARSAYILAN_RPM)
    ayrac.add_argument("--paralel", type=int, default=VARSAYILAN_PARALEL)
    ayrac.add_argument("--model-esz", type=int, default=VARSAYILAN_MODEL_ESZ,
                       help="aynı modele aynı anda gönderilebilecek en fazla istek sayısı")
    ayrac.add_argument("--kuru", action="store_true", help="API'ye gitmeden yalnızca ne yapılacağını gösterir")
    a = ayrac.parse_args(argv)

    sorular = json.loads(SORU_DOSYASI.read_text(encoding="utf-8"))["sorular"]
    plan = pilot_plani(sorular) if a.hangisi == "pilot" else ana_plan(sorular)
    if a.parca:
        if a.parca not in plan:
            ayrac.error(f"Bilinmeyen parça: {a.parca}. Seçenekler: {', '.join(plan)}")
        plan = {a.parca: plan[a.parca]}
    if a.sinir:
        plan = {parca: denemeler[: a.sinir] for parca, denemeler in plan.items()}

    kayit = HamKayit(HAM_KLASOR / f"{a.hangisi}.jsonl")
    print(f"Kayıt dosyası: {kayit.dosya}")

    if a.kuru:
        satirlar, _ = kayit.oku()
        for parca, denemeler in plan.items():
            kalan = kalan_denemeler(denemeler, satirlar)
            print(f"[{parca}] toplam {_sayi(len(denemeler))} · kalan {_sayi(len(kalan))} deneme "
                  f"({_sayi(sum(d.cagri_sayisi for d in kalan))} çağrı)")
        return 0

    calistirici = Calistirici(istemci_olustur(), kayit, sorular, rpm=a.rpm, paralel=a.paralel,
                              model_esz=a.model_esz)
    for parca, denemeler in plan.items():
        if not calistirici.calistir(denemeler, parca):
            break
    print("\nÖzet (bu çalıştırma):\n" + calistirici.ozet())
    return 1 if calistirici.durdur.is_set() else 0


if __name__ == "__main__":
    raise SystemExit(main())