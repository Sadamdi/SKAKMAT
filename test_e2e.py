"""Tes ujung ke ujung: jalankan server pada basis data sementara, lalu uji alur login, penilaian,
hak akses konsensus, dan hasil yang terlihat semua akun.

    python test_e2e.py
"""
import http.cookiejar
import json
import os
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
AKUN = {"kapten": "kapten123", "analis1": "analis123-1", "analis2": "analis123-2", "analis3": "analis123-3"}
NILAI = {
    "kapten": [[4, 4, 4, 4, 2], [3, 3, 3, 3, 1], [5, 2, 3, 5, 4]],
    "analis1": [[3, 4, 4, 3, 2], [4, 4, 3, 2, 1], [4, 3, 3, 5, 4]],
    "analis2": [[5, 3, 4, 4, 3], [3, 4, 4, 3, 2], [4, 2, 3, 4, 5]],
    "analis3": [[4, 4, 3, 3, 2], [3, 3, 4, 2, 2], [5, 3, 2, 5, 3]],
}


class Klien:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def minta(self, path, body=None, origin=None):
        req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"} if body is not None else {})
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


def main():
    tmp = tempfile.mkdtemp()
    env = dict(os.environ, SKAKMAT_DB=str(Path(tmp) / "uji.db"))
    srv = subprocess.Popen([sys.executable, "app.py", "--port", str(PORT)], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(BASE + "/", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        anon = Klien()
        cek(anon.minta("/api/kasus")[0] == 401, "tanpa login ditolak (401)")
        cek(anon.minta("/api/login", {"username": "kapten", "sandi": "salah"})[0] == 401, "sandi salah ditolak")
        klien = {}
        for u, s in AKUN.items():
            k = Klien()
            st, j = k.minta("/api/login", {"username": u, "sandi": s})
            cek(st == 200 and j["pengguna"]["username"] == u, f"login {u}")
            klien[u] = k
        st, j = klien["kapten"].minta("/api/login", {"username": "kapten", "sandi": "kapten123"}, origin="http://evil.example")
        cek(st == 403, "permintaan POST dengan Origin asing ditolak")
        # penilaian tidak valid
        st, _ = klien["analis1"].minta("/api/nilai", {"skor": [[9, 1, 1, 1, 1]] * 3})
        cek(st == 400, "nilai di luar 1..5 ditolak")
        # konsensus sebelum lengkap
        st, j = klien["kapten"].minta("/api/konsensus", {})
        cek(st == 409, "konsensus sebelum semua menilai ditolak")
        for u in ("analis1", "analis2", "analis3"):
            st, _ = klien[u].minta("/api/nilai", {"skor": NILAI[u]})
            cek(st == 200, f"{u} mengirim penilaian")
        st, j = klien["analis1"].minta("/api/konsensus", {})
        cek(st == 403, "analis tidak boleh menjalankan konsensus")
        st, j = klien["kapten"].minta("/api/konsensus", {})
        cek(st == 409, "konsensus ditolak selama Kapten belum menilai")
        st, _ = klien["kapten"].minta("/api/nilai", {"skor": NILAI["kapten"]})
        cek(st == 200, "kapten mengirim penilaian")
        st, j = klien["kapten"].minta("/api/konsensus", {})
        cek(st == 200, "Kapten menjalankan konsensus")
        # hasil sama dengan hitungan independen
        urut = ["kapten", "analis1", "analis2", "analis3"]
        ref = gdss.borda([gdss.topsis(NILAI[u]) for u in urut], 0)
        got = j["konsensus"]["borda"]
        cek(all(abs(a - b) < 1e-12 for a, b in zip(ref["nilai"], got["nilai"])) and ref["rank"] == got["rank"],
            f"hasil Borda = hitungan independen (pemenang {j['konsensus']['pemenang']})")
        # semua akun melihat hasil konsensus dan penilaian individual semua anggota
        for u in AKUN:
            st, j = klien[u].minta("/api/kasus")
            cek(st == 200 and j["konsensus"] and len(j["individual"]) == 4, f"{u} melihat hasil konsensus")
        st, _ = klien["analis2"].minta("/api/nilai", {"skor": NILAI["analis2"]})
        cek(st == 409, "penilaian dikunci setelah konsensus")
        st, _ = klien["analis1"].minta("/api/ulang", {})
        cek(st == 403, "analis tidak boleh mengulang putaran")
        st, _ = klien["kapten"].minta("/api/ulang", {})
        st, j = klien["kapten"].minta("/api/kasus")
        cek(st == 200 and j["konsensus"] is None and not any(s["sudah"] for s in j["status"]), "Kapten mengulang putaran")
        st, _ = klien["kapten"].minta("/api/kasus-baru", {"judul": "x", "fen": "bukan fen", "riwayat": "", "kandidat": ["a", "b", "c"]})
        cek(st == 400, "FEN tidak valid ditolak")
        st, _ = klien["kapten"].minta("/api/kasus-baru", {"judul": "Awal", "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                                                          "riwayat": "", "kandidat": ["e4", "d4", "Nf3"]})
        cek(st == 200, "kasus baru dibuat")
        # traversal path
        try:
            urllib.request.urlopen(BASE + "/..%2fapp.py")
            cek(False, "path traversal harus ditolak")
        except urllib.error.HTTPError as e:
            cek(e.code == 404, "path traversal ditolak (404)")
        print("SEMUA TES UJUNG KE UJUNG LOLOS")
    finally:
        srv.terminate()
        srv.wait(timeout=5)


if __name__ == "__main__":
    main()
