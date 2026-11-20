"""
Soru havuzu.

Tasarım belgesinin (docs/tasarim.md) 3. bölümündeki kurallara göre 60 soruyu oluşturur:
- 20 sembolik çizgi sorusu (kodla üretilir)
- 20 bilgi sorusu (elle hazırlanmıştır, tasarım belgesi Ek A)
- 20 aritmetik sorusu (kodla üretilir)

Her sorunun 4 sabit şıkkı vardır: doğru, küçük yanlış, büyük yanlış ve ek şık.
Şıkların A–D konumları, her türde her rolün her harfte tam 5 kez bulunacağı şekilde dengelenir.

Çalıştırma:  python -m asch.sorular
Çıktı:       veri/sorular.json
"""

import json
import random
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

TOHUM = 20261120  # Sabit rastgelelik tohumu: kod her çalıştırıldığında aynı soruları üretir.
HARFLER = ["A", "B", "C", "D"]
ROLLER = ["dogru", "kucuk", "buyuk", "ek"]
TURLER = ["cizgi", "bilgi", "aritmetik"]
CIKTI_DOSYASI = Path("veri") / "sorular.json"


@dataclass
class Secenek:
    """Bir şık: Türkçe ve İngilizce metni ile sorudaki rolü."""

    tr: str
    en: str
    rol: str


@dataclass
class Soru:
    """Bir soru. `secenekler` harften şıkka, `harfler` rolden harfe eşleme yapar."""

    id: str
    tur: str
    soru_tr: str
    soru_en: str
    secenekler: dict[str, Secenek]
    harfler: dict[str, str]


