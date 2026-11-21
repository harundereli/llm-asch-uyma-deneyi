"""
Pilot analizi (tasarım belgesi, Bölüm 8). Pilot raporundaki (docs/pilot_raporu.md) bütün sayılar
bu kodla üretilir.

Yalnızca okur: veri/ham/pilot.jsonl dosyasına dokunmaz.

Çalıştırma:  python -m analiz.pilot_analizi
"""

import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from asch.calistir import kalan_denemeler
from asch.kayit import TEKNIK_HATA, HamKayit
from asch.plan import ana_plan, pilot_plani, prompt_kosulu
from asch.promptlar import mesajlar

PILOT_DOSYASI = Path("veri") / "ham" / "pilot.jsonl"
SORU_DOSYASI = Path("veri") / "sorular.json"
MK_ESIGI = 0.90  # Bölüm 9.1 ve Bölüm 8'deki karar kuralı


def genel(satirlar: list[dict], sorular: list[dict]) -> None:
    print("=== 1. Genel durum ===")
    print(f"satır: {len(satirlar)} · durum: {dict(Counter(s['durum'] for s in satirlar))}")
    teknik = [s for s in satirlar if s["durum"] == TEKNIK_HATA]
    if teknik:
        print("teknik hatalar (model, tür):", dict(Counter((s["model"], s["hata_turu"]) for s in teknik)))
        print("   örnek mesaj:", (teknik[0]["hata_mesaji"] or "")[:150])
    for parca, denemeler in pilot_plani(sorular).items():
        print(f"tamamlanmamış [{parca}]: {len(kalan_denemeler(denemeler, satirlar))}")
    gecerli = [s for s in satirlar if s["durum"] != TEKNIK_HATA]
    print("sorunlu cevap türleri:", dict(Counter(s["sorun"] for s in gecerli if s["durum"] == "sorunlu")) or "yok")
    print("düşünme tokenı > 0:", sum(1 for s in gecerli if (s.get("dusunme_token") or 0) > 0),
          "· düşünme metni:", sum(1 for s in gecerli if s.get("dusunme_metni_var")))
    print("dönen model ≠ istenen:", sum(1 for s in gecerli if s["donen_model"] != s["model"]))
    print("bitiş nedenleri:", dict(Counter(s["bitis_nedeni"] for s in gecerli)))
    print("bir çağrıdaki deneme sayısı:", dict(sorted(Counter(s["deneme_sayisi"] for s in satirlar).items())))
    print("sistem izleri (model → iz sayısı):")
    for model, izler in sorted(_gruplu(gecerli, "model", "sistem_izi").items()):
        print(f"   {model}: {dict(izler)}")


def kontrol_on_testi(gecerli: list[dict], soru: dict) -> None:
    print("\n=== 2. Kontrol ön testi (temperature 0, tek başına) ===")
    tablo = defaultdict(lambda: [0, 0])
    satirlar = [s for s in gecerli if s["parca"] == "pilot_kontrol"]
    for s in satirlar:
        hucre = tablo[(s["model"], s["dil"], s["tur"])]
        hucre[0] += s["kategori"] == "bagimsiz"
        hucre[1] += 1
    print(f"   {'model':<22}{'dil':<5}{'tür':<11}{'doğru':>7}{'%':>6}")
    kural = False
    for (model, dil, tur), (dogru, n) in sorted(tablo.items()):
        alti = dogru / n < MK_ESIGI
        kural |= alti
        print(f"   {model:<22}{dil:<5}{tur:<11}{dogru:>3}/{n:<3}{100 * dogru / n:>6.0f}{'  ← %90 altı' if alti else ''}")
    yanlis = [s for s in satirlar if s["kategori"] != "bagimsiz"]
    for s in yanlis:
        print(f"   yanlış: {s['model']} {s['dil']} {s['soru_id']} {soru[s['soru_id']]['soru_tr']} → {s['harf']}")
    print("karar kuralı (Bölüm 8) tetiklendi mi?", "EVET" if kural else "hayır")


