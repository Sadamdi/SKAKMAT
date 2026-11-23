"""SKAKMAT - Sistem Kolaborasi Analis untuk Keputusan Melangkah Antar Tim.

GDSS catur konsultasi: tiga akun setara memainkan bidak putih bersama. Tiap ronde, setiap anggota
mengusulkan satu langkah dengan menggerakkan bidak di papan (satu-satunya input pengguna). Setelah
ketiga usulan masuk, server otomatis:
  1. menggabungkan usulan yang sama menjadi satu alternatif (dukungan dicatat),
  2. mengukur C1-C5 tiap alternatif dari posisi setelah langkah (mesin.py: python-chess + Stockfish),
  3. menjalankan TOPSIS sekali per anggota dengan bobot gaya mainnya (menyerang/seimbang/bertahan),
  4. menggabungkan tiga peringkat itu dengan voting Borda (gdss.py),
  5. memainkan langkah pemenang, lalu balasan lawan (Stockfish), dan membuka ronde berikutnya.

python-chess wajib untuk alur bermain; Stockfish opsional (tanpa Stockfish, C2 diukur secara statis
dan lawan memakai aturan sederhana; keduanya ditandai di tampilan).

    python app.py                 # http://127.0.0.1:8000
    python app.py --port 8080 --host 0.0.0.0   # agar bisa dibuka dari perangkat lain di jaringan
    uvicorn app:app --host 0.0.0.0 --port 8000   # cara setara; dipakai di Docker/server

Backend memakai FastAPI + Uvicorn; front end statis di static/. Lihat docs/ARSITEKTUR.md.
"""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import gdss
import mesin

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
DB_PATH = Path(os.environ.get("SKAKMAT_DB") or BASE / "skakmat.db")
SESI_DETIK = 8 * 3600
MAKS_BODY = 64 * 1024
GAGAL_MAKS, KUNCI_DETIK = 5, 60
VERSI_SKEMA = 2          # 1 = alur lama (Kapten, penilaian manual 1-5); 2 = catur konsultasi

# Akun demo: semua setara, tidak ada jabatan. Yang membedakan hanya gaya main (profil bobot di gdss.PROFIL).
# Ubah daftar ini untuk menambah/mengurangi anggota; urutan = urutan tampilan.
AKUN = [  # (username, nama, gaya, sandi)
    ("anggota1", "Anggota 1", "menyerang", "anggota123-1"),
    ("anggota2", "Anggota 2", "seimbang", "anggota123-2"),
    ("anggota3", "Anggota 3", "bertahan", "anggota123-3"),
]

# Posisi awal setiap permainan: Giuoco Piano setelah 1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6, putih berjalan.
POSISI_AWAL = {
    "fen": "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2P2N2/PP1P1PPP/RNBQK2R w KQkq - 4 5",
    "riwayat": ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6"],
}

COOKIE_AMAN = os.environ.get("SKAKMAT_COOKIE_SECURE") == "1"   # aktifkan bila dilayani lewat HTTPS
percobaan = {}     # (ip, username) -> (jumlah gagal, waktu kunci habis)
_kunci_ronde = threading.Lock()   # usulan, penilaian, dan ronde baru diproses satu per satu


# ------------------------------------------------------------------ basis data
def db():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def hash_sandi(sandi, garam):
    return hashlib.pbkdf2_hmac("sha256", sandi.encode(), garam, 200_000).hex()


