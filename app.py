"""SKAKMAT - Sistem Kolaborasi Analis untuk Keputusan Melangkah Antar Tim.

GDSS catur konsultasi. Pengguna mendaftar atau masuk, lalu membuat atau bergabung ke sebuah pertandingan
(maksimal 3 pemain). Tim memainkan bidak putih melawan komputer:

  giliran tim    : tiap anggota mengusulkan satu langkah (menggerakkan bidak) -> penilaian individual (C1-C5 diukur
                   mesin + TOPSIS per anggota dengan bobot gayanya) -> Ketua (pembuat pertandingan, jabatan
                   tertinggi) menjalankan konsensus voting Borda -> langkah pemenang dimainkan.
  giliran lawan  : komputer membalas dengan algoritma catur biasa (Stockfish; tanpa Stockfish: aturan sederhana).

Anggota bisa keluar atau bergabung kapan saja. Bila semua pemain keluar (atau tidak aktif terlalu lama),
pertandingan otomatis berakhir. Bila Ketua keluar, anggota yang bergabung paling awal menjadi Ketua.

python-chess wajib untuk alur bermain; Stockfish opsional.

    python app.py                 # http://127.0.0.1:8000
    python app.py --port 8080 --host 0.0.0.0   # agar bisa dibuka dari perangkat lain di jaringan
    uvicorn app:app --host 0.0.0.0 --port 8000   # cara setara; dipakai di Docker/server

Backend memakai FastAPI + Uvicorn; front end statis di static/. Lihat docs/ARSITEKTUR.md.
"""
import argparse
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import os
import re
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
DAFTAR_MAKS, DAFTAR_JENDELA = 10, 600       # pendaftaran per alamat IP per 10 menit
VERSI_SKEMA = 3          # 1 = Kapten + penilaian manual; 2 = satu permainan global; 3 = akun + pertandingan (lobi)
MAKS_ANGGOTA = 3
TIMEOUT_AKTIF = int(os.environ.get("SKAKMAT_TIMEOUT_AKTIF") or 120)   # detik tanpa aktivitas -> dianggap keluar

# Akun demo (dibuat otomatis agar mudah dicoba). Pengguna lain mendaftar sendiri lewat /api/daftar.
AKUN = [  # (username, nama, sandi)
    ("anggota1", "Anggota 1", "test123"),
    ("anggota2", "Anggota 2", "test123"),
    ("anggota3", "Anggota 3", "test123"),
]

