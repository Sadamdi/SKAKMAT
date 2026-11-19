"""SKAKMAT - Sistem Kolaborasi Analis untuk Keputusan Melangkah Antar Tim.

GDSS berbasis website: empat decision maker (Kapten, Analis 1, 2, 3) menilai tiga kandidat langkah
catur secara individual dengan TOPSIS, lalu akun Kapten (jabatan tertinggi) menjalankan konsensus
voting Borda. Semua decision maker dapat melihat hasil konsensus.

Inti aplikasi hanya memakai pustaka standar Python. Validasi legalitas langkah dan pembanding engine
(mesin.py) memakai python-chess + Stockfish bila terpasang; tanpa keduanya aplikasi tetap berjalan.

    python app.py                 # http://127.0.0.1:8000
    python app.py --port 8080 --host 0.0.0.0   # agar bisa dibuka dari perangkat lain di jaringan
"""
import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import sqlite3
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import gdss
import mesin

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
DB_PATH = Path(os.environ.get("SKAKMAT_DB") or BASE / "skakmat.db")
SESI_DETIK = 8 * 3600
MAKS_BODY = 64 * 1024
GAGAL_MAKS, KUNCI_DETIK = 5, 60

# Akun demo. Kapten memiliki jabatan tertinggi (tingkat 1) dan menjalankan konsensus.
AKUN = [
    ("kapten", "Kapten", "kapten", 1, "kapten123"),
    ("analis1", "Analis 1", "analis", 2, "analis123-1"),
    ("analis2", "Analis 2", "analis", 3, "analis123-2"),
    ("analis3", "Analis 3", "analis", 4, "analis123-3"),
]

# Kasus awal: Giuoco Piano setelah 1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6, putih berjalan.
KASUS_AWAL = {
    "judul": "Giuoco Piano: putih memilih langkah ke-5",
    "fen": "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2P2N2/PP1P1PPP/RNBQK2R w KQkq - 4 5",
    "riwayat": "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6",
    "kandidat": ["5. d4", "5. d3", "5. O-O"],
}

sesi = {}          # token -> (user_id, kedaluwarsa)
percobaan = {}     # (ip, username) -> (jumlah gagal, waktu kunci habis)


# ------------------------------------------------------------------ basis data
def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def hash_sandi(sandi, garam):
    return hashlib.pbkdf2_hmac("sha256", sandi.encode(), garam, 200_000).hex()


