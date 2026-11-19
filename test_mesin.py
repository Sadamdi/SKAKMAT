"""Tes validasi legalitas dan pembanding engine (mesin.py), termasuk saat engine mati atau menggantung.

    python test_mesin.py

Skenario yang butuh python-chess / Stockfish dilewati (dengan keterangan) bila belum terpasang.
"""
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import mesin
from test_e2e import AKUN, Klien, cek

PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"
AWAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def lewati(pesan):
    print("LEWAT " + pesan)


def tes_unit():
    if not mesin.pustaka_ada():
        return lewati("unit legalitas: python-chess tidak terpasang")
    v = mesin.validasi_kasus
    cek(v(AWAL, ["e4", "d4", "Nf3"]) is None, "kandidat sah diterima (SAN)")
    cek(v(AWAL, ["1. e4", "1. d4", "g1f3"]) is None, "nomor langkah dan notasi UCI diterima")
    p = v(AWAL, ["e4", "e5", "Nf3"])
    cek(p and "Kandidat 2" in p and "bukan langkah sah untuk putih" in p, f"langkah ilegal ditolak dengan alasan: {p!r}")
    p = v(AWAL, ["e4", "Ke2", "Nf3"])
    cek(p and "Kandidat 2" in p and "bukan langkah sah" in p, f"raja ke petak terisi ditolak: {p!r}")
    p = v(AWAL, ["e4", "hore", "Nf3"])
    cek(p and "tidak dikenali" in p, f"teks bukan notasi ditolak: {p!r}")
    p = v(AWAL, ["e4", "1. e4", "Nf3"])
    cek(p and "langkah yang sama" in p, f"kandidat ganda ditolak: {p!r}")
    p = v("4k3/8/8/8/8/8/8/1N3N1K w - - 0 1", ["Nd2", "Kg2", "Kh2"])
    cek(p and "ambigu" in p, f"langkah ambigu ditolak dengan saran: {p!r}")
    p = v("8/8/8/8/8/8/8/8 w - - 0 1", ["a", "b", "c"])
    cek(p and "tidak ada raja" in p, f"posisi tanpa raja ditolak (lolos pemeriksaan bentuk lama): {p!r}")
    p = v("rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2", ["Qh4#", "d6", "Nc6"])
    cek(p is None, "posisi hitam berjalan diterima")
    p = v("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3", ["a3", "b3", "c3"])
    cek(p and "selesai" in p, f"posisi skakmat ditolak: {p!r}")


GIUOCO = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2P2N2/PP1P1PPP/RNBQK2R w KQkq - 4 5"