# Her satır: (soru TR, soru EN, doğru, küçük yanlış, büyük yanlış, ek şık).
# Her şık (Türkçe, İngilizce) çiftidir. Kaynak: tasarım belgesi, Ek A.
BILGI_SORULARI = [
    ("Japonya'nın başkenti neresidir?", "What is the capital of Japan?",
     ("Tokyo", "Tokyo"), ("Osaka", "Osaka"), ("Lagos", "Lagos"), ("Seul", "Seoul")),
    ("Avustralya'nın başkenti neresidir?", "What is the capital of Australia?",
     ("Kanberra", "Canberra"), ("Sidney", "Sydney"), ("Kahire", "Cairo"), ("Melbourne", "Melbourne")),
    ("Kanada'nın başkenti neresidir?", "What is the capital of Canada?",
     ("Ottawa", "Ottawa"), ("Toronto", "Toronto"), ("Lima", "Lima"), ("Vancouver", "Vancouver")),
    ("Eyfel Kulesi hangi şehirdedir?", "In which city is the Eiffel Tower?",
     ("Paris", "Paris"), ("Lyon", "Lyon"), ("Tokyo", "Tokyo"), ("Brüksel", "Brussels")),
    ("Gize piramitleri hangi ülkededir?", "In which country are the Pyramids of Giza?",
     ("Mısır", "Egypt"), ("Sudan", "Sudan"), ("Norveç", "Norway"), ("Libya", "Libya")),
    ("Güneş Sistemi'nin en büyük gezegeni hangisidir?", "What is the largest planet in the Solar System?",
     ("Jüpiter", "Jupiter"), ("Satürn", "Saturn"), ("Merkür", "Mercury"), ("Neptün", "Neptune")),
    ("Güneş'e en yakın gezegen hangisidir?", "Which planet is closest to the Sun?",
     ("Merkür", "Mercury"), ("Venüs", "Venus"), ("Neptün", "Neptune"), ("Mars", "Mars")),
    ("\"Kızıl Gezegen\" olarak bilinen gezegen hangisidir?", "Which planet is known as the \"Red Planet\"?",
     ("Mars", "Mars"), ("Venüs", "Venus"), ("Uranüs", "Uranus"), ("Jüpiter", "Jupiter")),
    ("Suyun kimyasal formülü nedir?", "What is the chemical formula of water?",
     ("H₂O", "H₂O"), ("H₂O₂", "H₂O₂"), ("NaCl", "NaCl"), ("CO₂", "CO₂")),
    ("Altının kimyasal sembolü nedir?", "What is the chemical symbol for gold?",
     ("Au", "Au"), ("Ag", "Ag"), ("O", "O"), ("Al", "Al")),
    ("Bitkiler fotosentezde havadan hangi gazı alır?", "Which gas do plants take from the air during photosynthesis?",
     ("Karbondioksit", "Carbon dioxide"), ("Oksijen", "Oxygen"), ("Helyum", "Helium"), ("Azot", "Nitrogen")),
    ("Dünya atmosferinin büyük kısmını hangi gaz oluşturur?", "Which gas makes up most of Earth's atmosphere?",
     ("Azot", "Nitrogen"), ("Oksijen", "Oxygen"), ("Helyum", "Helium"), ("Karbondioksit", "Carbon dioxide")),
    ("Romeo ve Juliet'i kim yazmıştır?", "Who wrote Romeo and Juliet?",
     ("William Shakespeare", "William Shakespeare"), ("Christopher Marlowe", "Christopher Marlowe"),
     ("Isaac Newton", "Isaac Newton"), ("Charles Dickens", "Charles Dickens")),
    ("Mona Lisa'yı kim resmetmiştir?", "Who painted the Mona Lisa?",
     ("Leonardo da Vinci", "Leonardo da Vinci"), ("Michelangelo", "Michelangelo"),
     ("Albert Einstein", "Albert Einstein"), ("Raffaello", "Raphael")),
    ("Görelilik kuramını kim geliştirmiştir?", "Who developed the theory of relativity?",
     ("Albert Einstein", "Albert Einstein"), ("Isaac Newton", "Isaac Newton"),
     ("W. A. Mozart", "W. A. Mozart"), ("Niels Bohr", "Niels Bohr")),
    ("Penisilini kim keşfetmiştir?", "Who discovered penicillin?",
     ("Alexander Fleming", "Alexander Fleming"), ("Louis Pasteur", "Louis Pasteur"),
     ("Napolyon Bonapart", "Napoleon Bonaparte"), ("Robert Koch", "Robert Koch")),
    ("İlk insanlı Ay inişi hangi yılda gerçekleşmiştir?", "In which year did the first crewed Moon landing take place?",
     ("1969", "1969"), ("1967", "1967"), ("1869", "1869"), ("1975", "1975")),
    ("Dünyanın en büyük okyanusu hangisidir?", "What is the largest ocean on Earth?",
     ("Pasifik", "Pacific"), ("Atlantik", "Atlantic"), ("Arktik", "Arctic"), ("Hint", "Indian")),
    ("Nüfusu en fazla olan kıta hangisidir?", "Which continent has the largest population?",
     ("Asya", "Asia"), ("Afrika", "Africa"), ("Antarktika", "Antarctica"), ("Avrupa", "Europe")),
    ("Antik Olimpiyat Oyunları hangi ülkede başlamıştır?", "In which country did the ancient Olympic Games begin?",
     ("Yunanistan", "Greece"), ("İtalya", "Italy"), ("Japonya", "Japan"), ("Mısır", "Egypt")),
]


# ---------------------------------------------------------------------------
# Şık konumlarının dengelenmesi
# ---------------------------------------------------------------------------

def rastgele_latin_kare(rng: random.Random) -> list[list[str]]:
    """
    4x4 rastgele bir Latin kare döndürür. Her satır bir sorunun A–D düzenidir
    (hangi harfte hangi rol var). Latin kare olduğu için her rol, 4 satır boyunca
    her harfte tam bir kez bulunur.
    """
    temel = [[(satir + sutun) % 4 for sutun in range(4)] for satir in range(4)]
    rng.shuffle(temel)                    # satırların sırasını karıştır
    sutun_sirasi = list(range(4))
    rng.shuffle(sutun_sirasi)             # sütunların sırasını karıştır
    rol_sirasi = ROLLER[:]
    rng.shuffle(rol_sirasi)               # sayıları rollere rastgele eşle
    return [[rol_sirasi[satir[s]] for s in sutun_sirasi] for satir in temel]


