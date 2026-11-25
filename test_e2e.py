"""Tes ujung ke ujung: jalankan server pada basis data sementara, lalu uji pendaftaran dan login, lobi
(buat, gabung, keluar, pertandingan berakhir otomatis), peran Ketua, usulan langkah lewat API, penilaian individual
(C1-C5 -> TOPSIS per gaya), konsensus Borda oleh Ketua, balasan lawan, keanggotaan yang berubah di tengah ronde,
pemain tidak aktif, dan migrasi basis data lama.

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
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import gdss

PORT = 8765
AKUN = {"anggota1": "anggota123-1", "anggota2": "anggota123-2", "anggota3": "anggota123-3"}
AWAL = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2P2N2/PP1P1PPP/RNBQK2R w KQkq - 4 5"


class Klien:
    def __init__(self, port=PORT):
        self.base = f"http://127.0.0.1:{port}"
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def minta(self, path, body=None, origin=None, mentah=None):
        data = mentah if mentah is not None else (None if body is None else json.dumps(body).encode())
        req = urllib.request.Request(self.base + path, data=data,
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


def masuk(user, port=PORT):
    k = Klien(port)
    st, j = k.minta("/api/login", {"username": user, "sandi": AKUN[user]})
    cek(st == 200 and j["pengguna"]["username"] == user, f"login {user}")
    return k


def peserta_username(j):
    return [p["username"] for p in j["peserta"]]


# ------------------------------------------------------------------ 1. akun
def tes_akun():
    anon = Klien()
    cek(anon.minta("/api/lobi")[0] == 401 and anon.minta("/api/ronde")[0] == 401, "tanpa login ditolak (401)")
    cek(anon.minta("/api/login", {"username": "anggota1", "sandi": "salah"})[0] == 401, "sandi salah ditolak")
    cek(anon.minta("/api/login", {"username": "anggota1", "sandi": "anggota123-1"}, origin="http://evil.example")[0] == 403,
        "POST dengan Origin asing ditolak (403)")
    for isi, alasan in (({"username": "AB", "nama": "Budi", "sandi": "rahasia1"}, "nama pengguna terlalu pendek"),
                        ({"username": "Budi Satu", "nama": "Budi", "sandi": "rahasia1"}, "nama pengguna memuat spasi/huruf besar"),
                        ({"username": "budi_99", "nama": "B", "sandi": "rahasia1"}, "nama tampilan terlalu pendek"),
                        ({"username": "budi_99", "nama": "Budi", "sandi": "abc"}, "kata sandi terlalu pendek"),
                        ({"username": "budi_99", "nama": "Budi"}, "kata sandi tidak dikirim")):
        cek(anon.minta("/api/daftar", isi)[0] == 400, f"pendaftaran ditolak (400): {alasan}")
    k = Klien()
    st, j = k.minta("/api/daftar", {"username": "budi_99", "nama": "Budi", "sandi": "rahasia1"})
    cek(st == 200 and j["pengguna"]["username"] == "budi_99", "akun baru berhasil didaftarkan dan langsung masuk")
    cek(k.minta("/api/me")[1]["pengguna"]["nama"] == "Budi", "sesi akun baru aktif (/api/me)")
    cek(Klien().minta("/api/daftar", {"username": "budi_99", "nama": "Lain", "sandi": "rahasia2"})[0] == 409,
        "nama pengguna yang sama tidak bisa didaftarkan dua kali (409)")
    k2 = Klien()
    cek(k2.minta("/api/login", {"username": "budi_99", "sandi": "rahasia1"})[0] == 200
        and Klien().minta("/api/login", {"username": "budi_99", "sandi": "rahasia1x"})[0] == 401,
        "akun baru bisa login dengan sandinya, sandi salah ditolak")
    st, _ = k.minta("/api/keluar", {})
    cek(st == 200 and k.minta("/api/me")[1]["pengguna"] is None, "keluar akun menghapus sesi")
    lama = [masuk("anggota1").minta(p, {})[0] for p in ("/api/nilai", "/api/kasus-baru", "/api/usul-kandidat")]
    cek(lama == [410, 410, 410], "endpoint alur lama dinonaktifkan (410)")
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/..%2fapp.py")
        cek(False, "path traversal harus ditolak")
    except urllib.error.HTTPError as e:
        cek(e.code == 404, "path traversal ditolak (404)")


# ------------------------------------------------------------------ 2. lobi
def tes_lobi():
    a1, a2, a3 = masuk("anggota1"), masuk("anggota2"), masuk("anggota3")
    st, j = a1.minta("/api/lobi")
    cek(st == 200 and j["daftar"] == [] and j["pertandingan_saya"] is None, "lobi awal kosong")
    st, j = a1.minta("/api/ronde")
    cek(st == 200 and j["pertandingan"] is None, "belum bertanding: /api/ronde memberi pertandingan = null")
    for p in ("/api/usul", "/api/konsensus", "/api/ulang", "/api/pertandingan/keluar"):
        st, _ = a1.minta(p, {"langkah": "d2d4"})
        cek(st == 409, f"{p} tanpa pertandingan ditolak (409)")
    st, j = a1.minta("/api/pertandingan/buat", {"nama": "Meja Uji", "gaya": "tidak-ada"})
    cek(st == 400, "gaya main tidak dikenal ditolak (400)")
    st, j = a1.minta("/api/pertandingan/buat", {"nama": "Meja Uji", "gaya": "menyerang"})
    t = j["pertandingan"]
    cek(st == 200 and len(t["kode"]) == 5 and t["ketua"] == "Anggota 1" and [a["gaya"] for a in t["anggota"]] == ["menyerang"],
        f"anggota1 membuat pertandingan {t['kode']} dan menjadi Ketua")
    st, j = a1.minta("/api/ronde")
    cek(j["pertandingan"]["id"] == t["id"] and j["saya_ketua"] is True and j["kasus"]["fen"] == AWAL
        and j["kasus"]["nomor"] == 1 and len(j["langkah_sah"]) > 20, "ronde 1 dimulai di posisi awal; pembuat = Ketua")
    cek(a1.minta("/api/pertandingan/buat", {"nama": "Lagi"})[0] == 409, "pemain yang sedang bertanding tidak bisa membuat lagi (409)")
    st, j = a2.minta("/api/pertandingan/gabung", {"id": t["id"], "gaya": "menyerang"})
    cek(st == 409 and "sudah dipakai" in j["galat"], f"gaya yang sudah dipakai ditolak: {j.get('galat')!r}")
    cek(a2.minta("/api/pertandingan/gabung", {"id": 9999})[0] == 404, "pertandingan tidak ada (404)")
    cek(a2.minta("/api/pertandingan/gabung", {"kode": "ZZZZZ"})[0] == 404, "kode salah (404)")
    st, j = a2.minta("/api/pertandingan/gabung", {"kode": t["kode"].lower(), "gaya": "seimbang"})
    cek(st == 200 and len(j["pertandingan"]["anggota"]) == 2, "anggota2 bergabung lewat kode (huruf kecil diterima)")
    st, j = a3.minta("/api/pertandingan/gabung", {"id": t["id"]})
    cek(st == 200 and j["pertandingan"]["anggota"][2]["gaya"] == "bertahan", "anggota3 bergabung tanpa memilih: dapat gaya yang tersisa (bertahan)")
    b = Klien()
    b.minta("/api/login", {"username": "budi_99", "sandi": "rahasia1"})
    st, j = b.minta("/api/pertandingan/gabung", {"id": t["id"]})
    cek(st == 409 and "penuh" in j["galat"], "pemain keempat ditolak: pertandingan penuh (maksimal 3)")
    st, j = b.minta("/api/lobi")
    cek(len(j["daftar"]) == 1 and j["daftar"][0]["penuh"] is True and j["daftar"][0]["gaya_tersedia"] == [], "lobi menampilkan pertandingan penuh")
    return t, {"anggota1": a1, "anggota2": a2, "anggota3": a3, "budi_99": b}


# ------------------------------------------------------------------ 3. satu ronde penuh
def tes_ronde(t, K):
    a1, a2, a3 = K["anggota1"], K["anggota2"], K["anggota3"]
    cek(a1.minta("/api/mundur", {})[0] == 409, "mundur di giliran pertama ditolak (409)")
    st, j = a1.minta("/api/usul", {"langkah": "d2d5"})
    cek(st == 400 and "tidak sah" in j["galat"], f"usulan ilegal ditolak: {j.get('galat')!r}")
    cek(a1.minta("/api/usul", {"langkah": "e5e4"})[0] == 400, "menggerakkan bidak lawan ditolak")
    cek(a1.minta("/api/usul", {"langkah": 42})[0] == 400 and a1.minta("/api/usul", mentah=b"bukan json")[0] == 400,
        "usulan bukan teks / bukan JSON ditolak (400)")
    cek(a2.minta("/api/konsensus", {})[0] == 403, "anggota biasa tidak boleh menjalankan konsensus (403)")
    cek(a1.minta("/api/konsensus", {})[0] == 409, "Ketua pun ditolak (409) selama usulan belum lengkap")
    st, j = a1.minta("/api/usul", {"langkah": "d2d3"})
    cek(st == 200 and j["usulan"]["san"] == "d3" and j["penilaian_siap"] is False, "anggota1 mengusulkan d3")
    st, j = a1.minta("/api/usul", {"langkah": "d2d4"})
    cek(st == 200 and j["usulan"]["san"] == "d4", "anggota1 mengganti usulan menjadi d4 sebelum penilaian")
    st, j = a2.minta("/api/ronde")
    cek(j["usulan_saya"] is None and [p["sudah"] for p in j["peserta"]] == [True, False, False] and "d2d4" not in json.dumps(j["peserta"]),
        "anggota2 melihat anggota1 sudah mengusulkan, tapi tidak melihat langkahnya")
    st, j = a2.minta("/api/usul", {"langkah": "d4"})
    cek(st == 200 and j["usulan"]["uci"] == "d2d4", "anggota2 mengusulkan langkah yang sama (notasi SAN diterima)")
    t0 = time.time()
    st, j = a3.minta("/api/usul", {"langkah": "e1g1"})
    d = time.time() - t0
    cek(st == 200 and j["penilaian_siap"] is True and j["dinilai"] is False and "konsensus" not in j and "borda" not in json.dumps(j),
        f"usulan ketiga menyiapkan penilaian individual ({d:.2f} s); konsensus belum dijalankan")
    for u, kl in K.items():
        if u == "budi_99":
            continue
        st, jr = kl.minta("/api/ronde")
        cek(st == 200 and len(jr["penilaian"]["topsis"]) == 3 and jr["konsensus"] is None and jr["hasil_terakhir"] is None
            and jr["bisa_konsensus"] == (u == "anggota1") and "borda" not in json.dumps(jr["penilaian"]),
            f"{u} melihat penilaian individual ketiga anggota (tanpa Borda); tombol konsensus hanya untuk Ketua")
    st, j = a1.minta("/api/usul", {"langkah": "g1f3"})
    cek(st == 409, "usulan dikunci setelah penilaian individual dibuat (409)")
    for u in ("anggota2", "anggota3"):
        cek(K[u].minta("/api/konsensus", {})[0] == 403, f"{u} (bukan Ketua) ditolak menjalankan konsensus (403)")
    st, j = a1.minta("/api/konsensus", {})
    cek(st == 200 and j["konsensus"], "Ketua menjalankan konsensus Borda")
    cek(a1.minta("/api/konsensus", {})[0] == 409, "konsensus kedua pada ronde yang sama ditolak (409)")
    k = j["konsensus"]
    alt = k["alternatif"]
    cek([a["san"] for a in alt] == ["d4", "O-O"] and [a["dukungan"] for a in alt] == [2, 1],
        "usulan ganda digabung: 2 alternatif, dukungan d4 = 2, O-O = 1")
    nilai = k["kriteria"]["nilai"]
    cek(len(nilai) == 2 and all(len(b) == 5 and all(1 <= v <= 5 for v in b) for b in nilai),
        f"C1-C5 tersimpan per alternatif ({k['kriteria']['sumber']['mode']}): {nilai}")
    cek([t_["gaya"] for t_ in k["topsis"]] == ["menyerang", "seimbang", "bertahan"]
        and all(t_["hasil"]["rank"] == gdss.topsis(nilai, gdss.kriteria_profil(t_["gaya"]))["rank"] for t_ in k["topsis"]),
        "tiga peringkat TOPSIS (satu per gaya) = hitungan independen")
    ref = gdss.konsensus_gaya(nilai, ["menyerang", "seimbang", "bertahan"], [2, 1])
    cek(all(abs(a - b) < 1e-12 for a, b in zip(ref["borda"]["nilai"], k["borda"]["nilai"]))
        and ref["borda"]["rank"] == k["borda"]["rank"] and alt[ref["pemenang"]]["uci"] == k["pemenang"]["uci"],
        f"hasil Borda = hitungan independen (pemenang {k['pemenang']['san']})")
    cek(k["lawan"] and k["lawan"]["san"] and k["lawan"]["sumber"],
        f"lawan membalas otomatis dengan catur biasa: {k['lawan']['san']} ({k['lawan']['sumber']})")
    for u in ("anggota1", "anggota2", "anggota3"):
        st, jr = K[u].minta("/api/ronde")
        h = jr["hasil_terakhir"]
        cek(st == 200 and h and h["kasus_id"] == k["kasus_id"] and len(h["topsis"]) == 3, f"{u} melihat hasil ronde 1 beserta penilaian tiap anggota")
    cek(jr["kasus"]["nomor"] == 2 and len(jr["kasus"]["riwayat"]) == 10 and jr["penilaian"] is None
        and not any(p["sudah"] for p in jr["peserta"]), f"ronde 2 dibuka otomatis: {jr['kasus']['riwayat_teks']}")
    cek(a1.minta("/api/konsensus", {})[0] == 409, "ronde 2 belum bisa dikonsensuskan sebelum ada usulan")
    # kembali ke giliran sebelumnya
    cek(a2.minta("/api/ronde")[1]["bisa_mundur"] is False and a1.minta("/api/ronde")[1]["bisa_mundur"] is True,
        "tombol kembali hanya untuk Ketua")
    cek(a2.minta("/api/mundur", {})[0] == 403, "anggota biasa ditolak kembali ke giliran sebelumnya (403)")
    st, j = a1.minta("/api/mundur", {})
    cek(st == 200 and j["kasus"]["nomor"] == 1 and len(j["kasus"]["riwayat"]) == 8, "Ketua kembali ke giliran 1 (riwayat 8 langkah)")
    st, jr = a2.minta("/api/ronde")
    cek(jr["kasus"]["nomor"] == 1 and jr["penilaian"] is None and jr["hasil_terakhir"] is None
        and not any(p["sudah"] for p in jr["peserta"]) and jr["bisa_mundur"] is False,
        "giliran 1 dibuka lagi tanpa usulan, penilaian, dan konsensus")
    for kl, lg in ((a1, "d2d4"), (a2, "d2d4"), (a3, "e1g1")):
        kl.minta("/api/usul", {"langkah": lg})
    st, j = a1.minta("/api/konsensus", {})
    st2, jr = a1.minta("/api/ronde")
    cek(st == 200 and jr["kasus"]["nomor"] == 2 and len(jr["kasus"]["riwayat"]) == 10,
        "usulan ulang dan konsensus berjalan lagi; ronde 2 terbuka kembali")


# ------------------------------------------------------------------ 4. anggota keluar / bergabung di tengah ronde
def tes_keanggotaan(t, K):
    a1, a2, a3 = K["anggota1"], K["anggota2"], K["anggota3"]
    st, j = a2.minta("/api/ronde")
    sah = [m["uci"] for m in j["langkah_sah"]]
    cek(a2.minta("/api/usul", {"langkah": sah[0]})[0] == 200, "ronde 2: anggota2 mengusulkan")
    st, j = a3.minta("/api/pertandingan/keluar", {})
    cek(st == 200 and j["pertandingan_berakhir"] is False, "anggota3 keluar dari pertandingan; pertandingan lanjut")
    st, j = a3.minta("/api/ronde")
    cek(j["pertandingan"] is None, "anggota3 kembali ke lobi (tidak lagi punya pertandingan)")
    st, j = a1.minta("/api/ronde")
    cek(peserta_username(j) == ["anggota1", "anggota2"] and j["pertandingan"]["penuh"] is False
        and j["pertandingan"]["gaya_tersedia"] == ["bertahan"], "anggota tersisa 2 orang; gaya bertahan tersedia lagi")
    st, j = a1.minta("/api/usul", {"langkah": sah[1]})
    cek(st == 200 and j["penilaian_siap"] is True and len(j["penilaian"]["topsis"]) == 2,
        "ronde dinilai hanya dari 2 anggota yang tersisa (anggota yang keluar tidak ditunggu)")
    st, j = a3.minta("/api/pertandingan/gabung", {"id": t["id"], "gaya": "bertahan"})
    cek(st == 200, "anggota3 bergabung lagi di tengah ronde, setelah penilaian dibuat")
    st, j = a1.minta("/api/ronde")
    cek(j["penilaian"] is None and j["bisa_konsensus"] is False and [p["sudah"] for p in j["peserta"]] == [True, True, False]
        and len(j["langkah_sah"]) > 20, "penilaian lama dibatalkan; ronde menunggu usulan anggota baru")
    st, j = a3.minta("/api/usul", {"langkah": sah[2]})
    cek(st == 200 and j["penilaian_siap"] is True and len(j["penilaian"]["topsis"]) == 3, "usulan anggota baru membuat penilaian 3 anggota")
    st, j = a1.minta("/api/pertandingan/keluar", {})
    cek(st == 200 and j["pertandingan_berakhir"] is False, "Ketua (anggota1) keluar")
    st, j = a2.minta("/api/ronde")
    cek(j["ketua"] == "anggota2" and j["saya_ketua"] is True and j["bisa_konsensus"] is True
        and peserta_username(j) == ["anggota2", "anggota3"] and len(j["penilaian"]["topsis"]) == 2,
        "anggota2 (bergabung paling awal) menjadi Ketua baru; penilaian dihitung ulang dari 2 anggota")
    cek(a3.minta("/api/konsensus", {})[0] == 403, "anggota3 tetap tidak boleh menjalankan konsensus")
    st, j = a2.minta("/api/konsensus", {})
    cek(st == 200 and j["konsensus"]["pemenang"]["san"], f"Ketua baru menjalankan konsensus ({j['konsensus']['pemenang']['san']})")
    st, j = a1.minta("/api/ronde")
    cek(j["pertandingan"] is None, "anggota1 yang sudah keluar tidak melihat pertandingan itu lagi")
    st, j = a1.minta("/api/pertandingan/gabung", {"id": t["id"], "gaya": "menyerang"})
    cek(st == 200, "anggota1 bisa bergabung lagi (sebagai anggota biasa)")
    st, j = a1.minta("/api/ronde")
    cek(j["saya_ketua"] is False and j["ketua"] == "anggota2", "anggota1 yang kembali bukan Ketua; Ketua tetap anggota2")
    st, j = a2.minta("/api/ulang", {})
    cek(st == 200 and j["kasus"]["permainan"] == 2 and j["kasus"]["nomor"] == 1 and j["kasus"]["fen"] == AWAL,
        "anggota memulai permainan baru dari posisi awal")


# ------------------------------------------------------------------ 5. pertandingan berakhir otomatis
def tes_berakhir(t, K):
    a1, a2, a3 = K["anggota1"], K["anggota2"], K["anggota3"]
    st, j = a1.minta("/api/pertandingan/keluar", {})
    cek(st == 200 and j["pertandingan_berakhir"] is False, "anggota1 keluar (2 pemain tersisa)")
    st, j = a3.minta("/api/keluar", {})
    cek(st == 200, "anggota3 keluar dari akun (logout): otomatis keluar dari pertandingan")
    st, j = a2.minta("/api/ronde")
    cek(peserta_username(j) == ["anggota2"], "tersisa satu pemain: anggota2")
    st, j = a2.minta("/api/pertandingan/keluar", {})
    cek(st == 200 and j["pertandingan_berakhir"] is True and "Semua pemain keluar" in j["alasan"],
        "pemain terakhir keluar: pertandingan berakhir otomatis")
    st, j = a2.minta("/api/lobi")
    cek(j["daftar"] == [] and j["pertandingan_saya"] is None, "pertandingan yang berakhir hilang dari lobi")
    b = K["budi_99"]
    st, j = b.minta("/api/pertandingan/gabung", {"id": t["id"]})
    cek(st == 409 and "berakhir" in j["galat"], "pertandingan yang sudah berakhir tidak bisa dimasuki lagi (409)")
    st, j = a2.minta("/api/pertandingan/buat", {"nama": "Meja Dua"})
    cek(st == 200 and j["pertandingan"]["id"] != t["id"], "pemain bisa membuat pertandingan baru sesudahnya")
    a3b = masuk("anggota3")
    st, j = a3b.minta("/api/pertandingan/gabung", {"id": j["pertandingan"]["id"], "gaya": "bertahan"})
    cek(st == 200, "pertandingan baru bisa dimasuki pemain lain")
    st, j = a3b.minta("/api/keluar", {})
    st, j = a2.minta("/api/ronde")
    cek(peserta_username(j) == ["anggota2"], "logout satu pemain tidak mengakhiri pertandingan selama masih ada yang lain")


# ------------------------------------------------------------------ 6. dua usulan serentak
def tes_serentak():
    a1, a2, a3 = masuk("anggota1"), masuk("anggota2"), masuk("anggota3")
    a2.minta("/api/pertandingan/keluar", {})      # anggota2 masih berada di "Meja Dua" dari tes sebelumnya
    st, j = a1.minta("/api/pertandingan/buat", {"nama": "Meja Serentak", "gaya": "menyerang"})
    pid = j["pertandingan"]["id"]
    a2.minta("/api/pertandingan/gabung", {"id": pid, "gaya": "seimbang"})
    a3.minta("/api/pertandingan/gabung", {"id": pid, "gaya": "bertahan"})
    a1.minta("/api/usul", {"langkah": "d2d4"})
    hasil = {}
    th = [threading.Thread(target=lambda k, u, m: hasil.__setitem__(u, k.minta("/api/usul", {"langkah": m})),
                           args=(k, u, m)) for k, u, m in ((a2, "anggota2", "d2d3"), (a3, "anggota3", "b2b4"))]
    [x.start() for x in th]
    [x.join() for x in th]
    siap = [j.get("penilaian_siap") for st, j in hasil.values()]
    st, j = a1.minta("/api/ronde")
    cek(sorted(siap) == [False, True] and j["kasus"]["nomor"] == 1 and len(j["penilaian"]["alternatif"]) == 3,
        "dua usulan serentak: penilaian individual dibuat tepat sekali")
    a1.minta("/api/konsensus", {})
    st, j = a1.minta("/api/ronde")
    cek(j["kasus"]["nomor"] == 2 and len(j["hasil_terakhir"]["alternatif"]) == 3, "konsensus Ketua membuka tepat satu ronde berikutnya")
    # dua pertandingan berjalan bersamaan tidak saling mengganggu
    b = Klien()
    b.minta("/api/login", {"username": "budi_99", "sandi": "rahasia1"})
    st, j = b.minta("/api/pertandingan/buat", {"nama": "Meja Lain"})
    st, j = b.minta("/api/ronde")
    cek(j["kasus"]["nomor"] == 1 and j["kasus"]["fen"] == AWAL and peserta_username(j) == ["budi_99"],
        "pertandingan kedua berjalan sendiri (ronde 1) sementara pertandingan pertama sudah ronde 2")


# ------------------------------------------------------------------ 7. pemain tidak aktif
def tes_tidak_aktif():
    tmp = Path(tempfile.mkdtemp())
    port = PORT + 3
    srv = nyalakan(tmp / "idle.db", port, {"SKAKMAT_TIMEOUT_AKTIF": "2"})
    try:
        a1, a2, a3 = masuk("anggota1", port), masuk("anggota2", port), masuk("anggota3", port)
        st, j = a1.minta("/api/pertandingan/buat", {"nama": "Meja Diam"})
        pid = j["pertandingan"]["id"]
        a2.minta("/api/pertandingan/gabung", {"id": pid})
        time.sleep(3.2)
        st, j = a1.minta("/api/ronde")      # anggota1 aktif; anggota2 diam > 2 detik
        cek(peserta_username(j) == ["anggota1"], "pemain yang diam melewati batas waktu dianggap keluar")
        cek(a2.minta("/api/ronde")[1]["pertandingan"] is None, "pemain itu kembali ke lobi saat berikutnya membuka halaman")
        time.sleep(3.2)
        st, j = a3.minta("/api/lobi")       # semua pemain diam -> pertandingan berakhir
        cek(j["daftar"] == [], "semua pemain diam: pertandingan berakhir otomatis")
        cek(a1.minta("/api/ronde")[1]["pertandingan"] is None, "pemain yang tadi diam tidak lagi berada di pertandingan")
    finally:
        srv.terminate()
        srv.wait(timeout=10)


# ------------------------------------------------------------------ 8. migrasi, skakmat, sandi lingkungan
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
    port = PORT + 2
    srv = nyalakan(db, port, tangkap=True)
    try:
        cadangan = list(tmp.glob("lama.db.lama-*"))
        k = Klien(port)
        st, j = k.minta("/api/login", {"username": "anggota1", "sandi": "anggota123-1"})
        cek(srv.poll() is None and st == 200, "basis data skema lama dimigrasi otomatis: server hidup, akun baru bisa masuk")
        with sqlite3.connect(cadangan[0]) as c:
            ada = c.execute("SELECT username FROM pengguna").fetchone()[0]
        cek(len(cadangan) == 1 and ada == "kapten", f"file lama dicadangkan utuh: {cadangan[0].name}")
    finally:
        srv.terminate()
        out = srv.communicate(timeout=10)[0]
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
        u = {r["username"]: dict(r) for r in c.execute("SELECT id, username, nama FROM pengguna")}
        pid, g = app.buat_pertandingan(c, u["anggota1"], "Uji skakmat", "menyerang")
        for nama, gaya in (("anggota2", "seimbang"), ("anggota3", "bertahan")):
            _, g = app.gabung_pertandingan(c, u[nama], pid, gaya)
            assert g is None, g
        # putih: Qh5xf7# tersedia (Scholar's mate)
        app.buat_ronde(c, pid, 1, 9, "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4",
                       ["e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6"])
        ids = [p["id"] for p in app.anggota_aktif(c, pid)]
        kasus = app.kasus_aktif(c, pid)
        for uid, m in zip(ids, ["h5f7", "h5f7", "d2d3"]):
            c.execute("INSERT INTO usulan VALUES(?,?,?,?,?)", (kasus["id"], uid, m, "-", time.time()))
        k, galat = app.jalankan_penilaian(c, kasus)
        cek(galat is None and k["pemenang"]["san"] == "Qxf7#" and k["akhir"] == "Skakmat. Tim menang." and k["lawan"] is None
            and app.kasus_aktif(c, pid)["id"] == kasus["id"], "langkah pemenang skakmat: permainan selesai, tanpa balasan lawan dan ronde baru")
        cek(k["kriteria"]["nilai"][0][1] == 5.0 and k["kriteria"]["nilai"][0][4] == 1.0, "langkah skakmat dinilai maksimal (C2 = 5, risiko C5 = 1)")
        # lawan yang memberi skakmat: ronde berikutnya langsung ditandai selesai
        app.buat_ronde(c, pid, 2, 1, "rnbqkbnr/pppp1ppp/8/4p3/8/5P2/PPPPP1PP/RNBQKBNR w KQkq - 0 2", ["f3", "e5"])
        kasus = app.kasus_aktif(c, pid)
        for uid in ids:
            c.execute("INSERT INTO usulan VALUES(?,?,?,?,?)", (kasus["id"], uid, "g2g4", "g4", time.time()))
        k, galat = app.jalankan_penilaian(c, kasus)
        baru = app.kasus_aktif(c, pid)
        cek(galat is None and len(k["alternatif"]) == 1 and k["alternatif"][0]["dukungan"] == 3 and k["lawan"]["san"] == "Qh4#"
            and baru["selesai"] == "Skakmat. Tim kalah." and app.mesin.langkah_sah(baru["fen"]) == [],
            "suara bulat (1 alternatif) tetap dinilai; lawan memberi skakmat -> ronde ditandai selesai")


def sandi_dari_lingkungan():
    """Server yang dibuka lewat internet memakai kata sandi acak dari SKAKMAT_SANDI_<USERNAME>."""
    tmp = Path(tempfile.mkdtemp())
    db = tmp / "sandi.db"
    for ulang, sandi in enumerate(("RahasiaBaru-1", "RahasiaLagi-2")):   # kedua: basis data sudah ada
        srv = nyalakan(db, env_tambahan={"SKAKMAT_SANDI_ANGGOTA1": sandi})
        try:
            k = Klien()
            st_lama, _ = k.minta("/api/login", {"username": "anggota1", "sandi": "anggota123-1"})
            st_baru, _ = k.minta("/api/login", {"username": "anggota1", "sandi": sandi})
            st_lain, _ = Klien().minta("/api/login", {"username": "anggota2", "sandi": "anggota123-2"})
            cek(st_lama == 401 and st_baru == 200 and st_lain == 200,
                f"kata sandi dari lingkungan (start ke-{ulang + 1}): sandi bawaan ditolak, sandi baru diterima, akun lain tetap bawaan")
        finally:
            srv.terminate()
            srv.wait(timeout=10)


def main():
    try:
        import chess  # noqa: F401
    except ImportError:
        raise SystemExit("Tes ini butuh python-chess. Jalankan dengan: .venv/bin/python test_e2e.py")
    tmp = Path(tempfile.mkdtemp())
    srv = nyalakan(tmp / "uji.db")
    try:
        tes_akun()
        t, K = tes_lobi()
        tes_ronde(t, K)
        tes_keanggotaan(t, K)
        tes_berakhir(t, K)
        tes_serentak()
    finally:
        srv.terminate()
        srv.wait(timeout=10)
    tes_tidak_aktif()
    migrasi()
    akhir_permainan()
    sandi_dari_lingkungan()
    print("SEMUA TES UJUNG KE UJUNG LOLOS")


if __name__ == "__main__":
    main()
