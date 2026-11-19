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
from test_e2e import AKUN, NILAI, Klien, cek

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


def konsensus(klien):
    for u in AKUN:
        klien[u].minta("/api/nilai", {"skor": NILAI[u]})
    st, j = klien["kapten"].minta("/api/konsensus", {})
    return st, j


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
    st, j = k["analis1"].minta("/api/kasus")
    cek(st == 200 and j["engine"]["tersedia"] is False and j["engine"]["kode"] == "menunggu_konsensus"
        and j["engine"]["alasan"], "sebelum konsensus: engine ditahan dengan alasan")
    st, j = konsensus(k)
    cek(st == 200, "konsensus tetap berjalan seperti biasa")
    t = time.time()
    st, j = k["analis2"].minta("/api/kasus")
    e = j["engine"]
    cek(st == 200 and e["tersedia"] is True and len(e["kandidat"]) == 3, f"setelah konsensus: peringkat engine dikirim ({time.time() - t:.2f} s)")
    cek(all(isinstance(x["peringkat"], int) and 1 <= x["peringkat"] <= 3 for x in e["kandidat"]), "peringkat engine bilangan 1..3")
    cek(all((x["cp"] is None) != (x["mat"] is None) for x in e["kandidat"]), "tiap kandidat punya tepat satu nilai: cp atau mat")
    cek([x["langkah"] for x in e["kandidat"]] == j["kasus"]["kandidat"], "urutan kandidat engine = urutan kasus")
    cek(set(j) >= {"pengguna", "kasus", "kriteria", "status", "semua_sudah", "konsensus", "skor_saya", "topsis_saya", "individual"},
        "field lama /api/kasus tetap ada")
    print("      engine:", e["engine"], [(x["langkah"], x["cp"], x["mat"], x["peringkat"]) for x in e["kandidat"]])
    t = time.time()
    st, j2 = k["kapten"].minta("/api/kasus")
    cek(j2["engine"] == e and time.time() - t < 1.0, "permintaan berikutnya memakai cache (hasil sama, cepat)")
    # usulan kandidat
    st, j = k["analis1"].minta("/api/usul-kandidat", {"fen": AWAL})
    cek(st == 403, "analis tidak boleh meminta usulan kandidat")
    st, j = k["kapten"].minta("/api/usul-kandidat", {"fen": "bukan fen"})
    cek(st == 400 and j["galat"] == "Format FEN tidak valid.", "usulan: FEN rusak ditolak sebelum menyentuh engine")
    st, j = k["kapten"].minta("/api/usul-kandidat", {"fen": "8/8/8/8/8/8/8/8 w - - 0 1"})
    cek(st == 400 and "tidak ada raja" in j["galat"], f"usulan: posisi ilegal ditolak sebelum menyentuh engine: {j['galat']!r}")
    t = time.time()
    st, j = k["kapten"].minta("/api/usul-kandidat", {"fen": AWAL})
    cek(st == 200 and len(j["kandidat"]) == 3 and j["kandidat"] == sorted(j["kandidat"]) and all(x.startswith("1. ") for x in j["kandidat"]),
        f"usulan 3 kandidat urut abjad: {j.get('kandidat')} ({time.time() - t:.2f} s)")
    cek(mesin.validasi_kasus(AWAL, j["kandidat"]) is None, "kandidat usulan lolos validasi legalitas")
    st, j = k["kapten"].minta("/api/usul-kandidat", {"fen": "7k/8/8/8/8/8/8/K7 w - - 0 1"})
    cek(st == 400 and "remis" in j["galat"], f"usulan: posisi remis (material kurang) ditolak: {j['galat']!r}")
    # validasi legalitas di kasus-baru
    st, j = k["kapten"].minta("/api/kasus-baru", {"judul": "x", "fen": AWAL, "riwayat": "", "kandidat": ["e4", "e5", "Nf3"]})
    cek(st == 400 and "Kandidat 2" in j["galat"], f"kasus-baru: kandidat ilegal ditolak: {j['galat']!r}")
    st, j = k["kapten"].minta("/api/kasus-baru", {"judul": "x", "fen": "bukan fen", "riwayat": "", "kandidat": ["a", "b", "c"]})
    cek(st == 400 and j["galat"] == "Format FEN tidak valid.", "kasus-baru: pesan FEN rusak yang lama tidak berubah")
    st, j = k["kapten"].minta("/api/kasus-baru", {"judul": "x", "fen": "8/8/8/8/8/8/8/8 w - - 0 1", "riwayat": "", "kandidat": ["a", "b", "c"]})
    cek(st == 400 and "tidak ada raja" in j["galat"], "kasus-baru: posisi ilegal (bentuk benar) ditolak")
    st, j = k["kapten"].minta("/api/kasus-baru", {"judul": "Sah", "fen": AWAL, "riwayat": "", "kandidat": ["e4", "d4", "Nf3"]})
    cek(st == 200 and j == {"ok": True}, "kasus-baru: kandidat sah diterima, respons sama seperti dulu")