SKEMA = """
CREATE TABLE IF NOT EXISTS pengguna(
    id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, nama TEXT NOT NULL,
    gaya TEXT NOT NULL, garam BLOB NOT NULL, sandi TEXT NOT NULL);
-- Satu baris = satu ronde (posisi tempat tim harus melangkah). permainan naik saat "Ronde baru".
CREATE TABLE IF NOT EXISTS sesi(
    token TEXT PRIMARY KEY, pengguna_id INTEGER NOT NULL REFERENCES pengguna(id), kedaluwarsa REAL NOT NULL);
CREATE TABLE IF NOT EXISTS kasus(
    id INTEGER PRIMARY KEY AUTOINCREMENT, permainan INTEGER NOT NULL, nomor INTEGER NOT NULL,
    fen TEXT NOT NULL, riwayat TEXT NOT NULL, dibuat REAL NOT NULL, selesai TEXT);
CREATE TABLE IF NOT EXISTS usulan(
    kasus_id INTEGER NOT NULL REFERENCES kasus(id) ON DELETE CASCADE,
    pengguna_id INTEGER NOT NULL REFERENCES pengguna(id),
    langkah TEXT NOT NULL, san TEXT NOT NULL, waktu REAL NOT NULL, PRIMARY KEY(kasus_id, pengguna_id));
-- Jejak audit lengkap satu keputusan: alternatif, nilai C1-C5, peringkat TOPSIS per gaya, Borda, langkah.
CREATE TABLE IF NOT EXISTS konsensus(
    kasus_id INTEGER PRIMARY KEY REFERENCES kasus(id) ON DELETE CASCADE,
    alternatif TEXT NOT NULL, kriteria TEXT NOT NULL, topsis TEXT NOT NULL, borda TEXT NOT NULL,
    pemenang TEXT NOT NULL, pemenang_san TEXT NOT NULL, fen_setelah TEXT NOT NULL,
    lawan TEXT, lawan_san TEXT, lawan_sumber TEXT, akhir TEXT, waktu REAL NOT NULL);
"""


def migrasi_bila_perlu():
    """Basis data skema lama (Kapten + penilaian manual) tidak cocok dengan alur baru. Isinya hanya data
    demo, jadi file dicadangkan utuh di sebelahnya lalu tabel lama dibuang. Aplikasi tidak pernah mati
    hanya karena basis data lama; bila pencadangan pun gagal, berhenti dengan pesan yang jelas."""
    if not DB_PATH.exists():
        return
    try:
        with sqlite3.connect(DB_PATH) as c:
            versi = c.execute("PRAGMA user_version").fetchone()[0]
            tabel = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.DatabaseError as e:
        raise SystemExit(f"Basis data {DB_PATH} rusak atau bukan file SQLite ({e}). "
                         f"Pindahkan atau hapus file itu, lalu jalankan lagi; file baru dibuat otomatis.")
    if not tabel - {"sqlite_sequence"} or versi == VERSI_SKEMA:
        return
    cadangan = DB_PATH.with_name(f"{DB_PATH.name}.lama-{time.strftime('%Y%m%d-%H%M%S')}")
    try:
        shutil.copy2(DB_PATH, cadangan)
    except OSError as e:
        raise SystemExit(f"Basis data {DB_PATH} memakai skema lama (versi {versi}) dan tidak bisa dicadangkan "
                         f"({e}). Hapus file itu secara manual, lalu jalankan lagi.")
    with sqlite3.connect(DB_PATH) as c:
        c.execute("PRAGMA foreign_keys = OFF")
        for t in ("konsensus", "penilaian", "usulan", "kasus", "pengguna"):
            c.execute(f"DROP TABLE IF EXISTS {t}")
    print(f"Basis data skema lama (versi {versi}) dicadangkan ke {cadangan.name} dan diganti skema baru.", flush=True)


def siapkan_db():
    migrasi_bila_perlu()
    with db() as c:
        c.executescript(SKEMA)
        c.execute(f"PRAGMA user_version = {VERSI_SKEMA}")
        for username, nama, gaya, sandi in AKUN:
            if gaya not in gdss.PROFIL:
                raise SystemExit(f"Gaya '{gaya}' untuk akun {username} tidak dikenal. Pilihan: {', '.join(gdss.PROFIL)}.")
            if c.execute("SELECT 1 FROM pengguna WHERE username=?", (username,)).fetchone():
                c.execute("UPDATE pengguna SET nama=?, gaya=? WHERE username=?", (nama, gaya, username))
            else:
                garam = secrets.token_bytes(16)
                c.execute("INSERT INTO pengguna(username,nama,gaya,garam,sandi) VALUES(?,?,?,?,?)",
                          (username, nama, gaya, garam, hash_sandi(sandi, garam)))
        if c.execute("SELECT COUNT(*) FROM kasus").fetchone()[0] == 0:
            permainan_baru(c)


