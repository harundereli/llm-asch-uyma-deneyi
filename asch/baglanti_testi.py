"""
EVREN bağlantı testi (pilottan önce).

1. /v1/models ile tasarımdaki üç modelin platformda olup olmadığını kontrol eder.
2. Her modele tek bir soru sorar (BLG-01, Türkçe, tek başına, temperature 0) ve sonucu gösterir.

Toplam 3 çağrı, birkaç yüz token. Bu çağrılar deney verisine dahil değildir.

Çalıştırma:  python -m asch.baglanti_testi
"""

import json
from pathlib import Path

from asch.model import MODELLER, cagir, istemci_olustur, modelleri_listele
from asch.promptlar import mesajlar


def main() -> None:
    istemci = istemci_olustur()

    print("1) Model listesi (/v1/models)")
    mevcut = modelleri_listele(istemci)
    for model in MODELLER:
        print(f"   {model:<22} {'VAR' if model in mevcut else 'YOK'}")
    eksik = [m for m in MODELLER if m not in mevcut]
    if eksik:
        print(f"\n   Platformdaki modeller: {', '.join(sorted(mevcut))}")
        print("   Eksik model var; test burada durduruldu.")
        return

    sorular = json.loads(Path("veri/sorular.json").read_text(encoding="utf-8"))["sorular"]
    soru = next(s for s in sorular if s["id"] == "BLG-01")
    print(f"\n2) Deneme sorusu: {soru['soru_tr']}  (doğru şık: {soru['harfler']['dogru']})")

    for model in MODELLER:
        s = cagir(istemci, model, mesajlar(soru, "tr"), temperature=0.0, max_tokens=50)
        print(f"\n   [{model}]")
        if not s.basarili:
            print(f"   HATA ({s.hata_turu}): {s.hata_mesaji}")
            continue
        print(f"   cevap         : {s.ham_cevap!r}")
        print(f"   dönen model   : {s.donen_model}")
        print(f"   bitiş nedeni  : {s.bitis_nedeni}")
        print(f"   token         : girdi {s.girdi_token}, çıktı {s.cikti_token}, düşünme {s.dusunme_token}")
        print(f"   düşünme metni : {'VAR (düşünme açık olabilir!)' if s.dusunme_metni_var else 'yok'}")
        print(f"   süre          : {s.sure_sn} sn ({s.deneme_sayisi}. denemede)")


if __name__ == "__main__":
    main()
    