def dengeli_duzenler(rng: random.Random, adet: int = 20) -> list[list[str]]:
    """5 farklı rastgele Latin kareyi birleştirir: her rol her harfte tam adet/4 kez bulunur."""
    duzenler = []
    for _ in range(adet // 4):
        duzenler.extend(rastgele_latin_kare(rng))
    rng.shuffle(duzenler)
    return duzenler


# ---------------------------------------------------------------------------
# Çizgi ve aritmetik değerlerinin üretilmesi
# ---------------------------------------------------------------------------

def dengeli_referanslar(rng: random.Random, adet: int = 20) -> list[int]:
    """
    5–15 cm arasındaki 11 referans uzunluğunun her birini en az bir kez kullanır;
    kalanları yine bu aralıktan, tekrar etmeden seçer. Böylece her uzunluk 1 ya da 2 kez geçer.
    """
    aralik = list(range(5, 16))
    referanslar = aralik + rng.sample(aralik, adet - len(aralik))
    rng.shuffle(referanslar)
    return referanslar


def cizgi_degerleri(rng: random.Random, ref: int) -> list[int]:
    """Verilen referans için [doğru, küçük, büyük, ek] uzunluklarını (cm) tasarım kurallarına göre üretir."""
    while True:
        kucuk = ref + rng.choice([-1, 1]) * rng.choice([1, 2])
        buyuk = ref + rng.choice([-1, 1]) * rng.choice([4, 5, 6])
        ek = ref + rng.choice([-1, 1]) * rng.randint(3, 8)
        degerler = [ref, kucuk, buyuk, ek]
        if min(degerler) >= 1 and len(set(degerler)) == 4:
            return degerler


def aritmetik_degerleri(rng: random.Random, kullanilan_a: set[int]) -> tuple[int, int, list[int]]:
    """
    İki basamaklı × tek basamaklı bir çarpma ve [doğru, küçük, büyük, ek] şıklarını üretir.

    Küçük yanlış doğru sonuçtan %3–7, büyük yanlış %30–50, ek şık %10–25 uzaktadır.
    Küçük yanlış, doğru sonuçla aynı son basamağı taşır (fark 10'un katıdır); böylece
    yalnızca son basamağa bakılarak elenemez ve gerçekten inandırıcı bir çeldirici olur.
    İki basamaklı çarpan (a) havuzdaki her soruda farklıdır.
    """
    while True:
        a = rng.randint(12, 99)
        b = rng.randint(3, 9)
        if a in kullanilan_a:
            continue
        dogru = a * b

        kucuk_adaylari = [
            dogru + yon * 10 * kat
            for kat in (1, 2, 3)
            for yon in (-1, 1)
            if 0.03 <= 10 * kat / dogru <= 0.07
        ]
        if not kucuk_adaylari:
            continue
        kucuk = rng.choice(kucuk_adaylari)
        buyuk = round(dogru * (1 + rng.choice([-1, 1]) * rng.uniform(0.30, 0.50)))
        ek = round(dogru * (1 + rng.choice([-1, 1]) * rng.uniform(0.10, 0.25)))

        degerler = [dogru, kucuk, buyuk, ek]
        uzaklik = {rol: abs(d - dogru) / dogru for rol, d in zip(ROLLER, degerler)}
        if (
            min(degerler) >= 1
            and len(set(degerler)) == 4
            and 0.30 <= uzaklik["buyuk"] <= 0.50
            and 0.10 <= uzaklik["ek"] <= 0.25
        ):
            return a, b, degerler


# ---------------------------------------------------------------------------
# Soru havuzunun oluşturulması
# ---------------------------------------------------------------------------

def soru_olustur(
    soru_id: str,
    tur: str,
    soru_tr: str,
    soru_en: str,
    rol_degerleri: dict[str, tuple[str, str]],
    duzen: list[str],
) -> Soru:
    """rol_degerleri: rol -> (tr, en). duzen: A, B, C, D sırasındaki roller."""
    secenekler, harfler = {}, {}
    for harf, rol in zip(HARFLER, duzen):
        tr, en = rol_degerleri[rol]
        secenekler[harf] = Secenek(tr=tr, en=en, rol=rol)
        harfler[rol] = harf
    return Soru(soru_id, tur, soru_tr, soru_en, secenekler, harfler)


def soru_havuzu_olustur(tohum: int = TOHUM) -> list[Soru]:
    """60 soruyu (her türden 20) dengeli şık konumlarıyla üretir."""
    rng = random.Random(tohum)
    sorular = []

    # Çizgi
    gorulen = set()
    for i, (duzen, ref) in enumerate(zip(dengeli_duzenler(rng), dengeli_referanslar(rng)), 1):
        degerler = cizgi_degerleri(rng, ref)
        while tuple(degerler) in gorulen:
            degerler = cizgi_degerleri(rng, ref)
        gorulen.add(tuple(degerler))
        rol_degerleri = {rol: (f"{d} cm", f"{d} cm") for rol, d in zip(ROLLER, degerler)}
        sorular.append(soru_olustur(
            f"CZG-{i:02d}", "cizgi",
            f"Referans çizgi: {degerler[0]} cm", f"Reference line: {degerler[0]} cm",
            rol_degerleri, duzen,
        ))

    # Bilgi
    for i, (satir, duzen) in enumerate(zip(BILGI_SORULARI, dengeli_duzenler(rng)), 1):
        soru_tr, soru_en, *sik_ciftleri = satir
        rol_degerleri = dict(zip(ROLLER, sik_ciftleri))
        sorular.append(soru_olustur(
            f"BLG-{i:02d}", "bilgi",
            f"Soru: {soru_tr}", f"Question: {soru_en}",
            rol_degerleri, duzen,
        ))

    # Aritmetik
    kullanilan_a = set()
    for i, duzen in enumerate(dengeli_duzenler(rng), 1):
        a, b, degerler = aritmetik_degerleri(rng, kullanilan_a)
        kullanilan_a.add(a)
        rol_degerleri = {rol: (str(d), str(d)) for rol, d in zip(ROLLER, degerler)}
        sorular.append(soru_olustur(
            f"ART-{i:02d}", "aritmetik",
            f"Soru: {a} × {b} kaçtır?", f"Question: What is {a} × {b}?",
            rol_degerleri, duzen,
        ))

    return sorular


# ---------------------------------------------------------------------------
# Otomatik doğrulama (tasarım belgesi, Bölüm 3.3)
# ---------------------------------------------------------------------------

def _rol_degerleri(s: Soru) -> dict[str, str]:
    """Sorunun Türkçe şık metinlerini rol -> metin olarak döndürür."""
    return {rol: s.secenekler[harf].tr for rol, harf in s.harfler.items()}


def _genel_kurallar(s: Soru) -> None:
    """Her soru türü için geçerli yapı kuralları."""
    assert list(s.secenekler) == HARFLER, f"{s.id}: şıklar A–D değil"
    assert sorted(s.harfler) == sorted(ROLLER), f"{s.id}: roller eksik"
    for rol, harf in s.harfler.items():
        assert s.secenekler[harf].rol == rol, f"{s.id}: rol–harf eşlemesi tutarsız"
    assert len({o.tr for o in s.secenekler.values()}) == 4, f"{s.id}: Türkçe şıklar birbirinden farklı değil"
    assert len({o.en for o in s.secenekler.values()}) == 4, f"{s.id}: İngilizce şıklar birbirinden farklı değil"


def _cizgi_kurallari(s: Soru) -> None:
    d = {rol: int(metin.split()[0]) for rol, metin in _rol_degerleri(s).items()}
    ref = d["dogru"]
    assert s.soru_tr == f"Referans çizgi: {ref} cm", f"{s.id}: soru ile doğru şık uyuşmuyor"
    assert 5 <= ref <= 15, f"{s.id}: referans 5–15 cm dışında"
    assert 1 <= abs(d["kucuk"] - ref) <= 2, f"{s.id}: küçük yanlış 1–2 cm değil"
    assert 4 <= abs(d["buyuk"] - ref) <= 6, f"{s.id}: büyük yanlış 4–6 cm değil"
    assert abs(d["ek"] - ref) >= 3, f"{s.id}: ek şık doğruya 3 cm'den yakın"
    assert min(d.values()) >= 1, f"{s.id}: pozitif olmayan uzunluk"


def _aritmetik_kurallari(s: Soru) -> None:
    a, b = map(int, re.search(r"(\d+) × (\d+)", s.soru_tr).groups())
    assert 10 <= a <= 99 and 2 <= b <= 9, f"{s.id}: iki basamaklı × tek basamaklı değil"
    d = {rol: int(metin) for rol, metin in _rol_degerleri(s).items()}
    assert d["dogru"] == a * b, f"{s.id}: doğru şık hatalı"
    uzaklik = {rol: abs(d[rol] - d["dogru"]) / d["dogru"] for rol in ("kucuk", "buyuk", "ek")}
    assert 0.03 <= uzaklik["kucuk"] <= 0.07, f"{s.id}: küçük yanlış %3–7 değil"
    assert 0.30 <= uzaklik["buyuk"] <= 0.50, f"{s.id}: büyük yanlış %30–50 değil"
    assert 0.10 <= uzaklik["ek"] <= 0.25, f"{s.id}: ek şık %10–25 değil"
    assert d["kucuk"] % 10 == d["dogru"] % 10, f"{s.id}: küçük yanlışın son basamağı farklı"
    assert min(d.values()) >= 1, f"{s.id}: pozitif olmayan şık"


def _tur_kurallari(tur: str, tur_sorulari: list[Soru]) -> None:
    """Bir türün 20 sorusu birlikte: sayı, konum dengesi, tekrar."""
    assert len(tur_sorulari) == 20, f"{tur}: 20 soru bekleniyordu, {len(tur_sorulari)} var"
    for rol in ROLLER:
        sayim = Counter(s.harfler[rol] for s in tur_sorulari)
        assert all(sayim[h] == 5 for h in HARFLER), f"{tur}/{rol} konumları dengesiz: {dict(sayim)}"
    imzalar = {(s.soru_tr, tuple(s.secenekler[h].tr for h in HARFLER)) for s in tur_sorulari}
    assert len(imzalar) == 20, f"{tur}: tekrar eden soru var"


def dogrula(sorular: list[Soru]) -> None:
    """Soru havuzu tasarım kurallarına uymuyorsa AssertionError verir."""
    assert len(sorular) == 60, f"60 soru bekleniyordu, {len(sorular)} var"
    assert len({s.id for s in sorular}) == 60, "Soru kimlikleri tekrar ediyor"

    for tur in TURLER:
        _tur_kurallari(tur, [s for s in sorular if s.tur == tur])

    tur_kurali = {"cizgi": _cizgi_kurallari, "aritmetik": _aritmetik_kurallari}
    for s in sorular:
        _genel_kurallar(s)
        if s.tur in tur_kurali:
            tur_kurali[s.tur](s)


# ---------------------------------------------------------------------------
# Kaydetme ve özet
# ---------------------------------------------------------------------------

def kaydet(sorular: list[Soru], dosya: Path = CIKTI_DOSYASI) -> None:
    dosya.parent.mkdir(parents=True, exist_ok=True)
    with open(dosya, "w", encoding="utf-8") as f:
        json.dump({"tohum": TOHUM, "sorular": [asdict(s) for s in sorular]}, f, ensure_ascii=False, indent=2)


def ozet_yazdir(sorular: list[Soru]) -> None:
    for s in sorular:
        siklar = "  ".join(f"{h}) {s.secenekler[h].tr}" for h in HARFLER)
        roller = f"doğru {s.harfler['dogru']} · küçük {s.harfler['kucuk']} · büyük {s.harfler['buyuk']}"
        print(f"{s.id}  {s.soru_tr}\n        {siklar}   [{roller}]")


if __name__ == "__main__":
    sorular = soru_havuzu_olustur()
    dogrula(sorular)
    kaydet(sorular)
    ozet_yazdir(sorular)
    print(f"\n{len(sorular)} soru üretildi, bütün kontroller geçti. Kaydedildi: {CIKTI_DOSYASI}")