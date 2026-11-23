"""Inti perhitungan SKAKMAT: TOPSIS (penilaian individual) dan voting Borda (konsensus).

Tanpa dependensi luar. Semua fungsi murni sehingga mudah diuji (lihat test_gdss.py).
"""
import math

# Kriteria penilaian langkah catur. Skala nilai 1 sampai 5.
KRITERIA = [
    {"kode": "C1", "nama": "Keamanan raja", "bobot": 25, "jenis": "benefit"},
    {"kode": "C2", "nama": "Keamanan material", "bobot": 20, "jenis": "benefit"},
    {"kode": "C3", "nama": "Penguasaan pusat papan", "bobot": 20, "jenis": "benefit"},
    {"kode": "C4", "nama": "Peluang serangan", "bobot": 20, "jenis": "benefit"},
    {"kode": "C5", "nama": "Risiko serangan balik lawan", "bobot": 15, "jenis": "cost"},
]
NILAI_MIN, NILAI_MAKS = 1, 5


def validasi_nilai(skor, jumlah_alternatif):
    """skor: daftar [alternatif][kriteria] bilangan bulat 1..5. Mengembalikan pesan salah atau None."""
    if not isinstance(skor, list) or len(skor) != jumlah_alternatif:
        return "Jumlah baris penilaian tidak sesuai jumlah kandidat langkah."
    for baris in skor:
        if not isinstance(baris, list) or len(baris) != len(KRITERIA):
            return "Setiap kandidat harus dinilai pada semua kriteria."
        for v in baris:
            if isinstance(v, bool) or not isinstance(v, int) or not NILAI_MIN <= v <= NILAI_MAKS:
                return f"Nilai harus bilangan bulat {NILAI_MIN} sampai {NILAI_MAKS}."
    return None


def peringkat(nilai):
    """Peringkat 1 = nilai terbesar. Bila sama, indeks yang lebih kecil lebih dulu."""
    urut = sorted(range(len(nilai)), key=lambda i: (-nilai[i], i))
    hasil = [0] * len(nilai)
    for r, i in enumerate(urut, start=1):
        hasil[i] = r
    return hasil


def topsis(skor, kriteria=KRITERIA):
    """Hitung TOPSIS satu penilai. skor[i][j] = nilai alternatif i pada kriteria j."""
    m, n = len(skor), len(kriteria)
    bobot = [k["bobot"] / sum(c["bobot"] for c in kriteria) for k in kriteria]
    pembagi = [math.sqrt(sum(skor[i][j] ** 2 for i in range(m))) for j in range(n)]
    r = [[(skor[i][j] / pembagi[j]) if pembagi[j] else 0.0 for j in range(n)] for i in range(m)]
    y = [[r[i][j] * bobot[j] for j in range(n)] for i in range(m)]
    a_plus, a_min = [], []
    for j in range(n):
        kolom = [y[i][j] for i in range(m)]
        if kriteria[j]["jenis"] == "benefit":
            a_plus.append(max(kolom))
            a_min.append(min(kolom))
        else:
            a_plus.append(min(kolom))
            a_min.append(max(kolom))
    d_plus = [math.sqrt(sum((y[i][j] - a_plus[j]) ** 2 for j in range(n))) for i in range(m)]
    d_min = [math.sqrt(sum((y[i][j] - a_min[j]) ** 2 for j in range(n))) for i in range(m)]
    v = [(d_min[i] / (d_plus[i] + d_min[i])) if (d_plus[i] + d_min[i]) else 0.5 for i in range(m)]
    return {"r": r, "y": y, "a_plus": a_plus, "a_min": a_min,
            "d_plus": d_plus, "d_min": d_min, "v": v, "rank": peringkat(v)}


def borda(hasil_per_penilai, urutan_pemutus=0):
    """Konsensus Borda.

    hasil_per_penilai: daftar hasil topsis() satu per penilai.
    Bobot Borda untuk peringkat p dari n alternatif adalah n - p + 1 (3, 2, 1 untuk tiga kandidat).
    Poin alternatif i = jumlah (bobot Borda x skor preferensi) dari semua penilai.
    Nilai Borda = poin / jumlah poin seluruh alternatif.
    Bila nilai sama, kandidat dengan peringkat lebih baik menurut penilai urutan_pemutus
    (akun jabatan tertinggi) yang menang.
    """
    n = len(hasil_per_penilai[0]["v"])
    bobot = [n - p + 1 for p in range(1, n + 1)]
    poin = [0.0] * n
    hitung_peringkat = [[0] * n for _ in range(n)]   # [alternatif][peringkat-1]
    for h in hasil_per_penilai:
        for i in range(n):
            poin[i] += bobot[h["rank"][i] - 1] * h["v"][i]
            hitung_peringkat[i][h["rank"][i] - 1] += 1
    total = sum(poin)
    nilai = [(p / total) if total else 0.0 for p in poin]
    pemutus = hasil_per_penilai[urutan_pemutus]["rank"]
    urut = sorted(range(n), key=lambda i: (-round(nilai[i], 12), pemutus[i], i))
    rank = [0] * n
    for r, i in enumerate(urut, start=1):
        rank[i] = r
    return {"bobot_borda": bobot, "poin": poin, "nilai": nilai, "rank": rank,
            "pemenang": urut[0], "hitung_peringkat": hitung_peringkat}