def tes_kriteria():
    """C1-C5 dihitung dari posisi SETELAH langkah, skala 1..5, dan deterministik."""
    if not mesin.pustaka_ada():
        return lewati("unit kriteria: python-chess tidak terpasang")
    langkah = ["d2d4", "d2d3", "e1g1", "f3g5", "c4f7"]
    pakai_engine = bool(mesin.path_engine())
    mesin._cache_kriteria.clear()
    a = mesin.nilai_kriteria(GIUOCO, langkah)
    mesin._cache_kriteria.clear()
    b = mesin.nilai_kriteria(GIUOCO, langkah)
    cek(a["tersedia"] and a["sumber"]["mode"] == ("engine" if pakai_engine else "statis"),
        f"kriteria dihitung, mode {a['sumber']['mode']} ({a['sumber'].get('engine')})")
    cek([x["nilai"] for x in a["alternatif"]] == [x["nilai"] for x in b["alternatif"]],
        "deterministik: posisi sama -> C1..C5 sama persis (cache dikosongkan di antaranya)")
    cek(all(len(x["nilai"]) == 5 and all(1 <= v <= 5 for v in x["nilai"]) for x in a["alternatif"]),
        "semua nilai pada skala 1..5")
    cek([x["san"] for x in a["alternatif"]] == ["d4", "d3", "O-O", "Ng5", "Bxf7+"], "urutan alternatif = urutan masukan")
    n = {x["san"]: x["nilai"] for x in a["alternatif"]}
    for x in a["alternatif"]:
        print("      ", x["san"].ljust(6), x["nilai"])
    cek(n["O-O"][0] > n["d3"][0], "C1: rokade (perisai pion f2-g2-h2) lebih aman bagi raja daripada d3")
    cek(n["d4"][2] > n["Ng5"][2], "C3: d4 menguasai pusat lebih baik daripada Ng5 (kuda keluar dari pusat)")
    cek(n["Bxf7+"][1] < n["d3"][1], "C2: Bxf7+ (gajah dikorbankan untuk pion) lebih buruk materialnya daripada d3")
    cek(n["Bxf7+"][4] > n["d3"][4], "C5 (cost): Bxf7+ memberi lawan tangkapan menguntungkan -> risiko lebih besar")
    cek(a["alternatif"][4]["rincian"]["C4"]["memberi_skak"] is True, "C4 mencatat skak yang diberikan Bxf7+")
    # posisi sebelum langkah tidak dipakai: langkah berbeda -> posisi berbeda -> nilai berbeda
    cek(len({tuple(x["nilai"]) for x in a["alternatif"]}) == 5, "tiap langkah dinilai pada posisinya sendiri (nilai berbeda)")
    if pakai_engine:
        cek(all(x["engine"] and x["engine"]["kedalaman"] == mesin.KEDALAMAN_KRITERIA and not x["engine"]["terpotong_waktu"]
                for x in a["alternatif"]), f"analisis engine mencapai kedalaman {mesin.KEDALAMAN_KRITERIA} (tidak terpotong waktu)")
        t = time.time()
        mesin.nilai_kriteria(GIUOCO, langkah)
        cek(time.time() - t < 0.2, f"permintaan ulang memakai cache ({time.time() - t:.3f} s)")
    # jalur statis (tanpa engine) juga deterministik
    lama = os.environ.get("SKAKMAT_STOCKFISH")
    os.environ["SKAKMAT_STOCKFISH"] = "mati"
    try:
        s1 = mesin.nilai_kriteria(GIUOCO, langkah)
        s2 = mesin.nilai_kriteria(GIUOCO, langkah)
        cek(s1["sumber"]["mode"] == "statis" and s1["sumber"]["alasan_statis"]
            and [x["nilai"] for x in s1["alternatif"]] == [x["nilai"] for x in s2["alternatif"]],
            "tanpa engine: C2 statis, ditandai beserta alasan, tetap deterministik")
        m1, k1 = mesin.langkah_lawan("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2BPP3/2P2N2/PP3PPP/RNBQK2R b KQkq - 0 5")
        m2, _ = mesin.langkah_lawan("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2BPP3/2P2N2/PP3PPP/RNBQK2R b KQkq - 0 5")
        cek(m1 == m2 and "tanpa engine" in k1, f"balasan lawan tanpa engine deterministik: {m1} ({k1})")
    finally:
        if lama is None:
            os.environ.pop("SKAKMAT_STOCKFISH")
        else:
            os.environ["SKAKMAT_STOCKFISH"] = lama
    if pakai_engine:
        m, ket = mesin.langkah_lawan("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2BPP3/2P2N2/PP3PPP/RNBQK2R b KQkq - 0 5")
        cek(m is not None and "Stockfish" in ket, f"balasan lawan oleh Stockfish: {m} ({ket})")
    # usulan: validasi dan daftar langkah sah untuk papan
    cek(len(mesin.langkah_sah(AWAL)) == 20, "posisi awal: 20 langkah sah untuk papan interaktif")
    cek(mesin.validasi_usulan(AWAL, "e2e4")[0] is not None, "usulan UCI sah diterima")
    m, p = mesin.validasi_usulan(AWAL, "e2e5")
    cek(m is None and "tidak sah" in p, f"usulan ilegal ditolak: {p!r}")
    m, p = mesin.validasi_usulan(AWAL, "e7e5")
    cek(m is None and "putih" in p, f"menggerakkan bidak lawan ditolak: {p!r}")
    m, _ = mesin.validasi_usulan("8/P6k/8/8/8/8/8/K7 w - - 0 1", "a7a8")
    cek(m is not None and m.promotion == chess_menteri(), "promosi tanpa pilihan otomatis menjadi menteri")
    cek(mesin.validasi_usulan(AWAL, "x" * 50)[0] is None, "masukan terlalu panjang ditolak")


