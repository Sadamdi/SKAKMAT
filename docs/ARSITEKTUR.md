# Arsitektur SKAKMAT

Dokumen ini menjelaskan susunan aplikasi, alasan pilihan teknologinya, dan cara menjalankannya
di laptop (lokal) maupun di server.

## 1. Gambaran umum

```
 Browser anggota (3 perangkat)
        │  HTTP(S): halaman statis + JSON API, cookie sesi HttpOnly
        ▼
 [Reverse proxy HTTPS]  ← hanya di server (Caddy/Nginx), opsional di lokal
        │
        ▼
 Uvicorn  ──  FastAPI (app.py)
        │        ├─ rute /api/*      login, ronde, usul, konsensus, ulang, keluar
        │        ├─ rute /*          berkas statis dari static/
        │        └─ middleware       header keamanan, pemeriksaan Origin
        │
        ├─ gdss.py   TOPSIS per gaya main + voting Borda (Python murni)
        ├─ mesin.py  legalitas langkah, ukur C1–C5, balasan lawan (python-chess + Stockfish)
        └─ SQLite    skakmat.db: pengguna, sesi, ronde, usulan, konsensus (jejak audit)
```

Satu proses server menyajikan front end sekaligus API, jadi tidak ada masalah CORS dan cukup satu
alamat untuk dibuka.

## 2. Pilihan teknologi

| Lapisan | Pilihan | Alasan |
|---|---|---|
| Backend | **Python 3 + FastAPI + Uvicorn** | Algoritma (TOPSIS, Borda) dan analisis catur (python-chess, Stockfish) sudah Python, jadi satu bahasa di seluruh server. FastAPI memberi routing, middleware, dan penanganan konkurensi yang matang; Uvicorn adalah server ASGI standarnya. Sebelumnya server ditulis dengan `http.server` bawaan — cukup untuk demo, tetapi tidak layak diletakkan di server. |
| Basis data | **SQLite** | Tiga pengguna dan satu permainan aktif; tidak butuh server basis data. File tunggal, mudah dicadangkan. Sesi login juga disimpan di sini, jadi restart server tidak mengeluarkan semua orang. |
| Front end | **HTML + CSS + JavaScript biasa**, disajikan dari `static/` | Sudah dikerjakan dan diuji (papan interaktif, aksesibilitas, mode gelap). Tanpa langkah build dan tanpa Node.js di server. Memindahkannya ke React/Vue menambah toolchain tanpa fungsi baru; kontraknya hanya API JSON, jadi bisa diganti kapan saja (lihat bagian 7). |
| Engine catur | **Stockfish** (opsional) + **python-chess** (wajib untuk bermain) | Engine hanya mengukur dan membalas sebagai lawan; tidak ikut memilih keputusan kelompok. |
| Pengemasan | **Docker** (opsional) | Satu image berisi Python, paket, dan Stockfish, sehingga jalan sama di laptop mana pun dan di server. |

## 3. Struktur berkas

```
app.py            FastAPI: rute, sesi, basis data, alur ronde
gdss.py           TOPSIS, profil gaya main, Borda
mesin.py          python-chess dan Stockfish
static/           index.html, style.css, app.js, favicon.svg
requirements.txt  chess, fastapi, uvicorn
Dockerfile, docker-compose.yml, .env.example
docs/             dokumen ini
test_*.py         tes algoritma, mesin, dan ujung ke ujung
```

## 4. Alur data satu ronde

1. Anggota login → server membuat sesi (tabel `sesi`) dan mengirim cookie `sesi` (HttpOnly,
   SameSite=Strict).
2. Browser memanggil `GET /api/ronde` tiap beberapa detik untuk status ronde.
3. Anggota menggerakkan bidak → `POST /api/usul`; server memeriksa legalitas (python-chess).
4. Saat usulan ketiga masuk, server menjalankan penilaian di dalam kunci ronde: ukur C1–C5 →
   TOPSIS tiga kali (satu per gaya main) → Borda → mainkan langkah pemenang → balasan lawan →
   buka ronde berikutnya. Semuanya disimpan di tabel `konsensus` sebagai jejak audit.