def engine_mati(k):
    st, j = konsensus(k)
    cek(st == 200, "konsensus berjalan normal tanpa engine")
    st, j = k["analis3"].minta("/api/kasus")
    e = j["engine"]
    cek(st == 200 and j["konsensus"] and len(j["individual"]) == 4, "hasil konsensus tetap lengkap tanpa engine")
    cek(e["tersedia"] is False and e["kode"] == "engine_tidak_ada" and "Stockfish" in e["alasan"], f"penanda tidak tersedia + alasan: {e}")
    cek("kandidat" not in e, "tidak ada angka engine palsu")
    st, j = k["kapten"].minta("/api/usul-kandidat", {"fen": AWAL})
    cek(st == 503 and "tidak tersedia" in j["galat"], f"usulan saat engine mati: 503 dengan pesan: {j['galat']!r}")
    st, j = k["kapten"].minta("/api/kasus-baru", {"judul": "x", "fen": AWAL, "riwayat": "", "kandidat": ["e4", "e5", "Nf3"]})
    cek(st == 400, "validasi legalitas tetap jalan walau engine mati (cukup python-chess)")


def engine_menggantung(k):
    st, _ = konsensus(k)
    batas = mesin.WAKTU_START + mesin.WAKTU_ANTRE + 3
    t = time.time()
    st, j = k["kapten"].minta("/api/kasus")
    d = time.time() - t
    cek(st == 200 and j["engine"]["tersedia"] is False and j["engine"]["kode"] == "engine_gagal",
        f"engine menggantung: /api/kasus tetap menjawab dengan penanda gagal ({d:.1f} s)")
    cek(d < batas, f"tidak menggantung: selesai dalam {d:.1f} s (< {batas:.0f} s)")
    t = time.time()
    st, j = k["analis1"].minta("/api/kasus")
    cek(j["engine"]["kode"] == "engine_gagal" and time.time() - t < 1.0,
        f"kegagalan diingat sebentar: permintaan berikutnya tidak menunggu lagi ({time.time() - t:.2f} s)")
    t = time.time()
    st, j = k["kapten"].minta("/api/usul-kandidat", {"fen": AWAL})
    d = time.time() - t
    cek(st == 503 and d < batas, f"usulan saat engine menggantung: 503 dalam {d:.1f} s")


def tanpa_pustaka(k):
    st, j = k["kapten"].minta("/api/kasus-baru", {"judul": "x", "fen": AWAL, "riwayat": "", "kandidat": ["e4", "e5", "Nf3"]})
    cek(st == 200 and "peringatan" in j and "tidak diperiksa" in j["peringatan"],
        "tanpa python-chess: kasus diterima seperti dulu, dengan peringatan legalitas tidak diperiksa")
    st, j = k["kapten"].minta("/api/kasus-baru", {"judul": "x", "fen": "bukan fen", "riwayat": "", "kandidat": ["a", "b", "c"]})
    cek(st == 400, "tanpa python-chess: pemeriksaan bentuk FEN lama tetap jalan")
    st, j = konsensus(k)
    st, j = k["analis1"].minta("/api/kasus")
    cek(st == 200 and j["engine"]["kode"] == "pustaka_tidak_ada" and j["engine"]["alasan"], f"tanpa python-chess: {j['engine']}")


def main():
    ganti_alamat()
    print("== unit legalitas")
    tes_unit()
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