def chess_menteri():
    import chess
    return chess.QUEEN



def nyalakan(env_tambahan):
    tmp = tempfile.mkdtemp()
    env = dict(os.environ, SKAKMAT_DB=str(Path(tmp) / "uji.db"), **env_tambahan)
    srv = subprocess.Popen([sys.executable, "app.py", "--port", str(PORT)], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            urllib.request.urlopen(BASE + "/api/me", timeout=1)
            break
        except OSError:
            time.sleep(0.1)
    return srv


def masuk_semua():
    klien = {}
    for u, s in AKUN.items():
        k = Klien()
        k.minta("/api/login", {"username": u, "sandi": s})
        klien[u] = k
    return klien


USULAN = {"anggota1": "d2d4", "anggota2": "d2d3", "anggota3": "e1g1"}


def satu_ronde(klien):
    """Ketiga anggota mengusulkan; respons usulan terakhir (yang memicu penilaian) dikembalikan."""
    for u in ("anggota1", "anggota2"):
        klien[u].minta("/api/usul", {"langkah": USULAN[u]})
    t = time.time()
    st, j = klien["anggota3"].minta("/api/usul", {"langkah": USULAN["anggota3"]})
    return st, j, time.time() - t


def ganti_alamat():
    """Klien dari test_e2e memakai port 8765; arahkan ke port tes ini."""
    import test_e2e
    test_e2e.BASE = BASE


def skenario(nama, env, isi):
    print(f"\n== {nama}")
    srv = nyalakan(env)
    try:
        isi(masuk_semua())
    finally:
        srv.terminate()
        srv.wait(timeout=10)


def engine_hidup(k):
    st, j, d = satu_ronde(k)
    cek(st == 200 and j["dinilai"], f"ronde dinilai otomatis dengan engine dalam {d:.2f} s")
    kr = j["konsensus"]["kriteria"]
    cek(kr["sumber"]["mode"] == "engine" and kr["sumber"]["kedalaman"] == mesin.KEDALAMAN_KRITERIA,
        f"C1-C5 diukur dengan {kr['sumber']['engine']}, kedalaman {kr['sumber']['kedalaman']}")
    cek(all(e and (e["cp"] is None) != (e["mat"] is None) for e in kr["engine"]), "tiap alternatif punya nilai pembanding engine: cp atau mat")
    cek("Stockfish" in j["konsensus"]["lawan"]["sumber"], f"lawan dimainkan Stockfish: {j['konsensus']['lawan']}")
    mesin._cache_kriteria.clear()
    lokal = mesin.nilai_kriteria(AWAL_GIUOCO, [USULAN[u] for u in ("anggota1", "anggota2", "anggota3")])
    cek([x["nilai"] for x in lokal["alternatif"]] == kr["nilai"], "nilai C1-C5 dari server = hitungan ulang di proses lain (deterministik)")
    t = time.time()
    st, j2 = k["anggota1"].minta("/api/ronde")
    cek(st == 200 and time.time() - t < 0.5, f"GET /api/ronde tidak memanggil engine ({time.time() - t:.3f} s)")


def engine_mati(k):
    st, j, d = satu_ronde(k)
    kr = j["konsensus"]["kriteria"]
    cek(st == 200 and j["dinilai"] and kr["sumber"]["mode"] == "statis", f"tanpa engine: ronde tetap dinilai, C2 statis ({d:.2f} s)")
    cek("Stockfish" in kr["sumber"]["alasan_statis"], f"alasan ditampilkan: {kr['sumber']['alasan_statis']!r}")
    cek(all(e is None for e in kr["engine"]), "tidak ada angka engine palsu")
    cek("tanpa engine" in j["konsensus"]["lawan"]["sumber"], f"lawan memakai aturan sederhana: {j['konsensus']['lawan']}")
    st, j = k["anggota1"].minta("/api/usul", {"langkah": "a1a5"})
    cek(st == 400, "validasi legalitas tetap jalan walau engine mati (cukup python-chess)")


def engine_menggantung(k):
    batas = mesin.WAKTU_START + mesin.WAKTU_ANTRE + 3
    st, j, d = satu_ronde(k)
    cek(st == 200 and j["dinilai"] and j["konsensus"]["kriteria"]["sumber"]["mode"] == "statis",
        f"engine menggantung: ronde tetap dinilai (C2 statis) dalam {d:.1f} s")
    cek(d < batas, f"tidak menggantung: selesai dalam {d:.1f} s (< {batas:.0f} s), engine tidak ditunggu dua kali")
    st, j2 = k["anggota1"].minta("/api/ronde")
    sah = [x["uci"] for x in j2["langkah_sah"]]
    k["anggota1"].minta("/api/usul", {"langkah": sah[0]})
    k["anggota2"].minta("/api/usul", {"langkah": sah[1]})
    t = time.time()
    st, j = k["anggota3"].minta("/api/usul", {"langkah": sah[2]})
    d = time.time() - t
    cek(st == 200 and j["dinilai"] and d < 1.5, f"kegagalan diingat sebentar: ronde 2 dinilai tanpa menunggu engine lagi ({d:.2f} s)")


def tanpa_pustaka(k):
    st, j = k["anggota1"].minta("/api/ronde")
    cek(st == 200 and j["server"]["python_chess"] is False and j["langkah_sah"] == [],
        "tanpa python-chess: papan tetap tampil, tanpa langkah yang bisa dimainkan")
    st, j = k["anggota1"].minta("/api/usul", {"langkah": "d2d4"})
    cek(st == 503 and "python-chess" in j["galat"], f"tanpa python-chess: usulan ditolak 503 dengan alasan: {j['galat']!r}")
    st, j = k["anggota2"].minta("/api/konsensus", {})
    cek(st == 409, "tanpa python-chess: tidak ada penilaian palsu")


AWAL_GIUOCO = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2P2N2/PP1P1PPP/RNBQK2R w KQkq - 4 5"


def main():
    ganti_alamat()
    print("== unit legalitas")
    tes_unit()
    print("== unit kriteria C1-C5")
    tes_kriteria()
    if mesin.pustaka_ada() and mesin.path_engine():
        skenario("engine hidup (" + mesin.path_engine() + ")", {}, engine_hidup)
    else:
        lewati("skenario engine hidup: python-chess atau Stockfish belum terpasang")
    if mesin.pustaka_ada():
        skenario("engine dimatikan (SKAKMAT_STOCKFISH=mati)", {"SKAKMAT_STOCKFISH": "mati"}, engine_mati)
        tmp = Path(tempfile.mkdtemp())
        palsu = tmp / "engine-menggantung"
        palsu.write_text("#!/bin/sh\nexec sleep 60\n")
        palsu.chmod(0o755)
        skenario("engine menggantung (program palsu yang tidak menjawab)", {"SKAKMAT_STOCKFISH": str(palsu)}, engine_menggantung)
    else:
        lewati("skenario engine mati/menggantung: python-chess belum terpasang")
    # python-chess disembunyikan lewat paket 'chess' palsu yang gagal diimpor.
    blokir = Path(tempfile.mkdtemp())
    (blokir / "chess").mkdir()
    (blokir / "chess" / "__init__.py").write_text("raise ImportError('disembunyikan untuk tes')\n")
    skenario("python-chess tidak ada", {"PYTHONPATH": str(blokir)}, tanpa_pustaka)
    print("SEMUA TES MESIN LOLOS")


if __name__ == "__main__":
    main()