def tutarlilik(gecerli: list[dict], soru: dict) -> None:
    print("\n=== 3. Tutarlılık testi (k = 3, Türkçe, küçük hata, açık; 10 soru × 5 tekrar) ===")
    satirlar = [s for s in gecerli if s["parca"] == "pilot_tutarlilik"]
    for model in sorted({s["model"] for s in satirlar}):
        ms = [s for s in satirlar if s["model"] == model]
        cevaplar = defaultdict(set)
        for s in ms:
            cevaplar[s["soru_id"]].add(s["harf"])
        degisen = {q: sorted(h for h in v if h) for q, v in cevaplar.items() if len(v) > 1}
        print(f"   {model:<22}n={len(ms)} · kategori: {dict(Counter(s['kategori'] for s in ms))}"
              f" · cevabı tekrarlarda değişen soru: {len(degisen)}/{len(cevaplar)} {degisen or ''}")
    for s in (s for s in satirlar if s["kategori"] == "uydu"):
        print(f"   uyma: {s['model']} {s['soru_id']} ({soru[s['soru_id']]['soru_tr']}) → {s['harf']}")


def token_ve_sure(gecerli: list[dict], sorular: list[dict], soru: dict) -> None:
    print("\n=== 4. Token ve süre ===")
    for parca in ("pilot_kontrol", "pilot_tutarlilik"):
        ps = [s for s in gecerli if s["parca"] == parca]
        print(f"   {parca}: girdi ort. {st.mean(s['girdi_token'] for s in ps):.0f} · "
              f"çıktı ort. {st.mean(s['cikti_token'] for s in ps):.1f} token")
    for model in sorted({s["model"] for s in gecerli}):
        sure = sorted(s["sure_sn"] for s in gecerli if s["model"] == model)
        print(f"   {model:<22}süre medyan {st.median(sure):.1f} sn · %90 {sure[int(0.9 * len(sure)) - 1]:.1f} sn"
              f" · en fazla {sure[-1]:.1f} sn")

    # Ana deney tahmini: her model ve dil için pilotta ölçülen token/karakter oranı,
    # ana deneydeki her denemenin promptuna tek tek uygulanır.
    oran = {}
    for model in {s["model"] for s in gecerli}:
        for dil in ("tr", "en"):
            ps = [s for s in gecerli if s["model"] == model and s["dil"] == dil]
            karakter = sum(len(s["system_prompt"]) + len(s["user_prompt"]) for s in ps)
            oran[(model, dil)] = sum(s["girdi_token"] for s in ps) / karakter
    cikti = st.mean(s["cikti_token"] for s in gecerli)
    toplam = 0.0
    for parca, denemeler in ana_plan(sorular).items():
        parca_toplam = 0.0
        for d in denemeler:
            onceki = []
            for model in (d.sira or (d.model,)):
                msj = mesajlar(soru[d.soru_id], d.dil, **prompt_kosulu(d, soru[d.soru_id], onceki))
                girdi = oran[(model, d.dil)] * (len(msj[0]["content"]) + len(msj[1]["content"]))
                parca_toplam += girdi + (60 if d.gerekce else cikti)  # gerekçe cevabı daha uzun (varsayım)
                onceki.append("A")
        toplam += parca_toplam
        print(f"   tahmin [{parca}]: {parca_toplam / 1e6:.2f} milyon token")
    print(f"   ANA DENEY TAHMİNİ: {toplam / 1e6:.2f} milyon token")
    pilot_token = sum((s.get("girdi_token") or 0) + (s.get("cikti_token") or 0) for s in gecerli)
    print(f"   pilotun toplam tokenı: {pilot_token:,}".replace(",", "."))


def _gruplu(satirlar, anahtar, deger):
    sonuc = defaultdict(Counter)
    for s in satirlar:
        sonuc[s[anahtar]][s[deger]] += 1
    return sonuc


def main() -> None:
    satirlar, bozuk = HamKayit(PILOT_DOSYASI).oku()
    if bozuk:
        print(f"Uyarı: {bozuk} okunamayan satır")
    sorular = json.loads(SORU_DOSYASI.read_text(encoding="utf-8"))["sorular"]
    soru = {s["id"]: s for s in sorular}
    gecerli = [s for s in satirlar if s["durum"] != TEKNIK_HATA]
    print(f"Pilot: {satirlar[0]['zaman']} – {satirlar[-1]['zaman']} (UTC)\n")
    genel(satirlar, sorular)
    kontrol_on_testi(gecerli, soru)
    tutarlilik(gecerli, soru)
    token_ve_sure(gecerli, sorular, soru)


if __name__ == "__main__":
    main()