# ------------------------------------------------------------------ ronde dan permainan
def permainan_baru(c):
    p = c.execute("SELECT COALESCE(MAX(permainan), 0) + 1 FROM kasus").fetchone()[0]
    buat_ronde(c, p, 1, POSISI_AWAL["fen"], POSISI_AWAL["riwayat"])


def buat_ronde(c, permainan, nomor, fen, riwayat, selesai=None):
    c.execute("INSERT INTO kasus(permainan,nomor,fen,riwayat,dibuat,selesai) VALUES(?,?,?,?,?,?)",
              (permainan, nomor, fen, json.dumps(riwayat), time.time(), selesai))


def teks_riwayat(riwayat):
    """['e4','e5','Nf3'] -> '1. e4 e5 2. Nf3' (riwayat selalu dimulai dari posisi awal catur)."""
    return " ".join((f"{i // 2 + 1}. " if i % 2 == 0 else "") + san for i, san in enumerate(riwayat))


def kasus_aktif(c):
    r = c.execute("SELECT * FROM kasus ORDER BY id DESC LIMIT 1").fetchone()
    riwayat = json.loads(r["riwayat"])
    return {"id": r["id"], "permainan": r["permainan"], "nomor": r["nomor"], "fen": r["fen"],
            "riwayat": riwayat, "riwayat_teks": teks_riwayat(riwayat), "selesai": r["selesai"],
            "sisi_tim": "putih" if r["fen"].split()[1] == "w" else "hitam"}


def peserta(c):
    """Anggota aktif (yang ada di AKUN), dalam urutan AKUN."""
    urutan = {a[0]: i for i, a in enumerate(AKUN)}
    baris = c.execute("SELECT id, username, nama, gaya FROM pengguna").fetchall()
    out = [dict(r) for r in baris if r["username"] in urutan]
    out.sort(key=lambda r: urutan[r["username"]])
    for p in out:
        p["gaya_nama"] = gdss.PROFIL[p["gaya"]]["nama"]
        p["bobot"] = gdss.PROFIL[p["gaya"]]["bobot"]
    return out


def status_usulan(c, kasus_id):
    sudah = {r["pengguna_id"]: r["waktu"] for r in
             c.execute("SELECT pengguna_id, waktu FROM usulan WHERE kasus_id=?", (kasus_id,))}
    return [{**p, "sudah": p["id"] in sudah} for p in peserta(c)]


def baca_konsensus(c, kasus_id):
    r = c.execute("SELECT k.*, s.nomor, s.fen, s.permainan FROM konsensus k JOIN kasus s ON s.id = k.kasus_id "
                  "WHERE k.kasus_id=?", (kasus_id,)).fetchone()
    if not r:
        return None
    return {"kasus_id": r["kasus_id"], "nomor": r["nomor"], "fen_sebelum": r["fen"],
            "alternatif": json.loads(r["alternatif"]), "kriteria": json.loads(r["kriteria"]),
            "topsis": json.loads(r["topsis"]), "borda": json.loads(r["borda"]),
            "pemenang": {"uci": r["pemenang"], "san": r["pemenang_san"]}, "fen_setelah": r["fen_setelah"],
            "lawan": {"uci": r["lawan"], "san": r["lawan_san"], "sumber": r["lawan_sumber"]} if r["lawan"] else None,
            "akhir": r["akhir"], "waktu": r["waktu"]}


