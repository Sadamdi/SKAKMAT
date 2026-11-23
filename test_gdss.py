"""Tes inti perhitungan: bandingkan dengan hitungan NumPy independen (bila NumPy ada).

    python test_gdss.py
"""
import random

import gdss

CONTOH = [[4, 3, 4, 3, 2], [3, 4, 3, 2, 1], [5, 2, 3, 5, 4]]


def numpy_topsis(skor, kriteria=gdss.KRITERIA):
    import numpy as np
    x = np.array(skor, float)
    w = np.array([k["bobot"] for k in kriteria], float)
    w = w / w.sum()
    ben = np.array([k["jenis"] == "benefit" for k in kriteria])
    y = x / np.sqrt((x ** 2).sum(0)) * w
    ap = np.where(ben, y.max(0), y.min(0))
    an = np.where(ben, y.min(0), y.max(0))
    dp = np.sqrt(((y - ap) ** 2).sum(1))
    dn = np.sqrt(((y - an) ** 2).sum(1))
    return dn / (dp + dn)


def main():
    h = gdss.topsis(CONTOH)
    assert all(0 <= v <= 1 for v in h["v"])
    assert sorted(h["rank"]) == [1, 2, 3]
    try:
        import numpy as np
        for _ in range(200):
            s = [[random.randint(1, 5) for _ in range(5)] for _ in range(3)]
            if len({tuple(b) for b in s}) < 3:
                continue
            assert np.allclose(gdss.topsis(s)["v"], numpy_topsis(s), atol=1e-12), s
        print("TOPSIS cocok dengan NumPy pada 200 data acak")
    except ImportError:
        print("NumPy tidak terpasang: tes pembanding dilewati")

    # Borda: tiga penilai sepakat kandidat 0 terbaik
    a = gdss.topsis([[5, 5, 5, 5, 1], [3, 3, 3, 3, 3], [1, 1, 1, 1, 5]])
    b = gdss.topsis([[4, 5, 4, 4, 2], [3, 3, 3, 3, 3], [2, 2, 2, 2, 4]])
    c = gdss.topsis([[5, 4, 5, 3, 1], [2, 3, 2, 3, 3], [1, 2, 1, 2, 5]])
    k = gdss.borda([a, b, c])
    assert k["pemenang"] == 0 and k["rank"] == [1, 2, 3]
    assert abs(sum(k["nilai"]) - 1) < 1e-12 and k["bobot_borda"] == [3, 2, 1]

    # Seri: dua kandidat identik, pemenang ditentukan peringkat penilai pemutus (indeks 0)
    sama = gdss.topsis([[3, 3, 3, 3, 3], [3, 3, 3, 3, 3], [1, 1, 1, 1, 5]])
    kk = gdss.borda([sama])
    assert kk["pemenang"] == 0
    # Validasi masukan
    assert gdss.validasi_nilai(CONTOH, 3) is None
    assert gdss.validasi_nilai([[0, 1, 1, 1, 1]] * 3, 3)
    assert gdss.validasi_nilai([[True, 1, 1, 1, 1]] * 3, 3)
    assert gdss.validasi_nilai(CONTOH[:2], 3)
    tes_gaya()
    print("SEMUA TES LOLOS")


# Contoh dari pencarian acak (seed 7): profil seimbang memilih alternatif 0, tapi menyerang dan bertahan
# sama-sama memilih alternatif 2, sehingga keputusan kelompok (Borda) = alternatif 2.
BEDA = [[3, 3, 4, 1, 1], [2, 3, 1, 1, 1], [5, 3, 1, 2, 1]]
GAYA = ["menyerang", "seimbang", "bertahan"]