# ------------------------------------------------------------------ gaya main (profil bobot)
# Nilai C1-C5 dihitung mesin dari papan, jadi semua decision maker melihat angka yang sama. Yang membuat
# peringkat mereka berbeda adalah GAYA MAIN: tiap akun memberi bobot berbeda pada kriteria yang sama
# (laporan: "ada yang condong menyerang, ada pula yang memilih bertahan"). TOPSIS dijalankan sekali per
# decision maker dengan bobot gayanya, lalu Borda menggabungkan peringkat-peringkat itu.
# Urutan bobot = urutan KRITERIA (C1..C5). Profil "seimbang" sama dengan bobot KRITERIA di atas.
PROFIL = {
    "menyerang": {"nama": "Menyerang", "bobot": [20, 15, 20, 30, 15]},
    "seimbang": {"nama": "Seimbang", "bobot": [25, 20, 20, 20, 15]},
    "bertahan": {"nama": "Bertahan", "bobot": [30, 30, 15, 10, 15]},
}


def kriteria_profil(gaya):
    """Salinan KRITERIA dengan bobot gaya tersebut (jenis benefit/cost tidak berubah)."""
    return [{**k, "bobot": b} for k, b in zip(KRITERIA, PROFIL[gaya]["bobot"])]


def validasi_matriks(matriks):
    """Matriks keputusan dari mesin: 1..n baris, tiap baris 5 bilangan 1..5 (boleh pecahan)."""
    if not isinstance(matriks, list) or not matriks:
        return "Matriks keputusan kosong."
    for baris in matriks:
        if not isinstance(baris, list) or len(baris) != len(KRITERIA):
            return "Setiap alternatif harus punya nilai pada semua kriteria."
        for v in baris:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not NILAI_MIN <= v <= NILAI_MAKS:
                return f"Nilai harus bilangan {NILAI_MIN} sampai {NILAI_MAKS}."
    return None


def konsensus_gaya(matriks, gaya_penilai, dukungan=None):
    """TOPSIS per decision maker (bobot = gayanya) lalu konsensus Borda.

    matriks[i][j]   : nilai alternatif i pada kriteria j (sama untuk semua penilai; dihitung mesin).
    gaya_penilai    : daftar gaya, satu per decision maker (kunci PROFIL).
    dukungan[i]     : berapa decision maker yang mengusulkan alternatif i (usulan ganda digabung).

    Poin dan nilai Borda dihitung oleh borda() yang sama dengan sebelumnya. Hanya aturan seri yang
    berbeda karena tidak ada lagi jabatan tertinggi: bila nilai Borda sama, menang yang (1) didukung
    lebih banyak usulan, lalu (2) jumlah peringkat TOPSIS-nya lebih kecil, lalu (3) diusulkan lebih dulu.
    """
    pesan = validasi_matriks(matriks)
    if pesan:
        raise ValueError(pesan)
    n = len(matriks)
    dukungan = list(dukungan) if dukungan else [1] * n
    # peringkat() memutus nilai V yang sama menurut indeks. Supaya seri itu diputus menurut dukungan
    # (bukan kebetulan urutan), alternatif diurutkan dulu: dukungan terbanyak, lalu yang diusulkan lebih dulu.
    # Hasil dipetakan kembali ke urutan asli sebelum dikembalikan.
    p = sorted(range(n), key=lambda i: (-dukungan[i], i))       # p[posisi] = indeks asli
    balik = [p.index(i) for i in range(n)]                       # balik[indeks asli] = posisi
    m = [matriks[i] for i in p]
    hasil = []
    for g in gaya_penilai:
        h = topsis(m, kriteria_profil(g))
        hasil.append({**h, **{kunci: [h[kunci][balik[i]] for i in range(n)]
                              for kunci in ("r", "y", "d_plus", "d_min", "v", "rank")}})
    k = borda(hasil)
    jumlah_peringkat = [sum(h["rank"][i] for h in hasil) for i in range(n)]
    urut = sorted(range(n), key=lambda i: (-round(k["nilai"][i], 12), -dukungan[i], jumlah_peringkat[i], i))
    rank = [0] * n
    for r, i in enumerate(urut, start=1):
        rank[i] = r
    k.update(rank=rank, pemenang=urut[0], dukungan=dukungan, jumlah_peringkat=jumlah_peringkat,
             aturan_seri="dukungan usulan, lalu jumlah peringkat TOPSIS, lalu urutan usulan")
    return {"topsis": hasil, "borda": k, "pemenang": urut[0],
            "pemenang_per_penilai": [h["rank"].index(1) for h in hasil]}