def siapkan_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS pengguna(
            id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, nama TEXT NOT NULL,
            peran TEXT NOT NULL, tingkat INTEGER NOT NULL, garam BLOB NOT NULL, sandi TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS kasus(
            id INTEGER PRIMARY KEY AUTOINCREMENT, judul TEXT NOT NULL, fen TEXT NOT NULL,
            riwayat TEXT NOT NULL, kandidat TEXT NOT NULL, dibuat REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS penilaian(
            kasus_id INTEGER NOT NULL REFERENCES kasus(id) ON DELETE CASCADE,
            pengguna_id INTEGER NOT NULL REFERENCES pengguna(id),
            skor TEXT NOT NULL, waktu REAL NOT NULL, PRIMARY KEY(kasus_id, pengguna_id));
        CREATE TABLE IF NOT EXISTS konsensus(
            kasus_id INTEGER PRIMARY KEY REFERENCES kasus(id) ON DELETE CASCADE,
            hasil TEXT NOT NULL, oleh INTEGER NOT NULL, waktu REAL NOT NULL);
        """)
        if c.execute("SELECT COUNT(*) FROM pengguna").fetchone()[0] == 0:
            for username, nama, peran, tingkat, sandi in AKUN:
                garam = secrets.token_bytes(16)
                c.execute("INSERT INTO pengguna(username,nama,peran,tingkat,garam,sandi) VALUES(?,?,?,?,?,?)",
                          (username, nama, peran, tingkat, garam, hash_sandi(sandi, garam)))
        if c.execute("SELECT COUNT(*) FROM kasus").fetchone()[0] == 0:
            buat_kasus(c, KASUS_AWAL)


def buat_kasus(c, k):
    c.execute("INSERT INTO kasus(judul,fen,riwayat,kandidat,dibuat) VALUES(?,?,?,?,?)",
              (k["judul"], k["fen"], k["riwayat"], json.dumps(k["kandidat"]), time.time()))


def kasus_aktif(c):
    r = c.execute("SELECT * FROM kasus ORDER BY id DESC LIMIT 1").fetchone()
    return {"id": r["id"], "judul": r["judul"], "fen": r["fen"], "riwayat": r["riwayat"],
            "kandidat": json.loads(r["kandidat"])}


def fen_valid(fen):
    """Pemeriksaan bentuk FEN (bukan validasi legalitas posisi)."""
    bagian = fen.split()
    if len(bagian) < 2:
        return False
    baris = bagian[0].split("/")
    if len(baris) != 8:
        return False
    for b in baris:
        n = 0
        for ch in b:
            if ch.isdigit() and ch != "0":
                n += int(ch)
            elif ch in "prnbqkPRNBQK":
                n += 1
            else:
                return False
        if n != 8:
            return False
    return bagian[1] in ("w", "b")


# ------------------------------------------------------------------ logika bisnis
def status_penilai(c, kasus_id):
    baris = c.execute(
        "SELECT p.id, p.nama, p.tingkat, (SELECT COUNT(*) FROM penilaian n WHERE n.pengguna_id=p.id AND n.kasus_id=?) AS sudah "
        "FROM pengguna p ORDER BY p.tingkat", (kasus_id,)).fetchall()
    return [{"id": r["id"], "nama": r["nama"], "tingkat": r["tingkat"], "sudah": bool(r["sudah"])} for r in baris]


def ambil_hasil_individual(c, kasus_id):
    """Daftar (pengguna, skor, hasil topsis) berurut menurut tingkat jabatan (tertinggi dulu)."""
    baris = c.execute(
        "SELECT p.id, p.nama, p.tingkat, n.skor FROM penilaian n JOIN pengguna p ON p.id=n.pengguna_id "
        "WHERE n.kasus_id=? ORDER BY p.tingkat", (kasus_id,)).fetchall()
    out = []
    for r in baris:
        skor = json.loads(r["skor"])
        out.append({"id": r["id"], "nama": r["nama"], "tingkat": r["tingkat"], "skor": skor,
                    "topsis": gdss.topsis(skor)})
    return out


def jalankan_konsensus(c, kasus, pengguna):
    status = status_penilai(c, kasus["id"])
    belum = [s["nama"] for s in status if not s["sudah"]]
    if belum:
        return None, "Belum semua decision maker menilai: " + ", ".join(belum) + "."
    individual = ambil_hasil_individual(c, kasus["id"])
    # individual terurut menurut tingkat jabatan, indeks 0 = Kapten (pemutus bila seri)
    k = gdss.borda([i["topsis"] for i in individual], urutan_pemutus=0)
    hasil = {"borda": k, "penilai": [{"id": i["id"], "nama": i["nama"]} for i in individual],
             "pemenang": kasus["kandidat"][k["pemenang"]], "dijalankan_oleh": pengguna["nama"]}
    c.execute("INSERT OR REPLACE INTO konsensus(kasus_id,hasil,oleh,waktu) VALUES(?,?,?,?)",
              (kasus["id"], json.dumps(hasil), pengguna["id"], time.time()))
    return hasil, None


# ------------------------------------------------------------------ HTTP
class Penangan(BaseHTTPRequestHandler):
    server_version = "SKAKMAT/1.0"

    def log_message(self, fmt, *args):  # log ringkas
        print("[%s] %s" % (time.strftime("%H:%M:%S"), fmt % args))

    # -- util respons
    def kirim_json(self, data, status=200, cookie=None):
        isi = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(isi)))
        self.send_header("Cache-Control", "no-store")
        self.kepala_aman()
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(isi)

    def kepala_aman(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'")
        self.send_header("Referrer-Policy", "no-referrer")

    def kesalahan(self, status, pesan):
        self.kirim_json({"galat": pesan}, status)

    def baca_json(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if n <= 0 or n > MAKS_BODY:
            return None
        try:
            data = json.loads(self.rfile.read(n))
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def pengguna_login(self, c):
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        m = jar.get("sesi")
        if not m:
            return None
        info = sesi.get(m.value)
        if not info or info[1] < time.time():
            sesi.pop(m.value, None)
            return None
        r = c.execute("SELECT id, username, nama, peran, tingkat FROM pengguna WHERE id=?", (info[0],)).fetchone()
        return dict(r) if r else None

    def asal_sah(self):
        """Tolak POST lintas-situs: Origin (bila ada) harus sama dengan Host."""
        asal = self.headers.get("Origin")
        return not asal or urlparse(asal).netloc == self.headers.get("Host")

    # -- GET
    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            return self.api("GET", path)
        if path == "/":
            path = "/index.html"
        berkas = (STATIC / path.lstrip("/")).resolve()
        if STATIC.resolve() not in berkas.parents or not berkas.is_file():
            return self.kesalahan(404, "Tidak ditemukan.")
        isi = berkas.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(berkas.name)[0] or "application/octet-stream") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(isi)))
        self.kepala_aman()
        self.end_headers()
        self.wfile.write(isi)

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return self.kesalahan(404, "Tidak ditemukan.")
        if not self.asal_sah():
            return self.kesalahan(403, "Asal permintaan tidak sah.")
        self.api("POST", path)

    # -- API
    def api(self, metode, path):
        with db() as c:
            if metode == "POST" and path == "/api/login":
                return self.login(c)
            user = self.pengguna_login(c)
            if path == "/api/me" and metode == "GET":
                return self.kirim_json({"pengguna": user})
            if not user:
                return self.kesalahan(401, "Silakan masuk terlebih dahulu.")
            rute = {("GET", "/api/kasus"): self.get_kasus,
                    ("POST", "/api/nilai"): self.post_nilai,
                    ("POST", "/api/konsensus"): self.post_konsensus,
                    ("POST", "/api/ulang"): self.post_ulang,
                    ("POST", "/api/kasus-baru"): self.post_kasus_baru,
                    ("POST", "/api/usul-kandidat"): self.post_usul_kandidat,
                    ("POST", "/api/keluar"): self.post_keluar}
            fn = rute.get((metode, path))
            if not fn:
                return self.kesalahan(404, "Tidak ditemukan.")
            return fn(c, user)

    def login(self, c):
        data = self.baca_json()
        if not data or not isinstance(data.get("username"), str) or not isinstance(data.get("sandi"), str):
            return self.kesalahan(400, "Isi nama pengguna dan kata sandi.")
        kunci = (self.client_address[0], data["username"].lower())
        gagal, sampai = percobaan.get(kunci, (0, 0))
        if gagal >= GAGAL_MAKS and sampai > time.time():
            return self.kesalahan(429, "Terlalu banyak percobaan. Coba lagi sebentar.")
        r = c.execute("SELECT * FROM pengguna WHERE username=?", (data["username"].lower(),)).fetchone()
        sah = False
        if r:
            sah = hmac.compare_digest(hash_sandi(data["sandi"], r["garam"]), r["sandi"])
        else:
            hash_sandi(data["sandi"], b"0" * 16)   # samakan waktu proses
        if not sah:
            percobaan[kunci] = (gagal + 1, time.time() + KUNCI_DETIK)
            return self.kesalahan(401, "Nama pengguna atau kata sandi salah.")
        percobaan.pop(kunci, None)
        token = secrets.token_urlsafe(32)
        sesi[token] = (r["id"], time.time() + SESI_DETIK)
        cookie = f"sesi={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESI_DETIK}"
        self.kirim_json({"pengguna": {"id": r["id"], "username": r["username"], "nama": r["nama"],
                                      "peran": r["peran"], "tingkat": r["tingkat"]}}, cookie=cookie)

    def post_keluar(self, c, user):
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        if "sesi" in jar:
            sesi.pop(jar["sesi"].value, None)
        self.kirim_json({"ok": True}, cookie="sesi=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")

    def get_kasus(self, c, user):
        kasus = kasus_aktif(c)
        status = status_penilai(c, kasus["id"])
        saya = c.execute("SELECT skor FROM penilaian WHERE kasus_id=? AND pengguna_id=?",
                         (kasus["id"], user["id"])).fetchone()
        k = c.execute("SELECT hasil, waktu FROM konsensus WHERE kasus_id=?", (kasus["id"],)).fetchone()
        konsensus = json.loads(k["hasil"]) if k else None
        out = {"pengguna": user, "kasus": kasus, "kriteria": gdss.KRITERIA, "status": status,
               "semua_sudah": all(s["sudah"] for s in status), "konsensus": konsensus,
               "skor_saya": json.loads(saya["skor"]) if saya else None,
               "topsis_saya": gdss.topsis(json.loads(saya["skor"])) if saya else None}
        if konsensus:   # setelah konsensus, seluruh decision maker melihat penilaian individual semua anggota
            out["individual"] = [{"nama": i["nama"], "tingkat": i["tingkat"], "skor": i["skor"], "topsis": i["topsis"]}
                                 for i in ambil_hasil_individual(c, kasus["id"])]
        # Pembanding engine (field tambahan). Ditahan sampai konsensus supaya penilaian anggota tidak
        # terpengaruh nilai engine. Selalu berbentuk {"tersedia": bool, ...} dengan alasan bila tidak tersedia.
        out["engine"] = (mesin.peringkat_kasus(kasus["fen"], kasus["kandidat"]) if konsensus else
                         mesin.tidak_tersedia("menunggu_konsensus", "Peringkat engine ditampilkan setelah konsensus "
                                              "dijalankan, supaya penilaian anggota tidak terpengaruh."))
        return self.kirim_json(out)

    def post_nilai(self, c, user):
        kasus = kasus_aktif(c)
        if c.execute("SELECT 1 FROM konsensus WHERE kasus_id=?", (kasus["id"],)).fetchone():
            return self.kesalahan(409, "Konsensus sudah dijalankan; penilaian dikunci.")
        data = self.baca_json()
        skor = data.get("skor") if data else None
        pesan = gdss.validasi_nilai(skor, len(kasus["kandidat"]))
        if pesan:
            return self.kesalahan(400, pesan)
        c.execute("INSERT OR REPLACE INTO penilaian(kasus_id,pengguna_id,skor,waktu) VALUES(?,?,?,?)",
                  (kasus["id"], user["id"], json.dumps(skor), time.time()))
        return self.kirim_json({"ok": True, "topsis": gdss.topsis(skor)})

    def post_konsensus(self, c, user):
        if user["tingkat"] != 1:
            return self.kesalahan(403, "Hanya akun dengan jabatan tertinggi (Kapten) yang dapat menjalankan konsensus.")
        kasus = kasus_aktif(c)
        hasil, pesan = jalankan_konsensus(c, kasus, user)
        if pesan:
            return self.kesalahan(409, pesan)
        return self.kirim_json({"ok": True, "konsensus": hasil})

    def post_ulang(self, c, user):
        if user["tingkat"] != 1:
            return self.kesalahan(403, "Hanya Kapten yang dapat mengulang putaran penilaian.")
        kasus = kasus_aktif(c)
        c.execute("DELETE FROM konsensus WHERE kasus_id=?", (kasus["id"],))
        c.execute("DELETE FROM penilaian WHERE kasus_id=?", (kasus["id"],))
        return self.kirim_json({"ok": True})

    def post_kasus_baru(self, c, user):
        if user["tingkat"] != 1:
            return self.kesalahan(403, "Hanya Kapten yang dapat membuat kasus baru.")
        d = self.baca_json() or {}
        judul, fen, riwayat, kand = d.get("judul"), d.get("fen"), d.get("riwayat", ""), d.get("kandidat")
        if not (isinstance(judul, str) and isinstance(fen, str) and isinstance(riwayat, str)
                and isinstance(kand, list) and len(kand) == 3 and all(isinstance(x, str) and x.strip() for x in kand)):
            return self.kesalahan(400, "Isi judul, FEN, dan tepat tiga kandidat langkah.")
        if not (1 <= len(judul) <= 100 and len(riwayat) <= 500 and all(len(x) <= 20 for x in kand)):
            return self.kesalahan(400, "Teks terlalu panjang.")
        if not fen_valid(fen.strip()):
            return self.kesalahan(400, "Format FEN tidak valid.")
        # Tambahan: legalitas posisi dan kandidat langkah (bila python-chess terpasang).
        pesan = mesin.validasi_kasus(fen.strip(), [x.strip() for x in kand])
        if pesan:
            return self.kesalahan(400, pesan)
        buat_kasus(c, {"judul": judul.strip(), "fen": fen.strip(), "riwayat": riwayat.strip(),
                       "kandidat": [x.strip() for x in kand]})
        if not mesin.pustaka_ada():
            return self.kirim_json({"ok": True, "peringatan": "Legalitas langkah tidak diperiksa: "
                                    "pustaka python-chess tidak terpasang di server."})
        return self.kirim_json({"ok": True})

    def post_usul_kandidat(self, c, user):
        """Usulan tiga kandidat dari engine untuk FEN. Opsional; form manual tetap bisa dipakai."""
        if user["tingkat"] != 1:
            return self.kesalahan(403, "Hanya Kapten yang dapat meminta usulan kandidat.")
        d = self.baca_json() or {}
        fen = d.get("fen")
        if not isinstance(fen, str) or not fen_valid(fen.strip()):
            return self.kesalahan(400, "Format FEN tidak valid.")
        kandidat, galat = mesin.usul_kandidat(fen.strip())
        if galat:
            return self.kesalahan(*galat)
        return self.kirim_json({"ok": True, "kandidat": kandidat, "urutan": "abjad, bukan peringkat engine"})


def main():
    ap = argparse.ArgumentParser(description="SKAKMAT GDSS")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    siapkan_db()
    srv = ThreadingHTTPServer((a.host, a.port), Penangan)
    print(f"SKAKMAT berjalan di http://{a.host}:{a.port}  (Ctrl+C untuk berhenti)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBerhenti.")


if __name__ == "__main__":
    main()