def hasil_terakhir(c, kasus):
    """Konsensus terbaru dalam permainan yang sedang berjalan (ronde aktif atau ronde sebelumnya)."""
    r = c.execute("SELECT k.kasus_id FROM konsensus k JOIN kasus s ON s.id = k.kasus_id WHERE s.permainan=? "
                  "ORDER BY s.id DESC LIMIT 1", (kasus["permainan"],)).fetchone()
    return baca_konsensus(c, r["kasus_id"]) if r else None


def jalankan_penilaian(c, kasus):
    """Penilaian otomatis satu ronde. Mengembalikan (konsensus, None) atau (None, (status_http, pesan))."""
    if c.execute("SELECT 1 FROM konsensus WHERE kasus_id=?", (kasus["id"],)).fetchone():
        return None, (409, "Ronde ini sudah dinilai.")
    status = status_usulan(c, kasus["id"])
    belum = [s["nama"] for s in status if not s["sudah"]]
    if belum:
        return None, (409, "Belum semua anggota mengusulkan langkah: " + ", ".join(belum) + ".")
    # Usulan diurutkan menurut waktu masuk; langkah yang sama digabung menjadi satu alternatif.
    baris = c.execute("SELECT u.pengguna_id, u.langkah, u.san, u.waktu FROM usulan u WHERE u.kasus_id=? "
                      "ORDER BY u.waktu, u.pengguna_id", (kasus["id"],)).fetchall()
    ids_peserta = {p["id"] for p in status}
    alternatif = []
    for r in baris:
        if r["pengguna_id"] not in ids_peserta:
            continue
        a = next((x for x in alternatif if x["uci"] == r["langkah"]), None)
        if a is None:
            a = {"uci": r["langkah"], "san": r["san"], "pengusul": []}
            alternatif.append(a)
        a["pengusul"].append(r["pengguna_id"])
    for a in alternatif:
        a["dukungan"] = len(a["pengusul"])

    krit = mesin.nilai_kriteria(kasus["fen"], [a["uci"] for a in alternatif])
    if not krit["tersedia"]:
        return None, (503, "Penilaian otomatis tidak bisa dijalankan: " + krit["alasan"])
    matriks = [x["nilai"] for x in krit["alternatif"]]
    k = gdss.konsensus_gaya(matriks, [p["gaya"] for p in status], [a["dukungan"] for a in alternatif])
    topsis = [{"pengguna_id": p["id"], "nama": p["nama"], "gaya": p["gaya"], "gaya_nama": p["gaya_nama"],
               "bobot": p["bobot"], "hasil": h} for p, h in zip(status, k["topsis"])]
    kriteria = {"sumber": krit["sumber"], "nilai": matriks,
                "rincian": [x["rincian"] for x in krit["alternatif"]],
                "engine": [x["engine"] for x in krit["alternatif"]]}
    menang = alternatif[k["pemenang"]]

    tim = kasus["fen"].split()[1] == "w"
    fen_setelah, san = mesin.mainkan(kasus["fen"], menang["uci"])
    riwayat = kasus["riwayat"] + [san]
    akhir = mesin.status_akhir(fen_setelah, tim)
    lawan = lawan_san = lawan_sumber = None
    if not akhir:
        m, lawan_sumber = mesin.langkah_lawan(fen_setelah)
        lawan = m.uci()
        fen_baru, lawan_san = mesin.mainkan(fen_setelah, lawan)
        buat_ronde(c, kasus["permainan"], kasus["nomor"] + 1, fen_baru, riwayat + [lawan_san],
                   selesai=mesin.status_akhir(fen_baru, tim))
    c.execute("INSERT INTO konsensus(kasus_id,alternatif,kriteria,topsis,borda,pemenang,pemenang_san,fen_setelah,"
              "lawan,lawan_san,lawan_sumber,akhir,waktu) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (kasus["id"], json.dumps(alternatif), json.dumps(kriteria), json.dumps(topsis), json.dumps(k["borda"]),
               menang["uci"], san, fen_setelah, lawan, lawan_san, lawan_sumber, akhir, time.time()))
    return baca_konsensus(c, kasus["id"]), None