def tes_gaya():
    """TOPSIS dengan tiga profil bobot dan Borda yang benar-benar menggabungkan peringkat berbeda."""
    # bobot profil seimbang = bobot KRITERIA lama, jadi TOPSIS-nya identik dengan topsis() lama
    assert [k["bobot"] for k in gdss.kriteria_profil("seimbang")] == [k["bobot"] for k in gdss.KRITERIA]
    assert gdss.topsis(CONTOH, gdss.kriteria_profil("seimbang")) == gdss.topsis(CONTOH)
    assert all(k["jenis"] == b["jenis"] for g in gdss.PROFIL for k, b in zip(gdss.kriteria_profil(g), gdss.KRITERIA))
    assert gdss.kriteria_profil("menyerang")[4]["jenis"] == "cost"

    # tiga profil -> tiga peringkat berbeda pada matriks yang sama
    h = {g: gdss.topsis(BEDA, gdss.kriteria_profil(g)) for g in GAYA}
    print("Peringkat per profil:", {g: h[g]["rank"] for g in GAYA})
    assert h["seimbang"]["rank"] == [1, 3, 2]
    assert h["menyerang"]["rank"] == [2, 3, 1] and h["bertahan"]["rank"] == [2, 3, 1]
    assert h["seimbang"]["v"] != h["menyerang"]["v"] != h["bertahan"]["v"]

    # Borda memilih berbeda dari TOPSIS tunggal (profil seimbang / bobot lama)
    k = gdss.konsensus_gaya(BEDA, GAYA)
    tunggal = gdss.topsis(BEDA)["rank"].index(1)
    print(f"Pemenang TOPSIS tunggal (seimbang) = {tunggal}, pemenang Borda = {k['pemenang']}, "
          f"nilai Borda = {[round(x, 4) for x in k['borda']['nilai']]}")
    assert tunggal == 0 and k["pemenang"] == 2, "Borda harus bisa berbeda dari TOPSIS tunggal"
    assert k["pemenang_per_penilai"] == [2, 0, 2]
    # hasil konsensus_gaya = borda() lama atas topsis per gaya (poin dan nilai sama persis)
    lama = gdss.borda([h[g] for g in GAYA])
    assert lama["poin"] == k["borda"]["poin"] and lama["nilai"] == k["borda"]["nilai"]

    # Seberapa sering profil berbeda pada matriks acak (bukti Borda tidak sekadar mengulang satu TOPSIS)
    acak = random.Random(7)
    beda_peringkat = beda_tunggal = total = 0
    for _ in range(5000):
        m = [[acak.randint(1, 5) for _ in range(5)] for _ in range(3)]
        if len({tuple(b) for b in m}) < 3:
            continue
        total += 1
        kk = gdss.konsensus_gaya(m, GAYA)
        beda_peringkat += len({tuple(t["rank"]) for t in kk["topsis"]}) > 1
        beda_tunggal += kk["pemenang"] != gdss.topsis(m)["rank"].index(1)
    print(f"Dari {total} matriks acak: peringkat tiga profil tidak seragam pada {beda_peringkat}, "
          f"pemenang Borda berbeda dari TOPSIS tunggal pada {beda_tunggal}")
    assert beda_peringkat > total * 0.3 and beda_tunggal > 0

    try:
        import numpy as np
        for _ in range(200):
            m = [[round(acak.uniform(1, 5), 4) for _ in range(5)] for _ in range(3)]
            kk = gdss.konsensus_gaya(m, GAYA, dukungan=[acak.randint(1, 3) for _ in range(3)])
            for t, g in zip(kk["topsis"], GAYA):
                assert np.allclose(t["v"], numpy_topsis(m, gdss.kriteria_profil(g)), atol=1e-12), (m, g)
        print("TOPSIS tiap profil cocok dengan NumPy pada 200 matriks pecahan acak")
    except ImportError:
        print("NumPy tidak terpasang: pembanding TOPSIS per profil dilewati")

    # usulan ganda: dua orang mengusulkan langkah sama -> satu alternatif, dukungan 2
    dua = gdss.konsensus_gaya([[3, 3, 3, 3, 3], [4, 2, 4, 4, 3]], GAYA, dukungan=[2, 1])
    assert len(dua["borda"]["nilai"]) == 2 and dua["borda"]["dukungan"] == [2, 1]
    assert sorted(dua["borda"]["rank"]) == [1, 2]
    # seri sempurna: aturan seri pertama = dukungan usulan
    seri = gdss.konsensus_gaya([[3, 3, 3, 3, 3], [3, 3, 3, 3, 3]], GAYA, dukungan=[1, 2])
    assert seri["pemenang"] == 1
    assert seri["topsis"][0]["v"] == [0.5, 0.5] and seri["topsis"][0]["rank"] == [2, 1]
    seri = gdss.konsensus_gaya([[3, 3, 3, 3, 3], [3, 3, 3, 3, 3]], GAYA, dukungan=[1, 1])
    assert seri["pemenang"] == 0
    # pengurutan internal tidak mengubah hasil bila dukungan sama: identik dengan topsis() langsung
    acak2 = [[4.2, 1.3, 2.2, 3.9, 2.0], [2.0, 4.4, 3.1, 1.7, 1.2], [3.3, 3.0, 4.6, 2.4, 3.8]]
    a = gdss.konsensus_gaya(acak2, GAYA, dukungan=[1, 2, 1])
    for t, g in zip(a["topsis"], GAYA):
        langsung = gdss.topsis(acak2, gdss.kriteria_profil(g))
        assert all(abs(x - y) < 1e-12 for x, y in zip(t["v"], langsung["v"])) and t["rank"] == langsung["rank"], g
    # suara bulat: satu alternatif saja
    satu = gdss.konsensus_gaya([[2.5, 3.1, 4.0, 1.2, 2.2]], GAYA, dukungan=[3])
    assert satu["pemenang"] == 0 and satu["borda"]["rank"] == [1]
    # nilai pecahan dari mesin diterima, di luar 1..5 ditolak
    assert gdss.validasi_matriks([[1.5, 2.25, 3, 4.75, 5]]) is None
    assert gdss.validasi_matriks([[0.5, 2, 3, 4, 5]]) and gdss.validasi_matriks([[True, 2, 3, 4, 5]])
    assert gdss.validasi_matriks([]) and gdss.validasi_matriks([[1, 2, 3]])
    print("TES GAYA + BORDA LOLOS")


if __name__ == "__main__":
    main()
