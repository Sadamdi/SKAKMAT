"""Tes inti perhitungan: bandingkan dengan hitungan NumPy independen (bila NumPy ada).

    python test_gdss.py
"""
import random

import gdss

CONTOH = [[4, 3, 4, 3, 2], [3, 4, 3, 2, 1], [5, 2, 3, 5, 4]]


def numpy_topsis(skor):
    import numpy as np
    x = np.array(skor, float)
    w = np.array([k["bobot"] for k in gdss.KRITERIA], float)
    w = w / w.sum()
    ben = np.array([k["jenis"] == "benefit" for k in gdss.KRITERIA])
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
    print("SEMUA TES LOLOS")


if __name__ == "__main__":
    main()