5. Semua akun melihat hasil yang sama lewat `GET /api/ronde`.

## 5. Menjalankan secara lokal

Tanpa Docker:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip ...
.venv/bin/python app.py                          # http://127.0.0.1:8000
```

Stockfish dipasang terpisah (lihat README) dan dicari di `PATH`, atau tunjuk dengan
`SKAKMAT_STOCKFISH=/lokasi/stockfish`. Agar bisa dibuka dari perangkat lain di jaringan yang sama:
`python app.py --host 0.0.0.0`.

Dengan Docker (Stockfish sudah termasuk):

```bash
docker compose up --build        # http://127.0.0.1:8000
```

## 6. Menjalankan di server

Contoh: VPS Linux dengan domain.

```bash
git clone https://github.com/Sadamdi/SKAKMAT && cd SKAKMAT
docker compose up -d --build     # aplikasi mendengarkan di 127.0.0.1:8000
```

Hadapkan ke internet lewat reverse proxy dengan HTTPS. Contoh Caddy (sertifikat otomatis):

```
skakmat.contoh.id {
    reverse_proxy 127.0.0.1:8000
}
```

Lalu set `SKAKMAT_COOKIE_SECURE=1` (di `.env` di samping `docker-compose.yml`) dan jalankan ulang
`docker compose up -d`. Reverse proxy harus meneruskan header `Host` asli (default Caddy dan Nginx
`proxy_set_header Host $host;`) karena pemeriksaan Origin membandingkannya.

Tanpa Docker, jalankan sebagai service systemd:

```ini
[Service]
WorkingDirectory=/opt/skakmat
Environment=SKAKMAT_DB=/var/lib/skakmat/skakmat.db SKAKMAT_COOKIE_SECURE=1
ExecStart=/opt/skakmat/.venv/bin/python app.py --port 8000
Restart=on-failure
User=skakmat
```

**Cadangan:** salin file SQLite (`/data/skakmat.db` di Docker, volume `skakmat-data`).

### Variabel lingkungan

| Variabel | Default | Fungsi |
|---|---|---|
| `SKAKMAT_HOST` / `SKAKMAT_PORT` | `127.0.0.1` / `8000` | alamat dan port |
| `SKAKMAT_DB` | `skakmat.db` | lokasi file SQLite |
| `SKAKMAT_STOCKFISH` | cari di `PATH` | path engine; `mati` = tanpa engine |
| `SKAKMAT_COOKIE_SECURE` | `0` | `1` bila memakai HTTPS |
| `SKAKMAT_PROXY_IPS` | `127.0.0.1` | proxy yang dipercaya untuk `X-Forwarded-For` |
| `SKAKMAT_DOCS` | `0` | `1` membuka dokumentasi API di `/api/docs` |

## 7. Batasan dan arah pengembangan

- **Satu proses server.** Kunci ronde dan batas percobaan login ada di memori proses, jadi jangan
  menjalankan beberapa worker Uvicorn. Untuk tiga pengguna ini lebih dari cukup. Untuk skala
  lebih besar, pindahkan kunci dan batas login ke basis data atau Redis, dan ganti SQLite dengan
  PostgreSQL.
- **Penilaian berjalan di dalam permintaan** usulan ketiga (sekitar 0,1 detik tanpa engine, sampai
  beberapa detik dengan Stockfish). Bila perlu, pindahkan ke antrean tugas.
- **Front end ke framework:** karena seluruh komunikasi lewat JSON (`/api/*`), `static/` bisa diganti
  aplikasi React/Vue/Svelte yang di-build ke folder yang sama (atau disajikan terpisah dengan
  CORS dibuka secara eksplisit) tanpa mengubah backend.
- **Akun** didefinisikan di daftar `AKUN` pada `app.py` (demo). Ganti kata sandi sebelum dipakai
  di server publik.