ENDPOINT_LAMA = {"/api/nilai", "/api/kasus", "/api/kasus-baru", "/api/usul-kandidat"}


# ------------------------------------------------------------------ sesi (disimpan di SQLite supaya selamat dari restart)
def buat_sesi(c, pengguna_id):
    token = secrets.token_urlsafe(32)
    c.execute("DELETE FROM sesi WHERE kedaluwarsa < ?", (time.time(),))
    c.execute("INSERT INTO sesi(token, pengguna_id, kedaluwarsa) VALUES(?,?,?)",
              (token, pengguna_id, time.time() + SESI_DETIK))
    return token


def cookie_sesi(token, umur):
    aman = "; Secure" if COOKIE_AMAN else ""
    return f"sesi={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={umur}{aman}"


def pengguna_dari_cookie(c, token):
    if not token:
        return None
    r = c.execute("SELECT p.id, p.username, p.nama, p.gaya FROM sesi s JOIN pengguna p ON p.id = s.pengguna_id "
                  "WHERE s.token=? AND s.kedaluwarsa >= ?", (token, time.time())).fetchone()
    return dict(r) if r else None


# ------------------------------------------------------------------ aplikasi web (FastAPI)
app = FastAPI(title="SKAKMAT GDSS", version="2.0",
              docs_url="/api/docs" if os.environ.get("SKAKMAT_DOCS") == "1" else None,
              redoc_url=None, openapi_url="/api/openapi.json" if os.environ.get("SKAKMAT_DOCS") == "1" else None)


@app.on_event("startup")
def saat_mulai():
    siapkan_db()
    if not mesin.pustaka_ada():
        print("PERINGATAN: python-chess tidak terpasang. Papan bisa dilihat, tapi usulan langkah ditolak (503).", flush=True)
    elif not mesin.path_engine():
        print("Catatan: Stockfish tidak ditemukan. C2 diukur secara statis dan lawan memakai aturan sederhana.", flush=True)


def galat(status, pesan):
    return JSONResponse({"galat": pesan}, status_code=status)


@app.exception_handler(StarletteHTTPException)
async def tangani_http(request, exc):
    return galat(exc.status_code, "Tidak ditemukan." if exc.status_code == 404 else str(exc.detail))


@app.middleware("http")
async def kepala_dan_asal(request: Request, call_next):
    """Header keamanan untuk semua respons, dan tolak POST lintas-situs (Origin harus sama dengan Host)."""
    if request.method == "POST":
        asal = request.headers.get("origin")
        if asal and urlparse(asal).netloc != request.headers.get("host"):
            resp = galat(403, "Asal permintaan tidak sah.")
        else:
            resp = await call_next(request)
    else:
        resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


async def baca_json(request: Request):
    body = await request.body()
    if not body or len(body) > MAKS_BODY:
        return None
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def api(fungsi):
    """Bungkus handler sinkron: buka koneksi, cek sesi, jalankan di thread pool (SQLite dan engine memblokir)."""
    async def rute(request: Request):
        data = await baca_json(request) if request.method == "POST" else None

        def kerja():
            with db() as c:
                user = pengguna_dari_cookie(c, request.cookies.get("sesi"))
                if not user:
                    return galat(401, "Silakan masuk terlebih dahulu.")
                return fungsi(c, user, data, request)
        return await run_in_threadpool(kerja)
    return rute


