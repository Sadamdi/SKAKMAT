"""Tes ujung ke ujung: jalankan server pada basis data sementara, lalu uji login, usulan langkah lewat API,
penilaian otomatis (C1-C5 -> TOPSIS per gaya -> Borda), ronde berikutnya, akses setara, dan migrasi
basis data lama.

    .venv/bin/python test_e2e.py      # butuh python-chess; Stockfish opsional

Catatan: tes ini hanya memanggil API. Tampilan (DOM/CSS/JS) diperiksa terpisah di browser.
"""
import http.cookiejar
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import gdss

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"
AKUN = {"anggota1": "anggota123-1", "anggota2": "anggota123-2", "anggota3": "anggota123-3"}
GAYA = {"anggota1": "menyerang", "anggota2": "seimbang", "anggota3": "bertahan"}
AWAL = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2P2N2/PP1P1PPP/RNBQK2R w KQkq - 4 5"


class Klien:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def minta(self, path, body=None, origin=None, mentah=None):
        data = mentah if mentah is not None else (None if body is None else json.dumps(body).encode())
        req = urllib.request.Request(BASE + path, data=data,
                                     headers={"Content-Type": "application/json"} if data is not None else {})
        if origin:
            req.add_header("Origin", origin)
        try:
            with self.op.open(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")


def cek(kondisi, pesan):
    print(("OK   " if kondisi else "GAGAL ") + pesan)
    if not kondisi:
        raise SystemExit(1)


def nyalakan(db, port=PORT, env_tambahan=None, tangkap=False):
    """tangkap=True hanya untuk server berumur pendek: keluaran yang tidak dibaca bisa memenuhi pipa."""
    env = dict(os.environ, SKAKMAT_DB=str(db), **(env_tambahan or {}))
    keluar = subprocess.PIPE if tangkap else subprocess.DEVNULL
    srv = subprocess.Popen([sys.executable, "app.py", "--port", str(port)], env=env,
                           stdout=keluar, stderr=subprocess.STDOUT, text=True)
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
            break
        except OSError:
            if srv.poll() is not None:
                break
            time.sleep(0.1)
    return srv


def masuk_semua():
    klien = {}
    for u, s in AKUN.items():
        k = Klien()
        st, j = k.minta("/api/login", {"username": u, "sandi": s})
        klien[u] = (k, st, j)
    return klien


def alur(klien):
    a1, a2, a3 = klien["anggota1"], klien["anggota2"], klien["anggota3"]
    st, j = a1.minta("/api/ronde")
    cek(st == 200 and j["kasus"]["fen"] == AWAL and j["kasus"]["nomor"] == 1 and len(j["langkah_sah"]) > 20
        and not any(p["sudah"] for p in j["peserta"]), f"ronde 1 dimulai di posisi awal, {len(j['langkah_sah'])} langkah sah dikirim ke papan")
    cek(all(set(x) == {"dari", "ke", "uci", "san"} for x in j["langkah_sah"]), "langkah sah berisi petak asal/tujuan untuk papan")
    st, j = a1.minta("/api/usul", {"langkah": "d2d5"})
    cek(st == 400 and "tidak sah" in j["galat"], f"usulan ilegal ditolak: {j.get('galat')!r}")
    st, j = a1.minta("/api/usul", {"langkah": "e5e4"})
    cek(st == 400, "menggerakkan bidak lawan (hitam) ditolak")
    for isi in ({"langkah": 42}, {"langkah": ["d2d4"]}, {}, None):
        st, _ = a1.minta("/api/usul", isi) if isi is not None else a1.minta("/api/usul", mentah=b"bukan json")
        if st != 400:
            break
    cek(st == 400, "usulan bukan teks / bukan JSON ditolak (400)")
    st, _ = a2.minta("/api/konsensus", {})
    cek(st == 403, "anggota biasa tidak boleh menjalankan konsensus (403)")
    st, _ = a1.minta("/api/konsensus", {})
    cek(st == 409, "Ketua pun ditolak (409) selama usulan belum lengkap")
    st, j = a1.minta("/api/usul", {"langkah": "d2d3"})
    cek(st == 200 and j["usulan"]["san"] == "d3" and j["dinilai"] is False, "anggota1 mengusulkan d3")
    st, j = a1.minta("/api/usul", {"langkah": "d2d4"})
    cek(st == 200 and j["usulan"]["san"] == "d4", "anggota1 mengganti usulan menjadi d4 sebelum penilaian")
    st, j = a2.minta("/api/ronde")
    cek(st == 200 and j["usulan_saya"] is None and j["hasil_terakhir"] is None
        and [p["sudah"] for p in j["peserta"]] == [True, False, False] and "d2d4" not in json.dumps(j["peserta"]),
        "anggota2 melihat anggota1 sudah mengusulkan, tapi tidak melihat langkahnya")
    st, j = a2.minta("/api/usul", {"langkah": "d4"})
    cek(st == 200 and j["usulan"]["uci"] == "d2d4" and j["dinilai"] is False, "anggota2 mengusulkan langkah yang sama (SAN diterima)")
    t = time.time()
    st, j = a3.minta("/api/usul", {"langkah": "e1g1"})
    d = time.time() - t
    cek(st == 200 and j["penilaian_siap"] is True and j["dinilai"] is False and "konsensus" not in j
        and "borda" not in json.dumps(j), f"usulan ketiga menyiapkan penilaian individual ({d:.2f} s); konsensus belum dijalankan")
    for u, kl in klien.items():
        st, jr = kl.minta("/api/ronde")
        cek(st == 200 and jr["penilaian"] and len(jr["penilaian"]["topsis"]) == 3 and jr["konsensus"] is None
            and jr["hasil_terakhir"] is None and jr["bisa_konsensus"] == (u == "anggota1") and "borda" not in json.dumps(jr["penilaian"]),
            f"{u} melihat penilaian individual ketiga anggota (tanpa Borda); tombol konsensus hanya untuk Ketua")
    for u in ("anggota2", "anggota3"):
        st, _ = klien[u].minta("/api/konsensus", {})
        cek(st == 403, f"{u} (bukan Ketua) ditolak menjalankan konsensus (403)")
    st, j = a1.minta("/api/konsensus", {})
    cek(st == 200 and j["konsensus"], "Ketua menjalankan konsensus Borda")
    st, _ = a1.minta("/api/konsensus", {})
    cek(st == 409, "konsensus kedua pada ronde yang sama ditolak (409)")
    k = j["konsensus"]
    alt = k["alternatif"]
    cek([a["san"] for a in alt] == ["d4", "O-O"] and [a["dukungan"] for a in alt] == [2, 1],
        "usulan ganda digabung: 2 alternatif, dukungan d4 = 2, O-O = 1")
    nilai = k["kriteria"]["nilai"]
    cek(len(nilai) == 2 and all(len(b) == 5 and all(1 <= v <= 5 for v in b) for b in nilai),
        f"C1-C5 tersimpan per alternatif ({k['kriteria']['sumber']['mode']}): {nilai}")
    cek([t["gaya"] for t in k["topsis"]] == ["menyerang", "seimbang", "bertahan"]
        and all(t["hasil"]["rank"] == gdss.topsis(nilai, gdss.kriteria_profil(t["gaya"]))["rank"] for t in k["topsis"]),
        "tiga peringkat TOPSIS (satu per gaya) = hitungan independen")
    ref = gdss.konsensus_gaya(nilai, ["menyerang", "seimbang", "bertahan"], [2, 1])
    cek(all(abs(a - b) < 1e-12 for a, b in zip(ref["borda"]["nilai"], k["borda"]["nilai"]))
        and ref["borda"]["rank"] == k["borda"]["rank"] and alt[ref["pemenang"]]["uci"] == k["pemenang"]["uci"],
        f"hasil Borda = hitungan independen (pemenang {k['pemenang']['san']})")
    cek(k["lawan"] and k["lawan"]["san"] and k["lawan"]["sumber"], f"lawan membalas otomatis: {k['lawan']['san']} ({k['lawan']['sumber']})")
    for u, kl in klien.items():
        st, j = kl.minta("/api/ronde")
        h = j["hasil_terakhir"]
        cek(st == 200 and h and h["kasus_id"] == k["kasus_id"] and len(h["topsis"]) == 3
            and sorted(sum((a["pengusul"] for a in h["alternatif"]), [])) == [p["id"] for p in j["peserta"]],
            f"{u} melihat hasil ronde 1 beserta usulan tiap anggota")
    cek(j["kasus"]["nomor"] == 2 and j["kasus"]["fen"] != AWAL and len(j["kasus"]["riwayat"]) == 10
        and j["konsensus"] is None and not any(p["sudah"] for p in j["peserta"]),
        f"ronde 2 dibuka otomatis: {j['kasus']['riwayat_teks']}")
    st, _ = a1.minta("/api/konsensus", {})
    cek(st == 409, "ronde 2 belum bisa dinilai sebelum ada usulan")
    st, j = a3.minta("/api/ulang", {})
    cek(st == 200 and j["kasus"]["nomor"] == 1 and j["kasus"]["fen"] == AWAL, "semua akun boleh memulai ronde baru (anggota3)")
    st, j = a2.minta("/api/ulang", {})
    st, j2 = a1.minta("/api/ronde")
    cek(st == 200 and j2["kasus"]["permainan"] == j["kasus"]["permainan"] and j2["hasil_terakhir"] is None,
        "semua akun boleh memulai ronde baru (anggota2); hasil permainan lama tidak terbawa")
    # dua usulan terakhir masuk bersamaan: penilaian hanya boleh terjadi sekali
    import threading
    a1.minta("/api/usul", {"langkah": "d2d4"})
    hasil = {}
    th = [threading.Thread(target=lambda u, m: hasil.__setitem__(u, klien[u].minta("/api/usul", {"langkah": m})),
                           args=(u, m)) for u, m in (("anggota2", "d2d3"), ("anggota3", "b2b4"))]
    [t.start() for t in th]
    [t.join() for t in th]
    siap = [j.get("penilaian_siap") for st, j in hasil.values()]
    st, j = a1.minta("/api/ronde")
    cek(sorted(siap) == [False, True] and j["kasus"]["nomor"] == 1 and len(j["penilaian"]["alternatif"]) == 3,
        "dua usulan serentak: penilaian individual dibuat tepat sekali")
    a1.minta("/api/konsensus", {})
    st, j = a1.minta("/api/ronde")
    cek(j["kasus"]["nomor"] == 2 and len(j["hasil_terakhir"]["alternatif"]) == 3,
        "konsensus Ketua membuka tepat satu ronde berikutnya")


def main():
    try:
        import chess  # noqa: F401
    except ImportError:
        raise SystemExit("Tes ini butuh python-chess. Jalankan dengan: .venv/bin/python test_e2e.py")
    tmp = Path(tempfile.mkdtemp())
    srv = nyalakan(tmp / "uji.db")
    try:
        anon = Klien()
        cek(anon.minta("/api/ronde")[0] == 401, "tanpa login ditolak (401)")
        cek(anon.minta("/api/login", {"username": "anggota1", "sandi": "salah"})[0] == 401, "sandi salah ditolak")
        cek(anon.minta("/api/login", {"username": "kapten", "sandi": "kapten123"})[0] == 401, "akun kapten sudah tidak ada")
        klien = {}
        for u, (k, st, j) in masuk_semua().items():
            cek(st == 200 and j["pengguna"]["username"] == u and j["pengguna"]["gaya"] == GAYA[u]
                and "tingkat" not in j["pengguna"], f"login {u} (gaya {GAYA[u]}, tanpa tingkat jabatan)")
            klien[u] = k
        st, j = klien["anggota1"].minta("/api/login", {"username": "anggota1", "sandi": "anggota123-1"}, origin="http://evil.example")
        cek(st == 403, "permintaan POST dengan Origin asing ditolak")
        st, j = klien["anggota1"].minta("/api/usul", {"langkah": "d2d4"}, origin="http://evil.example")
        cek(st == 403, "usulan dengan Origin asing ditolak")
        lama = [klien["anggota1"].minta(p, {})[0] for p in ("/api/nilai", "/api/kasus-baru", "/api/usul-kandidat")]
        cek(lama == [410, 410, 410] and klien["anggota1"].minta("/api/kasus")[0] == 410, "endpoint alur lama dinonaktifkan (410)")
        alur(klien)
        try:
            urllib.request.urlopen(BASE + "/..%2fapp.py")
            cek(False, "path traversal harus ditolak")
        except urllib.error.HTTPError as e:
            cek(e.code == 404, "path traversal ditolak (404)")
    finally:
        srv.terminate()
        srv.wait(timeout=10)
    migrasi()
    akhir_permainan()
    print("SEMUA TES UJUNG KE UJUNG LOLOS")


def migrasi():
    """Basis data skema lama (dengan Kapten, tingkat, dan tabel penilaian) tidak membuat aplikasi mati."""
    tmp = Path(tempfile.mkdtemp())
    db = tmp / "lama.db"
    with sqlite3.connect(db) as c:
        c.executescript("""
        CREATE TABLE pengguna(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, nama TEXT NOT NULL,
            peran TEXT NOT NULL, tingkat INTEGER NOT NULL, garam BLOB NOT NULL, sandi TEXT NOT NULL);
        CREATE TABLE kasus(id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, fen TEXT NOT NULL,
            riwayat TEXT NOT NULL, kandidat TEXT NOT NULL, dibuat REAL NOT NULL);
        CREATE TABLE penilaian(kasus_id INTEGER, pengguna_id INTEGER, skor TEXT, waktu REAL);
        INSERT INTO pengguna VALUES(1,'kapten','Kapten','kapten',1,x'00','x');
        """)
    global BASE
    asli, BASE = BASE, f"http://127.0.0.1:{PORT + 2}"
    srv = nyalakan(db, PORT + 2, tangkap=True)
    try:
        cadangan = list(tmp.glob("lama.db.lama-*"))
        k = Klien()
        st, j = k.minta("/api/login", {"username": "anggota1", "sandi": "anggota123-1"})
        cek(srv.poll() is None and st == 200, "basis data skema lama dimigrasi otomatis: server hidup, akun baru bisa masuk")
        with sqlite3.connect(cadangan[0]) as c:
            ada = c.execute("SELECT username FROM pengguna").fetchone()[0]
        cek(len(cadangan) == 1 and ada == "kapten", f"file lama dicadangkan utuh: {cadangan[0].name}")
    finally:
        srv.terminate()
        out = srv.communicate(timeout=10)[0]
        BASE = asli
    cek("dicadangkan" in out, "server memberi tahu bahwa basis data lama dicadangkan")


def akhir_permainan():
    """Ronde yang berakhir skakmat: tidak ada balasan lawan, tidak ada ronde baru, usulan dikunci.
    Posisi seperti ini tidak bisa dibuat lewat API (tidak ada input FEN), jadi fungsi app dipanggil langsung."""
    os.environ["SKAKMAT_DB"] = str(Path(tempfile.mkdtemp()) / "akhir.db")
    import importlib
    import app
    importlib.reload(app)
    app.siapkan_db()
    with app.db() as c:
        # putih: Qh5xf7# tersedia (Scholar's mate)
        app.buat_ronde(c, 1, 9, "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4",
                       ["e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6"])
        ids = [p["id"] for p in app.peserta(c)]
        kasus = app.kasus_aktif(c)
        for pid, m in zip(ids, ["h5f7", "h5f7", "d2d3"]):
            c.execute("INSERT INTO usulan VALUES(?,?,?,?,?)", (kasus["id"], pid, m, "-", time.time()))
        k, galat = app.jalankan_penilaian(c, kasus)
        cek(galat is None and k["pemenang"]["san"] == "Qxf7#" and k["akhir"] == "Skakmat. Tim menang." and k["lawan"] is None
            and app.kasus_aktif(c)["id"] == kasus["id"], "langkah pemenang skakmat: permainan selesai, tanpa balasan lawan dan ronde baru")
        cek(k["kriteria"]["nilai"][0][1] == 5.0 and k["kriteria"]["nilai"][0][4] == 1.0, "langkah skakmat dinilai maksimal (C2 = 5, risiko C5 = 1)")
        # lawan yang memberi skakmat: ronde berikutnya langsung ditandai selesai
        app.buat_ronde(c, 2, 1, "rnbqkbnr/pppp1ppp/8/4p3/8/5P2/PPPPP1PP/RNBQKBNR w KQkq - 0 2", ["f3", "e5"])
        kasus = app.kasus_aktif(c)
        for pid in ids:
            c.execute("INSERT INTO usulan VALUES(?,?,?,?,?)", (kasus["id"], pid, "g2g4", "g4", time.time()))
        k, galat = app.jalankan_penilaian(c, kasus)
        baru = app.kasus_aktif(c)
        cek(galat is None and len(k["alternatif"]) == 1 and k["alternatif"][0]["dukungan"] == 3 and k["lawan"]["san"] == "Qh4#"
            and baru["selesai"] == "Skakmat. Tim kalah." and app.mesin.langkah_sah(baru["fen"]) == [],
            "suara bulat (1 alternatif) tetap dinilai; lawan memberi skakmat -> ronde ditandai selesai")


if __name__ == "__main__":
    main()