# Posisi awal setiap permainan baru: posisi awal catur biasa (putih berjalan). SKAKMAT_POSISI=giuoco memakai
# pembukaan Giuoco Piano yang sudah berjalan 4 langkah (1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6); dipakai oleh tes.
POSISI = {
    "standar": {"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "riwayat": []},
    "giuoco": {
        "fen": "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2P2N2/PP1P1PPP/RNBQK2R w KQkq - 4 5",
        "riwayat": ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6"],
    },
}
POSISI_AWAL = POSISI.get((os.environ.get("SKAKMAT_POSISI") or "standar").strip().lower(), POSISI["standar"])

COOKIE_AMAN = os.environ.get("SKAKMAT_COOKIE_SECURE") == "1"   # aktifkan bila dilayani lewat HTTPS
percobaan = {}     # (ip, username) -> (jumlah gagal, waktu kunci habis)
pendaftaran = {}   # ip -> [waktu, ...]
_kunci_ronde = threading.Lock()   # usulan, penilaian, keanggotaan, dan ronde baru diproses satu per satu
RE_USERNAME = re.compile(r"^[a-z0-9_]{3,20}$")


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
    garam BLOB NOT NULL, sandi TEXT NOT NULL, dibuat REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sesi(
    token TEXT PRIMARY KEY, pengguna_id INTEGER NOT NULL REFERENCES pengguna(id), kedaluwarsa REAL NOT NULL);
-- Satu baris = satu pertandingan (ruang main). Ketua = pembuat; berpindah ke anggota paling awal bila Ketua keluar.
CREATE TABLE IF NOT EXISTS pertandingan(
    id INTEGER PRIMARY KEY AUTOINCREMENT, kode TEXT UNIQUE NOT NULL, nama TEXT NOT NULL,
    ketua_id INTEGER REFERENCES pengguna(id), status TEXT NOT NULL DEFAULT 'berlangsung',
    alasan_selesai TEXT, dibuat REAL NOT NULL, berakhir REAL, publik INTEGER NOT NULL DEFAULT 1);
-- Keanggotaan: aktif = 1 selama pemain berada di pertandingan. gaya (menyerang/seimbang/bertahan) unik per pertandingan.
CREATE TABLE IF NOT EXISTS anggota(
    pertandingan_id INTEGER NOT NULL REFERENCES pertandingan(id) ON DELETE CASCADE,
    pengguna_id INTEGER NOT NULL REFERENCES pengguna(id),
    gaya TEXT NOT NULL, bergabung REAL NOT NULL, terakhir REAL NOT NULL, aktif INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY(pertandingan_id, pengguna_id));
-- Satu baris = satu ronde (posisi tempat tim harus melangkah). permainan naik saat "Permainan baru".
CREATE TABLE IF NOT EXISTS kasus(
    id INTEGER PRIMARY KEY AUTOINCREMENT, pertandingan_id INTEGER NOT NULL REFERENCES pertandingan(id) ON DELETE CASCADE,
    permainan INTEGER NOT NULL, nomor INTEGER NOT NULL,
    fen TEXT NOT NULL, riwayat TEXT NOT NULL, dibuat REAL NOT NULL, selesai TEXT);
CREATE TABLE IF NOT EXISTS usulan(
    kasus_id INTEGER NOT NULL REFERENCES kasus(id) ON DELETE CASCADE,
    pengguna_id INTEGER NOT NULL REFERENCES pengguna(id),
    langkah TEXT NOT NULL, san TEXT NOT NULL, waktu REAL NOT NULL, PRIMARY KEY(kasus_id, pengguna_id));
-- Penilaian individual per ronde: C1-C5 dan TOPSIS tiap anggota. Ada begitu semua anggota mengusulkan;
-- konsensus (Borda) baru dijalankan Ketua sesudahnya.
CREATE TABLE IF NOT EXISTS penilaian_individual(
    kasus_id INTEGER PRIMARY KEY REFERENCES kasus(id) ON DELETE CASCADE,
    alternatif TEXT NOT NULL, kriteria TEXT NOT NULL, topsis TEXT NOT NULL, waktu REAL NOT NULL);
-- Jejak audit lengkap satu keputusan: alternatif, nilai C1-C5, peringkat TOPSIS per gaya, Borda, langkah.
CREATE TABLE IF NOT EXISTS konsensus(
    kasus_id INTEGER PRIMARY KEY REFERENCES kasus(id) ON DELETE CASCADE,
    alternatif TEXT NOT NULL, kriteria TEXT NOT NULL, topsis TEXT NOT NULL, borda TEXT NOT NULL,
    pemenang TEXT NOT NULL, pemenang_san TEXT NOT NULL, fen_setelah TEXT NOT NULL,
    lawan TEXT, lawan_san TEXT, lawan_sumber TEXT, akhir TEXT, waktu REAL NOT NULL);
"""


def migrasi_bila_perlu():
    """Basis data skema lama tidak cocok dengan alur pertandingan. Isinya hanya data demo, jadi file dicadangkan
    utuh di sebelahnya lalu tabel lama dibuang. Aplikasi tidak pernah mati hanya karena basis data lama; bila
    pencadangan pun gagal, berhenti dengan pesan yang jelas."""
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
        for t in ("konsensus", "penilaian_individual", "penilaian", "usulan", "kasus", "anggota", "pertandingan",
                  "sesi", "pengguna"):
            c.execute(f"DROP TABLE IF EXISTS {t}")
    print(f"Basis data skema lama (versi {versi}) dicadangkan ke {cadangan.name} dan diganti skema baru.", flush=True)


def siapkan_db():
    migrasi_bila_perlu()
    with db() as c:
        c.executescript(SKEMA)
        c.execute(f"PRAGMA user_version = {VERSI_SKEMA}")
        if "publik" not in {r["name"] for r in c.execute("PRAGMA table_info(pertandingan)")}:   # basis data skema 3 lama
            c.execute("ALTER TABLE pertandingan ADD COLUMN publik INTEGER NOT NULL DEFAULT 1")
        for username, nama, sandi in AKUN:
            # SKAKMAT_SANDI_<USERNAME> (mis. SKAKMAT_SANDI_ANGGOTA1) menggantikan kata sandi bawaan; dipakai
            # saat server dibuka lewat internet supaya akun demo tidak bisa ditebak.
            sandi_env = os.environ.get("SKAKMAT_SANDI_" + username.upper())
            if c.execute("SELECT 1 FROM pengguna WHERE username=?", (username,)).fetchone():
                c.execute("UPDATE pengguna SET nama=? WHERE username=?", (nama, username))
                # Akun demo selalu kembali ke kata sandi bawaan (atau dari lingkungan) tiap server dinyalakan,
                # jadi kata sandinya tetap sama walau server dimulai ulang atau basis data lama dipakai.
                garam = secrets.token_bytes(16)
                c.execute("UPDATE pengguna SET garam=?, sandi=? WHERE username=?",
                          (garam, hash_sandi(sandi_env or sandi, garam), username))
            else:
                garam = secrets.token_bytes(16)
                c.execute("INSERT INTO pengguna(username,nama,garam,sandi,dibuat) VALUES(?,?,?,?,?)",
                          (username, nama, garam, hash_sandi(sandi_env or sandi, garam), time.time()))


# ------------------------------------------------------------------ pertandingan dan keanggotaan
def kode_baru(c):
    abjad = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        kode = "".join(secrets.choice(abjad) for _ in range(5))
        if not c.execute("SELECT 1 FROM pertandingan WHERE kode=?", (kode,)).fetchone():
            return kode


def anggota_aktif(c, pid):
    """Pemain yang sedang berada di pertandingan pid, urut menurut waktu bergabung (yang paling awal dulu)."""
    ketua = c.execute("SELECT ketua_id FROM pertandingan WHERE id=?", (pid,)).fetchone()
    ketua_id = ketua["ketua_id"] if ketua else None
    out = []
    for r in c.execute("SELECT p.id, p.username, p.nama, a.gaya FROM anggota a JOIN pengguna p ON p.id = a.pengguna_id "
                       "WHERE a.pertandingan_id=? AND a.aktif=1 ORDER BY a.bergabung, p.id", (pid,)):
        d = dict(r)
        d["gaya_nama"] = gdss.PROFIL[d["gaya"]]["nama"]
        d["bobot"] = gdss.PROFIL[d["gaya"]]["bobot"]
        d["ketua"] = d["id"] == ketua_id
        out.append(d)
    return out


def pertandingan_saya(c, user_id):
    """Pertandingan berlangsung yang sedang diikuti pengguna, atau None."""
    return c.execute("SELECT t.* FROM anggota a JOIN pertandingan t ON t.id = a.pertandingan_id "
                     "WHERE a.pengguna_id=? AND a.aktif=1 AND t.status='berlangsung'", (user_id,)).fetchone()


def ringkas_pertandingan(c, t):
    ag = anggota_aktif(c, t["id"])
    ketua = next((a for a in ag if a["ketua"]), None)
    return {"id": t["id"], "kode": t["kode"], "nama": t["nama"], "status": t["status"], "publik": bool(t["publik"]),
            "ketua": ketua["nama"] if ketua else None, "anggota": [
                {"id": a["id"], "nama": a["nama"], "gaya": a["gaya"], "gaya_nama": a["gaya_nama"], "ketua": a["ketua"]}
                for a in ag],
            "penuh": len(ag) >= MAKS_ANGGOTA,
            "gaya_tersedia": [g for g in gdss.PROFIL if g not in {a["gaya"] for a in ag}]}


def pilih_gaya(c, pid, gaya):
    """Gaya yang diminta (atau yang pertama tersedia). Mengembalikan (gaya, None) atau (None, pesan)."""
    terpakai = {a["gaya"] for a in anggota_aktif(c, pid)}
    bebas = [g for g in gdss.PROFIL if g not in terpakai]
    if not bebas:
        return None, "Pertandingan sudah penuh."
    if gaya in (None, ""):
        return bebas[0], None
    if gaya not in gdss.PROFIL:
        return None, "Gaya main tidak dikenal. Pilihan: " + ", ".join(gdss.PROFIL) + "."
    if gaya in terpakai:
        return None, f"Gaya {gdss.PROFIL[gaya]['nama']} sudah dipakai anggota lain. Pilihan yang tersisa: " + ", ".join(bebas) + "."
    return gaya, None


def buat_pertandingan(c, user, nama, gaya, publik=True):
    if gaya not in (None, "") and gaya not in gdss.PROFIL:
        return None, (400, "Gaya main tidak dikenal. Pilihan: " + ", ".join(gdss.PROFIL) + ".")
    now = time.time()
    cur = c.execute("INSERT INTO pertandingan(kode,nama,ketua_id,status,dibuat,publik) VALUES(?,?,?,?,?,?)",
                    (kode_baru(c), nama, user["id"], "berlangsung", now, 1 if publik else 0))
    pid = cur.lastrowid
    c.execute("INSERT INTO anggota(pertandingan_id,pengguna_id,gaya,bergabung,terakhir,aktif) VALUES(?,?,?,?,?,1)",
              (pid, user["id"], gaya or next(iter(gdss.PROFIL)), now, now))
    permainan_baru(c, pid)
    return pid, None


def gabung_pertandingan(c, user, pid, gaya):
    t = c.execute("SELECT * FROM pertandingan WHERE id=?", (pid,)).fetchone()
    if not t:
        return None, (404, "Pertandingan tidak ditemukan.")
    if t["status"] != "berlangsung":
        return None, (409, "Pertandingan ini sudah berakhir.")
    if pertandingan_saya(c, user["id"]):
        return None, (409, "Anda masih berada di sebuah pertandingan. Keluar dulu sebelum bergabung ke yang lain.")
    if len(anggota_aktif(c, pid)) >= MAKS_ANGGOTA:
        return None, (409, "Pertandingan sudah penuh (maksimal 3 pemain).")
    g, pesan = pilih_gaya(c, pid, gaya)
    if pesan:
        return None, (409, pesan)
    now = time.time()
    c.execute("INSERT INTO anggota(pertandingan_id,pengguna_id,gaya,bergabung,terakhir,aktif) VALUES(?,?,?,?,?,1) "
              "ON CONFLICT(pertandingan_id,pengguna_id) DO UPDATE SET gaya=excluded.gaya, bergabung=excluded.bergabung, "
              "terakhir=excluded.terakhir, aktif=1", (pid, user["id"], g, now, now))
    setelah_perubahan_anggota(c, pid)
    return pid, None


def keluar_pertandingan(c, user_id, pid):
    """Pemain keluar. Usulannya pada ronde berjalan dibuang; anggota yang tersisa tidak perlu menunggunya."""
    c.execute("UPDATE anggota SET aktif=0 WHERE pertandingan_id=? AND pengguna_id=?", (pid, user_id))
    k = kasus_aktif(c, pid)
    if k and not c.execute("SELECT 1 FROM konsensus WHERE kasus_id=?", (k["id"],)).fetchone():
        c.execute("DELETE FROM usulan WHERE kasus_id=? AND pengguna_id=?", (k["id"], user_id))
    setelah_perubahan_anggota(c, pid)


def setelah_perubahan_anggota(c, pid, alasan="Semua pemain keluar dari pertandingan."):
    """Dipanggil setiap ada pemain yang bergabung atau keluar.
    - tidak ada pemain tersisa -> pertandingan berakhir otomatis;
    - Ketua keluar -> anggota paling awal menjadi Ketua;
    - penilaian individual ronde berjalan yang belum dikonsensuskan dibuang (kumpulan penilainya berubah), lalu
      dibuat ulang bila semua pemain yang tersisa sudah mengusulkan."""
    ag = anggota_aktif(c, pid)
    if not ag:
        c.execute("UPDATE pertandingan SET status='selesai', alasan_selesai=?, berakhir=? WHERE id=?",
                  (alasan, time.time(), pid))
        return
    if not any(a["ketua"] for a in ag):
        c.execute("UPDATE pertandingan SET ketua_id=? WHERE id=?", (ag[0]["id"], pid))
    k = kasus_aktif(c, pid)
    if k and not c.execute("SELECT 1 FROM konsensus WHERE kasus_id=?", (k["id"],)).fetchone():
        c.execute("DELETE FROM penilaian_individual WHERE kasus_id=?", (k["id"],))
        if not k["selesai"] and mesin.pustaka_ada() and all(s["sudah"] for s in status_usulan(c, k)):
            siapkan_penilaian(c, k)


def bersihkan_tidak_aktif(c):
    """Pemain yang tidak mengirim permintaan apa pun selama TIMEOUT_AKTIF detik dianggap keluar (menutup tab
    tanpa menekan Keluar). Pertandingan tanpa pemain berakhir otomatis."""
    batas = time.time() - TIMEOUT_AKTIF
    basi = c.execute("SELECT pertandingan_id, pengguna_id FROM anggota WHERE aktif=1 AND terakhir < ?", (batas,)).fetchall()
    for r in basi:
        keluar_pertandingan(c, r["pengguna_id"], r["pertandingan_id"])
    return len(basi)


# ------------------------------------------------------------------ ronde dan permainan
def permainan_baru(c, pid):
    p = c.execute("SELECT COALESCE(MAX(permainan), 0) + 1 FROM kasus WHERE pertandingan_id=?", (pid,)).fetchone()[0]
    buat_ronde(c, pid, p, 1, POSISI_AWAL["fen"], POSISI_AWAL["riwayat"])


def buat_ronde(c, pid, permainan, nomor, fen, riwayat, selesai=None):
    c.execute("INSERT INTO kasus(pertandingan_id,permainan,nomor,fen,riwayat,dibuat,selesai) VALUES(?,?,?,?,?,?,?)",
              (pid, permainan, nomor, fen, json.dumps(riwayat), time.time(), selesai))


def teks_riwayat(riwayat):
    """['e4','e5','Nf3'] -> '1. e4 e5 2. Nf3' (riwayat selalu dimulai dari posisi awal catur)."""
    return " ".join((f"{i // 2 + 1}. " if i % 2 == 0 else "") + san for i, san in enumerate(riwayat))


def kasus_aktif(c, pid):
    r = c.execute("SELECT * FROM kasus WHERE pertandingan_id=? ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
    if not r:
        return None
    riwayat = json.loads(r["riwayat"])
    return {"id": r["id"], "pertandingan_id": r["pertandingan_id"], "permainan": r["permainan"], "nomor": r["nomor"],
            "fen": r["fen"], "riwayat": riwayat, "riwayat_teks": teks_riwayat(riwayat), "selesai": r["selesai"],
            "sisi_tim": "putih" if r["fen"].split()[1] == "w" else "hitam"}


def status_usulan(c, kasus):
    sudah = {r["pengguna_id"]: r["waktu"] for r in
             c.execute("SELECT pengguna_id, waktu FROM usulan WHERE kasus_id=?", (kasus["id"],))}
    return [{**p, "sudah": p["id"] in sudah} for p in anggota_aktif(c, kasus["pertandingan_id"])]


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
    r = c.execute("SELECT k.kasus_id FROM konsensus k JOIN kasus s ON s.id = k.kasus_id "
                  "WHERE s.pertandingan_id=? AND s.permainan=? ORDER BY s.id DESC LIMIT 1",
                  (kasus["pertandingan_id"], kasus["permainan"])).fetchone()
    return baca_konsensus(c, r["kasus_id"]) if r else None


def baca_penilaian(c, kasus_id):
    r = c.execute("SELECT * FROM penilaian_individual WHERE kasus_id=?", (kasus_id,)).fetchone()
    if not r:
        return None
    return {"kasus_id": r["kasus_id"], "alternatif": json.loads(r["alternatif"]),
            "kriteria": json.loads(r["kriteria"]), "topsis": json.loads(r["topsis"]), "waktu": r["waktu"]}


def siapkan_penilaian(c, kasus):
    """Tahap 1, otomatis begitu semua anggota mengusulkan: gabungkan usulan, ukur C1-C5, jalankan TOPSIS
    tiap anggota dengan bobot gayanya. Hasilnya disimpan sebagai penilaian individual; Borda belum dijalankan.
    Mengembalikan (penilaian, None) atau (None, (status_http, pesan))."""
    if c.execute("SELECT 1 FROM konsensus WHERE kasus_id=?", (kasus["id"],)).fetchone():
        return None, (409, "Ronde ini sudah dinilai.")
    if c.execute("SELECT 1 FROM penilaian_individual WHERE kasus_id=?", (kasus["id"],)).fetchone():
        return baca_penilaian(c, kasus["id"]), None
    status = status_usulan(c, kasus)
    if not status:
        return None, (409, "Tidak ada pemain di pertandingan ini.")
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
    c.execute("INSERT INTO penilaian_individual(kasus_id,alternatif,kriteria,topsis,waktu) VALUES(?,?,?,?,?)",
              (kasus["id"], json.dumps(alternatif), json.dumps(kriteria), json.dumps(topsis), time.time()))
    return baca_penilaian(c, kasus["id"]), None


def jalankan_konsensus(c, kasus):
    """Tahap 2, dijalankan Ketua: voting Borda atas penilaian individual semua anggota, lalu langkah pemenang
    dimainkan, lawan membalas (algoritma catur biasa), dan ronde berikutnya dibuka.
    Mengembalikan (konsensus, None) atau (None, (status, pesan))."""
    if c.execute("SELECT 1 FROM konsensus WHERE kasus_id=?", (kasus["id"],)).fetchone():
        return None, (409, "Ronde ini sudah dinilai.")
    pen = baca_penilaian(c, kasus["id"])
    if not pen:
        return None, (409, "Belum semua anggota selesai dinilai: konsensus baru bisa dijalankan setelah semua mengusulkan.")
    alternatif, kriteria, topsis = pen["alternatif"], pen["kriteria"], pen["topsis"]
    k = gdss.konsensus_gaya(kriteria["nilai"], [t["gaya"] for t in topsis], [a["dukungan"] for a in alternatif])
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
        buat_ronde(c, kasus["pertandingan_id"], kasus["permainan"], kasus["nomor"] + 1, fen_baru, riwayat + [lawan_san],
                   selesai=mesin.status_akhir(fen_baru, tim))
    c.execute("INSERT INTO konsensus(kasus_id,alternatif,kriteria,topsis,borda,pemenang,pemenang_san,fen_setelah,"
              "lawan,lawan_san,lawan_sumber,akhir,waktu) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (kasus["id"], json.dumps(alternatif), json.dumps(kriteria), json.dumps(topsis), json.dumps(k["borda"]),
               menang["uci"], san, fen_setelah, lawan, lawan_san, lawan_sumber, akhir, time.time()))
    return baca_konsensus(c, kasus["id"]), None


def jalankan_penilaian(c, kasus):
    """Seluruh alur sekaligus (tahap 1 lalu tahap 2). Dipakai tes; di aplikasi, tahap 2 hanya oleh Ketua."""
    pen, galat = siapkan_penilaian(c, kasus)
    if galat:
        return None, galat
    return jalankan_konsensus(c, kasus)


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
    r = c.execute("SELECT p.id, p.username, p.nama FROM sesi s JOIN pengguna p ON p.id = s.pengguna_id "
                  "WHERE s.token=? AND s.kedaluwarsa >= ?", (token, time.time())).fetchone()
    return dict(r) if r else None


# ------------------------------------------------------------------ aplikasi web (FastAPI)
@asynccontextmanager
async def siklus(_app):
    saat_mulai()
    yield


app = FastAPI(title="SKAKMAT GDSS", version="3.0", lifespan=siklus,
              docs_url="/api/docs" if os.environ.get("SKAKMAT_DOCS") == "1" else None,
              redoc_url=None, openapi_url="/api/openapi.json" if os.environ.get("SKAKMAT_DOCS") == "1" else None)


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


def denyut(c, user):
    """Setiap permintaan dari pemain yang sedang bertanding menandainya masih aktif; yang diam terlalu lama dikeluarkan."""
    c.execute("UPDATE anggota SET terakhir=? WHERE pengguna_id=? AND aktif=1", (time.time(), user["id"]))
    c.commit()
    ada_basi = c.execute("SELECT 1 FROM anggota WHERE aktif=1 AND terakhir < ? LIMIT 1", (time.time() - TIMEOUT_AKTIF,)).fetchone()
    if ada_basi:
        with _kunci_ronde:
            bersihkan_tidak_aktif(c)
            c.commit()


def api(fungsi):
    """Bungkus handler sinkron: buka koneksi, cek sesi, jalankan di thread pool (SQLite dan engine memblokir)."""
    async def rute(request: Request):
        data = await baca_json(request) if request.method == "POST" else None

        def kerja():
            with db() as c:
                user = pengguna_dari_cookie(c, request.cookies.get("sesi"))
                if not user:
                    return galat(401, "Silakan masuk terlebih dahulu.")
                denyut(c, user)
                return fungsi(c, user, data, request)
        return await run_in_threadpool(kerja)
    return rute


def butuh_pertandingan(c, user):
    t = pertandingan_saya(c, user["id"])
    if not t:
        return None, galat(409, "Anda belum berada di sebuah pertandingan. Buat atau bergabung dulu dari lobi.")
    return t, None


def get_lobi(c, user, data, request):
    """Daftar pertandingan yang sedang berlangsung dan pertandingan milik pengguna (bila ada)."""
    saya = pertandingan_saya(c, user["id"])
    daftar = [ringkas_pertandingan(c, t) for t in
              c.execute("SELECT * FROM pertandingan WHERE status='berlangsung' AND (publik=1 OR id=?) ORDER BY id DESC LIMIT 50",
                        (saya["id"] if saya else -1,))]
    return JSONResponse({"pengguna": user, "pertandingan_saya": saya["id"] if saya else None, "daftar": daftar,
                         "profil": gdss.PROFIL, "maks_anggota": MAKS_ANGGOTA})


def post_buat(c, user, data, request):
    data = data or {}
    nama = data.get("nama")
    nama = nama.strip() if isinstance(nama, str) else ""
    if not nama:
        nama = f"Meja {user['nama']}"
    if len(nama) > 40 or any(ord(ch) < 32 for ch in nama):
        return galat(400, "Nama pertandingan paling panjang 40 karakter, tanpa karakter kontrol.")
    gaya = data.get("gaya")
    if gaya is not None and not isinstance(gaya, str):
        return galat(400, "Gaya main tidak valid.")
    publik = data.get("publik", True)
    if not isinstance(publik, bool):
        return galat(400, "Pilihan publik atau privat tidak valid.")
    with _kunci_ronde:
        if pertandingan_saya(c, user["id"]):
            return galat(409, "Anda masih berada di sebuah pertandingan. Keluar dulu sebelum membuat yang baru.")
        pid, g = buat_pertandingan(c, user, nama, gaya, publik)
        if g:
            return galat(*g)
        c.commit()
    return JSONResponse({"ok": True, "pertandingan": ringkas_pertandingan(c, c.execute(
        "SELECT * FROM pertandingan WHERE id=?", (pid,)).fetchone())})


def post_gabung(c, user, data, request):
    data = data or {}
    kode = data.get("kode")
    pid = data.get("id")
    gaya = data.get("gaya")
    if gaya is not None and not isinstance(gaya, str):
        return galat(400, "Gaya main tidak valid.")
    if isinstance(kode, str) and kode.strip():
        r = c.execute("SELECT id FROM pertandingan WHERE kode=?", (kode.strip().upper(),)).fetchone()
        pid = r["id"] if r else None
    elif isinstance(pid, int) and not isinstance(pid, bool):
        r = c.execute("SELECT publik FROM pertandingan WHERE id=?", (pid,)).fetchone()
        if r and not r["publik"]:                  # pertandingan privat tidak bisa dimasuki lewat id, hanya lewat kode
            return galat(404, "Pertandingan tidak ditemukan. Pertandingan privat hanya bisa dimasuki dengan kode.")
    if isinstance(pid, bool) or not isinstance(pid, int):
        return galat(404, "Pertandingan tidak ditemukan.")
    with _kunci_ronde:
        hasil, g = gabung_pertandingan(c, user, pid, gaya)
        if g:
            return galat(*g)
        c.commit()
    return JSONResponse({"ok": True, "pertandingan": ringkas_pertandingan(c, c.execute(
        "SELECT * FROM pertandingan WHERE id=?", (pid,)).fetchone())})


def post_keluar_pertandingan(c, user, data, request):
    with _kunci_ronde:
        t = pertandingan_saya(c, user["id"])
        if not t:
            return galat(409, "Anda tidak sedang berada di pertandingan.")
        keluar_pertandingan(c, user["id"], t["id"])
        c.commit()
        sisa = c.execute("SELECT status, alasan_selesai FROM pertandingan WHERE id=?", (t["id"],)).fetchone()
    return JSONResponse({"ok": True, "pertandingan_berakhir": sisa["status"] == "selesai", "alasan": sisa["alasan_selesai"]})


def get_ronde(c, user, data, request):
    """Keadaan ronde pertandingan pengguna. Tidak pernah memanggil engine (semua angka sudah dihitung saat
    penilaian), jadi aman dipanggil berkala. Usulan anggota lain baru terlihat setelah ronde dinilai, supaya
    usulan tiap orang tetap independen."""
    t = pertandingan_saya(c, user["id"])
    if not t:
        return JSONResponse({"pengguna": user, "pertandingan": None})
    kasus = kasus_aktif(c, t["id"])
    status = status_usulan(c, kasus)
    saya = c.execute("SELECT langkah, san, waktu FROM usulan WHERE kasus_id=? AND pengguna_id=?",
                     (kasus["id"], user["id"])).fetchone()
    konsensus = baca_konsensus(c, kasus["id"])
    penilaian = None if konsensus else baca_penilaian(c, kasus["id"])
    bisa_usul = mesin.pustaka_ada() and not konsensus and not penilaian and not kasus["selesai"]
    ketua = next((s for s in status if s["ketua"]), None)
    saya_ketua = bool(ketua) and ketua["id"] == user["id"]
    return JSONResponse({
        "pengguna": {**user, "gaya": next((s["gaya"] for s in status if s["id"] == user["id"]), None)},
        "pertandingan": ringkas_pertandingan(c, t), "peserta": status, "kasus": kasus,
        "kriteria": gdss.KRITERIA, "profil": gdss.PROFIL,
        "semua_sudah": all(s["sudah"] for s in status),
        "usulan_saya": {"uci": saya["langkah"], "san": saya["san"], "waktu": saya["waktu"]} if saya else None,
        "langkah_sah": mesin.langkah_sah(kasus["fen"]) if bisa_usul else [],
        "ketua": ketua["username"] if ketua else None,
        "saya_ketua": saya_ketua,
        "penilaian": penilaian,                       # penilaian individual semua anggota, menunggu konsensus Ketua
        "bisa_konsensus": bool(penilaian) and saya_ketua,
        "bisa_mundur": saya_ketua and kasus["nomor"] > 1,      # kembali ke giliran sebelumnya (hanya Ketua)
        "konsensus": konsensus,                       # ronde aktif sudah dikonsensuskan (hanya bila permainan selesai)
        "hasil_terakhir": konsensus or hasil_terakhir(c, kasus),
        "server": {"python_chess": mesin.pustaka_ada(), "stockfish": bool(mesin.path_engine())},
    })


def post_usul(c, user, data, request):
    langkah = data.get("langkah") if data else None
    if not isinstance(langkah, str):
        return galat(400, "Usulan harus berupa satu langkah, mis. e2e4.")
    with _kunci_ronde:
        t, g = butuh_pertandingan(c, user)
        if g:
            return g
        kasus = kasus_aktif(c, t["id"])
        if kasus["selesai"]:
            return galat(409, "Permainan sudah selesai: " + kasus["selesai"] + " Mulai permainan baru.")
        if c.execute("SELECT 1 FROM konsensus WHERE kasus_id=?", (kasus["id"],)).fetchone():
            return galat(409, "Ronde ini sudah dinilai; usulan dikunci.")
        if c.execute("SELECT 1 FROM penilaian_individual WHERE kasus_id=?", (kasus["id"],)).fetchone():
            return galat(409, "Semua anggota sudah dinilai; usulan dikunci sambil menunggu Ketua menjalankan konsensus.")
        if not mesin.pustaka_ada():
            return galat(503, "Server tidak bisa memeriksa langkah: pustaka python-chess tidak terpasang.")
        m, pesan = mesin.validasi_usulan(kasus["fen"], langkah)
        if pesan:
            return galat(400, pesan)
        _, san = mesin.mainkan(kasus["fen"], m.uci())
        c.execute("INSERT OR REPLACE INTO usulan(kasus_id,pengguna_id,langkah,san,waktu) VALUES(?,?,?,?,?)",
                  (kasus["id"], user["id"], m.uci(), san, time.time()))
        c.commit()
        out = {"ok": True, "usulan": {"uci": m.uci(), "san": san}, "dinilai": False, "penilaian_siap": False}
        if all(s["sudah"] for s in status_usulan(c, kasus)):
            pen, g2 = siapkan_penilaian(c, kasus)
            c.commit()
            if g2:
                out["galat_penilaian"] = g2[1]
            else:
                out.update(penilaian_siap=True, penilaian=pen)
        return JSONResponse(out)


def post_konsensus(c, user, data, request):
    """Konsensus Borda. Hanya Ketua pertandingan (jabatan tertinggi), dan hanya setelah semua anggota selesai dinilai."""
    with _kunci_ronde:
        t, g = butuh_pertandingan(c, user)
        if g:
            return g
        if t["ketua_id"] != user["id"]:
            return galat(403, "Hanya Ketua (jabatan tertinggi) yang boleh menjalankan konsensus.")
        kasus = kasus_aktif(c, t["id"])
        if c.execute("SELECT 1 FROM penilaian_individual WHERE kasus_id=?", (kasus["id"],)).fetchone() is None:
            pen, g2 = siapkan_penilaian(c, kasus)    # bila tahap 1 sempat gagal (mis. engine mati), coba lagi
            c.commit()
            if g2:
                return galat(*g2)
        hasil, g2 = jalankan_konsensus(c, kasus)
        c.commit()
    if g2:
        return galat(*g2)
    return JSONResponse({"ok": True, "konsensus": hasil})


def post_ulang(c, user, data, request):
    """Permainan baru dari posisi awal. Semua anggota boleh; riwayat lama tetap tersimpan."""
    with _kunci_ronde:
        t, g = butuh_pertandingan(c, user)
        if g:
            return g
        permainan_baru(c, t["id"])
        c.commit()
        return JSONResponse({"ok": True, "kasus": kasus_aktif(c, t["id"])})


def post_mundur(c, user, data, request):
    """Kembali ke giliran sebelumnya (hanya Ketua). Ronde berjalan dibuang; ronde sebelumnya dibuka lagi tanpa
    konsensus, penilaian, dan usulan, sehingga semua anggota mengusulkan ulang. Riwayat tidak ikut berubah."""
    with _kunci_ronde:
        t, g = butuh_pertandingan(c, user)
        if g:
            return g
        if t["ketua_id"] != user["id"]:
            return galat(403, "Hanya Ketua yang boleh kembali ke giliran sebelumnya.")
        kasus = kasus_aktif(c, t["id"])
        if kasus["nomor"] <= 1:
            return galat(409, "Sudah di giliran pertama permainan ini; tidak ada giliran sebelumnya.")
        sebelumnya = c.execute("SELECT id FROM kasus WHERE pertandingan_id=? AND permainan=? AND nomor=?",
                               (t["id"], kasus["permainan"], kasus["nomor"] - 1)).fetchone()
        if not sebelumnya:
            return galat(409, "Giliran sebelumnya tidak ditemukan.")
        c.execute("DELETE FROM kasus WHERE id=?", (kasus["id"],))      # usulan dan penilaian ikut terhapus (CASCADE)
        for tabel in ("konsensus", "penilaian_individual", "usulan"):
            c.execute(f"DELETE FROM {tabel} WHERE kasus_id=?", (sebelumnya["id"],))
        c.commit()
        return JSONResponse({"ok": True, "kasus": kasus_aktif(c, t["id"])})


app.add_api_route("/api/lobi", api(get_lobi), methods=["GET"])
app.add_api_route("/api/pertandingan/buat", api(post_buat), methods=["POST"])
app.add_api_route("/api/pertandingan/gabung", api(post_gabung), methods=["POST"])
app.add_api_route("/api/pertandingan/keluar", api(post_keluar_pertandingan), methods=["POST"])
app.add_api_route("/api/ronde", api(get_ronde), methods=["GET"])
app.add_api_route("/api/usul", api(post_usul), methods=["POST"])
app.add_api_route("/api/konsensus", api(post_konsensus), methods=["POST"])
app.add_api_route("/api/ulang", api(post_ulang), methods=["POST"])
app.add_api_route("/api/mundur", api(post_mundur), methods=["POST"])


@app.post("/api/keluar")
async def post_keluar(request: Request):
    """Keluar dari akun. Pemain otomatis keluar dari pertandingannya; bila ia yang terakhir, pertandingan berakhir."""
    token = request.cookies.get("sesi")

    def kerja():
        with db() as c:
            user = pengguna_dari_cookie(c, token)
            if user:
                with _kunci_ronde:
                    t = pertandingan_saya(c, user["id"])
                    if t:
                        keluar_pertandingan(c, user["id"], t["id"])
                    c.execute("DELETE FROM sesi WHERE token=?", (token,))
                    c.commit()
        resp = JSONResponse({"ok": True})
        resp.headers["Set-Cookie"] = cookie_sesi("", 0)
        return resp
    return await run_in_threadpool(kerja)


@app.get("/api/me")
async def get_me(request: Request):
    def kerja():
        with db() as c:
            user = pengguna_dari_cookie(c, request.cookies.get("sesi"))
            if user:
                denyut(c, user)
                t = pertandingan_saya(c, user["id"])
                user = {**user, "pertandingan": t["id"] if t else None}
            return JSONResponse({"pengguna": user})
    return await run_in_threadpool(kerja)


def _sesi_baru(c, pengguna):
    token = buat_sesi(c, pengguna["id"])
    resp = JSONResponse({"pengguna": {"id": pengguna["id"], "username": pengguna["username"], "nama": pengguna["nama"]}})
    resp.headers["Set-Cookie"] = cookie_sesi(token, SESI_DETIK)
    return resp


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
            return _sesi_baru(c, r)
    return await run_in_threadpool(kerja)


@app.post("/api/daftar")
async def post_daftar(request: Request):
    """Akun baru. Nama pengguna 3-20 karakter (huruf kecil, angka, garis bawah), nama tampilan 2-30 karakter,
    kata sandi minimal 6 karakter. Langsung masuk setelah mendaftar."""
    data = await baca_json(request)
    if not data or not all(isinstance(data.get(k), str) for k in ("username", "nama", "sandi")):
        return galat(400, "Isi nama pengguna, nama tampilan, dan kata sandi.")
    username, nama, sandi = data["username"].strip().lower(), data["nama"].strip(), data["sandi"]
    if not RE_USERNAME.match(username):
        return galat(400, "Nama pengguna 3 sampai 20 karakter: huruf kecil, angka, dan garis bawah.")
    if not 2 <= len(nama) <= 30 or any(ord(ch) < 32 for ch in nama):
        return galat(400, "Nama tampilan 2 sampai 30 karakter.")
    if not 6 <= len(sandi) <= 100:
        return galat(400, "Kata sandi 6 sampai 100 karakter.")
    ip = request.client.host if request.client else "?"

    def kerja():
        sekarang = time.time()
        riwayat = [w for w in pendaftaran.get(ip, []) if w > sekarang - DAFTAR_JENDELA]
        if len(riwayat) >= DAFTAR_MAKS:
            return galat(429, "Terlalu banyak pendaftaran dari alamat ini. Coba lagi nanti.")
        with db() as c:
            garam = secrets.token_bytes(16)
            try:
                cur = c.execute("INSERT INTO pengguna(username,nama,garam,sandi,dibuat) VALUES(?,?,?,?,?)",
                                (username, nama, garam, hash_sandi(sandi, garam), sekarang))
            except sqlite3.IntegrityError:
                return galat(409, "Nama pengguna sudah dipakai. Pilih yang lain.")
            pendaftaran[ip] = riwayat + [sekarang]
            return _sesi_baru(c, {"id": cur.lastrowid, "username": username, "nama": nama})
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
