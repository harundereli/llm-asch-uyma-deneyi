"""
Ham veri kaydı (tasarım belgesi, Bölüm 6.2).

- Her çağrı JSONL dosyasına tek bir satır olarak yazılır.
- Dosyaya yalnızca EKLEME yapılır; bu sınıfta var olan bir satırı değiştiren ya da silen
  hiçbir işlem yoktur.
- Her satır yazıldığı anda diske işlenir (flush + fsync); elektrik kesilse bile en fazla
  o an yazılmakta olan satır kaybolur.
- Program yeniden başlatıldığında tamamlanmış denemeler okunur ve atlanır (kaldığı yerden devam).
- Teknik hatayla biten denemeler tamamlanmış sayılmaz; bir sonraki çalıştırmada yeniden denenir.
  Hata satırları dosyada kalır (silinmez), analizde aynı denemenin son geçerli satırı kullanılır.
- Paralel çalışan iş parçacıkları aynı dosyaya güvenle yazabilir.
"""

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

TEKNIK_HATA = "teknik_hata"


def simdi() -> str:
    """UTC zaman damgası, ISO biçiminde (ör. 2026-11-21T10:15:30.123456+00:00)."""
    return datetime.now(timezone.utc).isoformat()


class HamKayit:
    """Yalnızca eklenebilen JSONL kayıt dosyası."""

    def __init__(self, dosya: str | Path):
        self.dosya = Path(dosya)
        self.dosya.parent.mkdir(parents=True, exist_ok=True)
        self._kilit = threading.Lock()
        self._satir_sonu_kontrol_edildi = False

    def _yarim_satiri_kapat(self, f) -> None:
        """
        Önceki bir çalıştırma satırın ortasında kesildiyse dosya '\\n' ile bitmez. Yeni satırı
        onun devamına yazmamak için önce bir satır sonu eklenir. (Yarım satır silinmez; okuma
        sırasında bozuk satır olarak sayılır.)
        """
        if self._satir_sonu_kontrol_edildi:
            return
        self._satir_sonu_kontrol_edildi = True
        if self.dosya.exists() and self.dosya.stat().st_size > 0:
            with open(self.dosya, "rb") as okuma:
                okuma.seek(-1, os.SEEK_END)
                if okuma.read(1) != b"\n":
                    f.write("\n")

    def ekle(self, satir: dict) -> None:
        """Bir satırı dosyanın sonuna ekler ve hemen diske işler."""
        if "deneme_id" not in satir or "durum" not in satir:
            raise ValueError("Her kayıt satırında 'deneme_id' ve 'durum' alanları olmalı.")
        metin = json.dumps(satir, ensure_ascii=False)
        with self._kilit, open(self.dosya, "a", encoding="utf-8", newline="\n") as f:
            self._yarim_satiri_kapat(f)
            f.write(metin + "\n")
            f.flush()
            os.fsync(f.fileno())

    def oku(self) -> tuple[list[dict], int]:
        """Bütün geçerli satırları ve okunamayan (bozuk) satır sayısını döndürür."""
        if not self.dosya.exists():
            return [], 0
        satirlar, bozuk = [], 0
        with open(self.dosya, encoding="utf-8") as f:
            for ham in f:
                if not ham.strip():
                    continue
                try:
                    satirlar.append(json.loads(ham))
                except json.JSONDecodeError:
                    bozuk += 1
        return satirlar, bozuk

    def tamamlanan_idler(self) -> set[str]:
        """Teknik hata dışında bir sonuçla biten denemelerin kimlikleri (yeniden çalıştırılmaz)."""
        satirlar, _ = self.oku()
        return {s["deneme_id"] for s in satirlar if s.get("durum") != TEKNIK_HATA}
    