def get_ronde(c, user, data, request):
    """Keadaan ronde. Tidak pernah memanggil engine (semua angka sudah dihitung saat penilaian),
    jadi aman dipanggil berkala. Usulan anggota lain baru terlihat setelah ronde dinilai, supaya
    usulan tiap orang tetap independen."""
    kasus = kasus_aktif(c)
    status = status_usulan(c, kasus["id"])
    saya = c.execute("SELECT langkah, san, waktu FROM usulan WHERE kasus_id=? AND pengguna_id=?",
                     (kasus["id"], user["id"])).fetchone()
    konsensus = baca_konsensus(c, kasus["id"])
    bisa_usul = mesin.pustaka_ada() and not konsensus and not kasus["selesai"]
    return JSONResponse({
        "pengguna": user, "peserta": status, "kasus": kasus,
        "kriteria": gdss.KRITERIA, "profil": gdss.PROFIL,
        "semua_sudah": all(s["sudah"] for s in status),
        "usulan_saya": {"uci": saya["langkah"], "san": saya["san"], "waktu": saya["waktu"]} if saya else None,
        "langkah_sah": mesin.langkah_sah(kasus["fen"]) if bisa_usul else [],
        "konsensus": konsensus,                       # ronde aktif sudah dinilai (hanya bila permainan selesai)
        "hasil_terakhir": konsensus or hasil_terakhir(c, kasus),
        "server": {"python_chess": mesin.pustaka_ada(), "stockfish": bool(mesin.path_engine())},
    })


def post_usul(c, user, data, request):
    langkah = data.get("langkah") if data else None
    if not isinstance(langkah, str):
        return galat(400, "Usulan harus berupa satu langkah, mis. e2e4.")
    if user["username"] not in {a[0] for a in AKUN}:
        return galat(403, "Akun ini bukan anggota tim yang aktif.")
    with _kunci_ronde:
        kasus = kasus_aktif(c)
        if kasus["selesai"]:
            return galat(409, "Permainan sudah selesai: " + kasus["selesai"] + " Mulai ronde baru.")
        if c.execute("SELECT 1 FROM konsensus WHERE kasus_id=?", (kasus["id"],)).fetchone():
            return galat(409, "Ronde ini sudah dinilai; usulan dikunci.")
        if not mesin.pustaka_ada():
            return galat(503, "Server tidak bisa memeriksa langkah: pustaka python-chess tidak terpasang.")
        m, pesan = mesin.validasi_usulan(kasus["fen"], langkah)
        if pesan:
            return galat(400, pesan)
        _, san = mesin.mainkan(kasus["fen"], m.uci())
        c.execute("INSERT OR REPLACE INTO usulan(kasus_id,pengguna_id,langkah,san,waktu) VALUES(?,?,?,?,?)",
                  (kasus["id"], user["id"], m.uci(), san, time.time()))
        c.commit()
        out = {"ok": True, "usulan": {"uci": m.uci(), "san": san}, "dinilai": False}
        if all(s["sudah"] for s in status_usulan(c, kasus["id"])):
            hasil, g = jalankan_penilaian(c, kasus)
            c.commit()
            if g:
                out["galat_penilaian"] = g[1]
            else:
                out.update(dinilai=True, konsensus=hasil)
        return JSONResponse(out)


def post_konsensus(c, user, data, request):
    """Menjalankan ulang penilaian bila otomatisnya gagal (mis. server sempat mati). Semua akun boleh."""
    with _kunci_ronde:
        kasus = kasus_aktif(c)
        hasil, g = jalankan_penilaian(c, kasus)
        c.commit()
    if g:
        return galat(*g)
    return JSONResponse({"ok": True, "konsensus": hasil})


def post_ulang(c, user, data, request):
    """Ronde baru: mulai permainan baru dari posisi awal. Semua akun boleh; riwayat lama tetap tersimpan."""
    with _kunci_ronde:
        permainan_baru(c)
        c.commit()
    return JSONResponse({"ok": True, "kasus": kasus_aktif(c)})


def post_keluar(c, user, data, request):
    c.execute("DELETE FROM sesi WHERE token=?", (request.cookies.get("sesi"),))
    resp = JSONResponse({"ok": True})
    resp.headers["Set-Cookie"] = cookie_sesi("", 0)
    return resp


app.add_api_route("/api/ronde", api(get_ronde), methods=["GET"])
app.add_api_route("/api/usul", api(post_usul), methods=["POST"])
app.add_api_route("/api/konsensus", api(post_konsensus), methods=["POST"])
app.add_api_route("/api/ulang", api(post_ulang), methods=["POST"])
app.add_api_route("/api/keluar", api(post_keluar), methods=["POST"])


@app.get("/api/me")
async def get_me(request: Request):
    def kerja():
        with db() as c:
            return JSONResponse({"pengguna": pengguna_dari_cookie(c, request.cookies.get("sesi"))})
    return await run_in_threadpool(kerja)


@app.post("/api/login")
async def post_login(request: Request):
    data = await baca_json(request)
    if not data or not isinstance(data.get("username"), str) or not isinstance(data.get("sandi"), str):
        return galat(400, "Isi nama pengguna dan kata sandi.")
    ip = request.client.host if request.client else "?"

    def kerja():
        kunci = (ip, data["username"].lower())
        gagal, sampai = percobaan.get(kunci, (0, 0))
        if gagal >= GAGAL_MAKS and sampai > time.time():
            return galat(429, "Terlalu banyak percobaan. Coba lagi sebentar.")
        with db() as c:
            r = c.execute("SELECT * FROM pengguna WHERE username=?", (data["username"].lower(),)).fetchone()
            sah = False
            if r:
                sah = hmac.compare_digest(hash_sandi(data["sandi"], r["garam"]), r["sandi"])
            else:
                hash_sandi(data["sandi"], b"0" * 16)   # samakan waktu proses
            if not sah:
                percobaan[kunci] = (gagal + 1, time.time() + KUNCI_DETIK)
                return galat(401, "Nama pengguna atau kata sandi salah.")
            percobaan.pop(kunci, None)
            token = buat_sesi(c, r["id"])
        resp = JSONResponse({"pengguna": {"id": r["id"], "username": r["username"], "nama": r["nama"],
                                          "gaya": r["gaya"]}})
        resp.headers["Set-Cookie"] = cookie_sesi(token, SESI_DETIK)
        return resp
    return await run_in_threadpool(kerja)


@app.api_route("/api/{sisa:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def api_lain(sisa: str, request: Request):
    """Endpoint alur lama dijawab 410 (bagi yang sudah login); selain itu 401 atau 404."""
    jalur = "/api/" + sisa

    def kerja():
        with db() as c:
            user = pengguna_dari_cookie(c, request.cookies.get("sesi"))
        if not user:
            return galat(401, "Silakan masuk terlebih dahulu.")
        if jalur in ENDPOINT_LAMA:
            return galat(410, "Endpoint ini milik alur lama (penilaian manual) dan tidak dipakai lagi. "
                              "Usulkan langkah lewat papan: POST /api/usul.")
        return galat(404, "Tidak ditemukan.")
    return await run_in_threadpool(kerja)


@app.get("/{jalur:path}", include_in_schema=False)
async def berkas_statis(jalur: str):
    """Front end statis (static/). Path di luar folder itu ditolak."""
    berkas = (STATIC / (jalur or "index.html")).resolve()
    if STATIC.resolve() not in berkas.parents or not berkas.is_file():
        return galat(404, "Tidak ditemukan.")
    return FileResponse(berkas)


def main():
    ap = argparse.ArgumentParser(description="SKAKMAT GDSS")
    ap.add_argument("--host", default=os.environ.get("SKAKMAT_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("SKAKMAT_PORT", "8000")))
    a = ap.parse_args()
    print(f"SKAKMAT berjalan di http://{a.host}:{a.port}  (Ctrl+C untuk berhenti)", flush=True)
    # Satu proses: kunci ronde (threading.Lock) dan batas percobaan login hidup di memori proses ini.
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning",
                proxy_headers=True, forwarded_allow_ips=os.environ.get("SKAKMAT_PROXY_IPS", "127.0.0.1"))


if __name__ == "__main__":
    main()
