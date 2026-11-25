# ♟️ SKAKMAT: Catur Konsultasi GDSS

<div align="center">

**Sistem Kolaborasi Analis untuk Keputusan Melangkah Antar Tim**
*Project Akhir Praktikum Sistem Informasi, Kelompok 2, Kelas B, UIN Maulana Malik Ibrahim Malang*

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Stockfish](https://img.shields.io/badge/Stockfish-19-555555?style=for-the-badge)](https://stockfishchess.org/)

</div>

---

## 📖 Tentang Project

SKAKMAT adalah **Group Decision Support System (GDSS)** berbentuk game catur. Beberapa orang (maksimal 3 per
pertandingan) bermain catur **bersama melawan komputer**. Saat giliran tim, tiap orang mengusulkan satu langkah.
Sistem menilai tiap usulan dengan **TOPSIS** menurut gaya main masing-masing, lalu **Ketua** (akun berjabatan
tertinggi) menjalankan **voting Borda** untuk memutuskan satu langkah kelompok. Saat giliran lawan, komputer
membalas dengan catur biasa (Stockfish).

Pengguna **mendaftar atau masuk**, lalu **membuat pertandingan** atau **bergabung**. Boleh keluar dan bergabung
kapan saja; bila semua pemain keluar (atau diam 2 menit), pertandingan **berakhir otomatis**.

---

## ✨ Fitur Unggulan

| Fitur | Keterangan |
|---|---|
| 👤 Akun per pengguna | Daftar dan masuk, kata sandi PBKDF2, sesi cookie HttpOnly |
| 🏠 Lobi dan pertandingan | Buat, gabung dengan kode, keluar; banyak pertandingan sekaligus |
| 👑 Jabatan Ketua | Pembuat pertandingan; hanya Ketua yang boleh menjalankan konsensus (dicek di server, HTTP 403 untuk lainnya) |
| 🎭 Gaya main | Menyerang, Seimbang, Bertahan: bobot TOPSIS berbeda per anggota |
| 📐 Penilaian individual | Mesin mengukur C1 sampai C5, TOPSIS per anggota, terlihat semua orang |
| 🗳️ Konsensus Borda | Penggabungan peringkat anggota menjadi satu keputusan, dengan aturan seri jelas |
| 🤖 Lawan Stockfish | Giliran lawan memakai catur biasa, bukan TOPSIS |
| 🔄 Keanggotaan dinamis | Keluar dan bergabung di tengah ronde, Ketua berpindah otomatis |
| ♿ Aksesibilitas | Papan bisa dioperasikan penuh dengan keyboard, kontras WCAG AA, mode gelap |
| 🌐 Main bareng online | Satu perintah menghasilkan alamat Cloudflare gratis sementara |

---

## 🧠 Cara Kerja Singkat

```
 usulan tiap anggota
        │  (usulan sama digabung, dukungan dicatat)
        ▼
 mesin mengukur C1..C5 tiap usulan  ──►  matriks keputusan (sama untuk semua anggota)
        ▼
 TOPSIS sekali per anggota, bobot = gaya mainnya  ──►  penilaian individual (V dan peringkat)
        ▼
 Ketua menekan konsensus  ──►  voting Borda  ──►  satu pemenang
        ▼
 langkah pemenang dimainkan  ──►  Stockfish membalas  ──►  ronde berikutnya
```

| Kriteria | Arti | Jenis |
|---|---|---|
| C1 | Keamanan raja | benefit |
| C2 | Keamanan material | benefit |
| C3 | Penguasaan pusat papan | benefit |
| C4 | Peluang serangan | benefit |
| C5 | Risiko serangan balik lawan | cost |

Contoh ronde 1: d4 mendapat poin Borda 4,3194, d3 3,7491, O-O 1,0693, sehingga d4 menang walau satu anggota
memilih d3. Rumus lengkap, contoh hitungan, dan aturan seri ada di [docs/ALGORITMA.md](docs/ALGORITMA.md).

---

## 📚 Dokumentasi

| Dokumen | Isi |
|---|---|
| [docs/TUTORIAL_LENGKAP.md](docs/TUTORIAL_LENGKAP.md) | **Mulai di sini.** Tutorial lengkap dengan screenshot, plus hitungan TOPSIS dan Borda langkah demi langkah |
| [docs/PANDUAN_PENGGUNA.md](docs/PANDUAN_PENGGUNA.md) | Tutorial memakai aplikasi dari nol, masalah umum |
| [docs/ALGORITMA.md](docs/ALGORITMA.md) | Seluruh algoritma: pengukuran C1–C5, TOPSIS, Borda, aturan seri, aturan anggota |
| [docs/CARA_KERJA.md](docs/CARA_KERJA.md) | Contoh hitungan nyata satu ronde dan bukti pengujiannya |
| [docs/PENJELASAN_KODE.md](docs/PENJELASAN_KODE.md) | Penjelasan per berkas dan fungsi |
| [docs/ARSITEKTUR.md](docs/ARSITEKTUR.md) | Arsitektur, alasan pilihan teknologi, model data, deploy |

---

## 🛠️ Teknologi

| Lapisan | Pilihan |
|---|---|
| Backend | Python 3, FastAPI, Uvicorn |
| Basis data | SQLite (file `skakmat.db`) |
| Frontend | HTML, CSS, JavaScript biasa (tanpa framework dan tanpa build) |
| Catur | python-chess (wajib), Stockfish 19 (opsional, disarankan) |
| Deploy | Docker / docker compose, Cloudflare Quick Tunnel untuk alamat sementara |

---

## 👥 Tim

| Nama | Peran |
|---|---|
| Sulthan Adam Rahmadi | Backend, algoritma TOPSIS dan Borda, pengujian, dokumentasi |
| mug31 | Frontend |

---

## Arsitektur

Backend **FastAPI + Uvicorn** (Python), front end HTML/CSS/JS biasa dari `static/`, basis data SQLite, Stockfish
opsional. Bisa dijalankan lokal maupun di server (Docker). Penjelasan lengkap, alasan pilihan, dan
panduan deploy ada di [docs/ARSITEKTUR.md](docs/ARSITEKTUR.md).

Cara tercepat dengan Docker (Stockfish sudah termasuk): `docker compose up --build`, lalu buka
http://127.0.0.1:8000.

## Jalankan cepat di Windows (lokal)

Buka PowerShell, masuk ke folder proyek, pasang paket, lalu jalankan:

```powershell
cd "D:\adam kuliah\Semester 5\Information System Praktikum\UAS\SKAKMAT"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app.py
```

Buka http://127.0.0.1:8000 di browser. Berhenti dengan Ctrl+C. Pemasangan paket cukup sekali; lain kali
cukup `cd` lalu perintah terakhir. Tanpa Stockfish aplikasi tetap jalan (lihat tabel di bawah).

Untuk mencoba alur tiga akun di satu laptop, buka tiga jendela browser berbeda (atau satu jendela
biasa dan dua jendela penyamaran) supaya cookie sesinya tidak bertabrakan, lalu masuk sebagai
`anggota1` (Ketua), `anggota2`, dan `anggota3`. Setelah ketiganya mengusulkan langkah, hanya akun
`anggota1` yang punya tombol **Jalankan konsensus (voting Borda)**.

Menjalankan tes:

```powershell
.venv\Scripts\python test_gdss.py
.venv\Scripts\python test_mesin.py
.venv\Scripts\python test_e2e.py
```

## Main bareng dari perangkat lain (alamat internet sementara)

Satu orang (pemilik laptop) menyalakan server; **teman tidak perlu memasang atau menjalankan apa pun**,
cukup membuka alamat di browser mereka, di perangkat dan jaringan mana pun (tidak harus satu Wi-Fi).

```powershell
winget install --id Cloudflare.cloudflared      # sekali saja
cd "D:\adam kuliah\Semester 5\Information System Praktikum\UAS\SKAKMAT"
powershell -ExecutionPolicy Bypass -File .\jalankan_online.ps1
```

Skrip menyalakan server, membuka terowongan gratis Cloudflare (Quick Tunnel), lalu mencetak satu alamat
`https://....trycloudflare.com` dan kata sandi acak untuk tiga akun. Bagikan alamat itu; tiap orang masuk
dengan akunnya sendiri (boleh beda browser). Alamat dan kata sandi berubah setiap skrip dijalankan, dan semuanya
mati begitu skrip dihentikan (Ctrl+C). Laptop pemilik harus tetap menyala dan terhubung ke internet.

Variabel `SKAKMAT_SANDI_ANGGOTA1` (dan `..2`, `..3`) mengganti kata sandi bawaan; skrip di atas mengisinya otomatis.

## Cara menjalankan

Kebutuhan:

| Komponen | Wajib? | Untuk apa |
|---|---|---|
| Python 3.9 atau lebih baru | wajib | server, TOPSIS, Borda |
| `fastapi`, `uvicorn` | wajib | server web (terpasang lewat `requirements.txt`) |
| `chess` (python-chess) 1.11.2 | wajib untuk bermain | memeriksa legalitas langkah yang diusulkan dan memainkannya |
| Program Stockfish | disarankan | mengukur C1–C5, memainkan balasan lawan, dan pembanding |

Tanpa python-chess, papan hanya bisa dilihat (usulan ditolak dengan pesan jelas). Tanpa Stockfish,
C2 diukur secara statis dan lawan memakai aturan sederhana; keduanya ditandai di tampilan.

### 1. Paket Python

```bash
cd SKAKMAT                                # masuk ke folder hasil clone repo ini
python -m venv .venv                      # di Linux/macOS mungkin perlu: python3 -m venv .venv
.venv/bin/pip install -r requirements.txt # Windows: .venv\Scripts\pip install -r requirements.txt
```

### 2. Stockfish (Linux)

Stockfish tidak ada di repo resmi Arch. Paket PyPI bernama `stockfish` **bukan** engine-nya (hanya
pembungkus Python), jadi jangan dipasang untuk ini. Cara yang dipakai saat pengembangan: unduh
binary resmi dari rilis GitHub Stockfish, lalu pasang tanpa root ke `~/.local/bin`:

```bash
mkdir -p /tmp/sf && cd /tmp/sf
curl -LO https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-linux-x86-64-universal.tar.gz
sha256sum stockfish-linux-x86-64-universal.tar.gz
# harus: 9defc0d4e55d49c65a6d042f3e571a39fcea499ade6dbe741b53b8c65e03611f
tar xzf stockfish-linux-x86-64-universal.tar.gz
install -D -m 755 stockfish/stockfish-linux-x86-64-universal ~/.local/bin/stockfish
stockfish quit        # cek: harus mencetak "Stockfish 19 by the Stockfish developers"
```

Pastikan `~/.local/bin` ada di `PATH`. Alternatif: Debian/Ubuntu `sudo apt install stockfish`,
Arch lewat AUR `yay -S stockfish`. Di Windows/macOS unduh dari https://stockfishchess.org/download/.
Bila programnya tidak ada di `PATH`, tunjuk lokasinya dengan variabel lingkungan:

```bash
SKAKMAT_STOCKFISH=/lokasi/stockfish .venv/bin/python app.py
SKAKMAT_STOCKFISH=mati .venv/bin/python app.py      # sengaja tanpa engine
```

### 3. Jalankan

```bash
.venv/bin/python app.py     # Windows: .venv\Scripts\python app.py
```

Buka http://127.0.0.1:8000 di browser. Berhenti dengan Ctrl+C.

Supaya anggota kelompok lain bisa membuka dari laptop atau HP di jaringan yang sama:

```bash
.venv/bin/python app.py --host 0.0.0.0 --port 8000
```

lalu buka `http://<alamat-IP-laptop>:8000`. Tiap anggota memakai perangkatnya sendiri dan masuk
dengan akunnya sendiri.

Basis data SQLite `skakmat.db` dibuat otomatis saat pertama dijalankan. Bila file lama dari alur
sebelumnya (skema 1: Kapten dan penilaian manual) masih ada, file itu **dicadangkan** ke
`skakmat.db.lama-<tanggal>-<jam>` lalu diganti skema baru — aplikasi tidak mati karena basis data
lama. Hapus `skakmat.db` untuk mengulang dari awal.

## Akun dan pertandingan

Akun baru dibuat lewat **Daftar akun baru** di halaman masuk (nama pengguna 3 sampai 20 karakter huruf kecil,
angka, atau garis bawah; kata sandi minimal 6 karakter). Tiga akun demo dibuat otomatis agar mudah dicoba:

| Akun demo | Kata sandi |
|---|---|
| anggota1 | anggota123-1 |
| anggota2 | anggota123-2 |
| anggota3 | anggota123-3 |

Jabatan dan gaya main **bukan** melekat pada akun, tetapi pada pertandingan:

| Peran di pertandingan | Cara mendapatkannya |
|---|---|
| **Ketua** (jabatan tertinggi) | Pembuat pertandingan. Bila Ketua keluar, anggota yang bergabung paling awal naik menjadi Ketua. Hanya Ketua yang boleh menjalankan konsensus. |
| Gaya main | Dipilih saat membuat atau bergabung; unik per pertandingan. Menyerang: bobot C1 sampai C5 = 20/15/20/30/15; Seimbang = 25/20/20/20/15; Bertahan = 30/30/15/10/15. |

Kata sandi demo dapat diganti dengan variabel `SKAKMAT_SANDI_ANGGOTA1` (dan `..2`, `..3`).

## Alur penggunaan

1. **Daftar atau masuk.** Setelah masuk, pemain berada di **lobi**: daftar pertandingan yang sedang berlangsung
   (anggota, gaya yang masih tersedia, kode 5 karakter), form **Buat pertandingan**, dan **Gabung dengan kode**.
2. **Buat atau gabung.** Pembuat menjadi Ketua. Satu pemain hanya boleh berada di satu pertandingan; pertandingan
   penuh (3 pemain) tidak bisa dimasuki. Pemain baru boleh bergabung kapan saja, termasuk di tengah ronde.
3. **Usulkan langkah dengan menggerakkan bidak.** Klik bidak putih (petak tujuan yang sah ditandai), lalu klik
   tujuan. Bisa juga diseret. Dengan keyboard: Tab ke bidak, Enter, Tab ke petak tujuan, Enter, Esc untuk batal.
   Usulan masih bisa diganti sampai anggota terakhir mengusulkan, dan usulan anggota lain belum terlihat.
4. **Penilaian individual muncul otomatis** begitu semua anggota yang ada sudah mengusulkan: nilai C1 sampai C5
   dan satu tabel TOPSIS per anggota. Usulan dikunci pada tahap ini.
5. **Ketua menekan "Jalankan konsensus (voting Borda)".** Akun lain melihat "menunggu Ketua" (server menolak
   mereka dengan 403). Semua akun lalu melihat tabel Borda dan pembanding engine.
6. **Lawan membalas** dengan catur biasa (Stockfish), dan ronde berikutnya dibuka.
7. **Keluar.** Tombol *Keluar dari pertandingan* (kembali ke lobi), atau *Keluar* akun. Pemain yang tidak mengirim
   permintaan apa pun selama 2 menit juga dianggap keluar. Anggota yang keluar tidak ditunggu lagi; bila ia
   Ketua, jabatan berpindah. Bila tidak ada pemain tersisa, pertandingan berakhir.

Satu-satunya input permainan adalah gerakan bidak (selain login, pendaftaran, dan menu lobi).

## Metode

### Kriteria C1–C5, diukur mesin

Nilai dihitung **dari posisi setelah langkah dijalankan**, skalanya 1–5, dan deterministik: posisi
yang sama selalu menghasilkan angka yang sama (Stockfish 1 thread, hash dibersihkan).

| Kode | Kriteria | Jenis | Cara mengukur |
|---|---|---|---|
| C1 | Keamanan raja | benefit | pion pelindung di depan raja dikurangi jumlah serangan lawan ke petak sekitar raja |
| C2 | Keamanan material | benefit | perubahan selisih material setelah variasi utama Stockfish dimainkan, termasuk pertukaran yang belum selesai; tanpa engine: selisih material dikurangi ancaman tangkapan terbesar lawan |
| C3 | Penguasaan pusat papan | benefit | serangan dan bidak tim di d4, e4, d5, e5 dikurangi milik lawan |
| C4 | Peluang serangan | benefit | bidak lawan yang diserang, jumlah skak, dan mobilitas tim |
| C5 | Risiko serangan balik lawan | cost | tangkapan menguntungkan dan langkah skak yang tersedia bagi lawan |

Skala dipetakan dengan `tanh` supaya tidak didominasi satu kriteria, lalu dinormalisasi lagi oleh
TOPSIS. Mesin **hanya mengukur**; ia tidak memilih langkah dan bukan kriteria ke-6.

### Kenapa TOPSIS dijalankan tiga kali

Nilai C1–C5 sama untuk semua anggota (dihitung mesin dari papan). Kalau bobotnya juga sama, ketiga
ranking akan identik dan Borda hanya mengulang hasil TOPSIS tanpa menambah informasi apa pun. Karena
itu tiap anggota punya **gaya main** dengan bobot berbeda, persis premis laporan: *"setiap anggota
memiliki penilaian dan prioritas yang berbeda: ada yang condong menyerang, ada pula yang memilih
bertahan."*

Alurnya:

1. Ketiga usulan menjadi **alternatif** (usulan yang sama digabung jadi satu alternatif, dukungan
   dicatat).
2. C1–C5 diukur mesin untuk tiap alternatif → satu matriks keputusan bersama.
3. **TOPSIS tiga kali**, sekali per gaya → tiga peringkat yang bisa berbeda.
4. **Borda** menggabungkan ketiga peringkat → satu keputusan kelompok.

Dengan begitu TOPSIS punya kerja nyata (memeringkat dari sudut pandang tertentu) dan Borda punya
kerja nyata (menggabungkan sudut pandang yang saling berbeda), sementara pengguna tetap nol input.

**TOPSIS:** normalisasi vektor per kriteria, dikali bobot gaya, solusi ideal positif dan negatif
(benefit dan cost dibedakan), jarak D+ dan D−, skor preferensi V = D− / (D+ + D−), lalu peringkat.

**Borda:** untuk n alternatif, bobot peringkat 1..n adalah n, n−1, ..., 1. Poin alternatif =
jumlah (bobot Borda dari peringkatnya × skor preferensi V) dari ketiga anggota. Nilai Borda =
poin / total poin. Nilai tertinggi menjadi keputusan kelompok. Aturan seri: **dukungan usulan**, lalu **jumlah peringkat TOPSIS**, lalu **urutan usulan**.

Bukti Borda benar-benar mengubah hasil ada di `test_gdss.py`: pada matriks contoh, TOPSIS gaya
seimbang memilih alternatif 0 sementara Borda memilih alternatif 2. Dari 4997 matriks acak,
peringkat tiga profil tidak seragam pada 3083 kasus dan pemenang Borda berbeda dari pemenang TOPSIS
tunggal pada 49 kasus. Pada percobaan nyata di browser, dua anggota memilih satu langkah dan
anggota ketiga memilih langkah lain — Borda memutuskan pemenangnya dan UI menjelaskan siapa yang
setuju dan siapa yang tidak.

### Peran engine: mengukur, bukan memilih

Stockfish **tidak** ikut menentukan keputusan. Nilainya tidak masuk TOPSIS maupun Borda, dan tidak
menjadi kriteria ke-6. Engine dipakai untuk:

1. **Mengukur C1–C5** (C2 memakai variasi utamanya; C1, C3, C4, C5 dari python-chess dengan bantuan
   analisis engine bila tersedia).
2. **Memeriksa legalitas** langkah usulan (cukup python-chess).
3. **Memainkan balasan lawan** (kedalaman 10) supaya ronde berikutnya bisa mulai otomatis.
4. **Pembanding**, setelah konsensus: peringkat kelompok disandingkan dengan peringkat engine, dengan
   penanda sepakat/berbeda dan catatan bila selisihnya praktis setara. Angka ini ditahan sampai
   konsensus selesai supaya anggota tidak terpengaruh.

Batas engine: kedalaman 12 dan sekitar 0,02–1,5 detik per analisis untuk kriteria, kedalaman 10
untuk balasan lawan, satu analisis sekaligus, hasil disimpan di memori (cache). Bila engine tidak
ada, macet, atau gagal, server tetap berjalan dan menandai mode yang dipakai.

Hasil mencerminkan kesepakatan kelompok, bukan jaminan langkah terbaik atau kemenangan.

## Tampilan (front end)

Front end ada di `static/` dan hanya memakai HTML, CSS, dan JavaScript biasa (tanpa framework, tanpa
build step).

- **Papan adalah elemen utama:** 640px pada layar 1440px, memenuhi lebar di HP (326px pada 360px)
  dan tablet (694px pada 768px), selalu persegi. Klik bidak → petak tujuan sah ditandai → klik
  tujuan → usulan terkirim. Drag-and-drop tersedia; klik-klik tetap jalan.
- **Hanya bidak tim sendiri** yang bisa digerakkan. Langkah ilegal ditolak `mesin.py` dan bidak
  kembali ke tempatnya dengan pesan singkat di bawah papan.
- **Identitas tiap akun:** warna aksen dan inisial (A1/A2/A3) yang sama di status tim, usulan,
  penanda petak tujuan di papan, tabel TOPSIS, dan animasi. Tag gaya main (Menyerang/Seimbang/
  Bertahan) ikut ditampilkan.
- **Usulan serentak:** petak tujuan usulan tiap anggota ditandai inisial mereka di papan, dan usulan
  yang sama digabung dengan keterangan dukungan ("usulan ganda: 3 orang").
- **Hasil penilaian** berisi empat bagian berurutan: (1) daftar usulan anggota, (2) nilai C1–C5 dari
  mesin, (3) tiga tabel TOPSIS per gaya dengan bobotnya masing-masing, (4) tabel Borda + animasi
  penggabungan + kalimat penjelas siapa memilih apa dan apa keputusan Borda.
- **Animasi Borda:** batang bertumpuk menunjukkan poin tiap anggota (bobot peringkat × V)
  ditambahkan satu per satu, lalu pemenang ditandai (bisa diputar ulang). Hasil akhir dan tabel
  sudah tampil sebelum animasi selesai, dan `prefers-reduced-motion` dihormati (langsung posisi
  akhir, tanpa animasi).
- **Ronde otomatis:** setelah penilaian, papan menganimasikan usulan → langkah pemenang → balasan
  lawan, lalu ronde baru siap. Ada tombol **Ronde baru** untuk mulai ulang manual.
- **Penyegaran otomatis** tiap 4 detik, satu permintaan sekali jalan, berhenti saat tab tidak aktif.
  Ada keterangan waktu pembaruan terakhir dan tombol **Segarkan** manual.
- **Status memuat**, **sesi habis** (kembali ke halaman masuk), dan **tombol nonaktif** selama
  permintaan berjalan (mencegah kirim ganda).
- **Aksesibilitas:** papan bisa dioperasikan penuh dengan keyboard, label petak menyebut koordinat
  dan nama bidak, `aria-pressed` menandai bidak terpilih, `Esc` membatalkan pilihan; tabel punya
  `caption`/`scope`; pesan memakai `role="status"` atau `role="alert"`; kontras warna memenuhi
  WCAG AA di mode terang dan gelap (kontras bidak putih pada petak gelap 4,70:1; hitam pada petak
  terang 13,91:1).
- **Tanpa skrip/style inline** (CSP `default-src 'self'`), semua teks dari server masuk lewat
  `textContent`.

## Struktur berkas

```
SKAKMAT/
├── app.py            FastAPI: API, basis data, sesi, alur ronde
├── Dockerfile, docker-compose.yml, .env.example   pengemasan dan konfigurasi server
├── docs/             ARSITEKTUR, ALGORITMA, CARA_KERJA, PENJELASAN_KODE, PANDUAN_PENGGUNA
├── gdss.py           TOPSIS, profil gaya main, voting Borda
├── mesin.py          legalitas langkah, ukur C1-C5, balasan lawan, pembanding engine (python-chess + Stockfish)
├── static/           index.html, style.css, app.js, favicon.svg
├── requirements.txt  paket Python (chess, fastapi, uvicorn)
├── test_gdss.py      tes TOPSIS tiga profil dan Borda (dibandingkan NumPy bila terpasang)
├── test_e2e.py       tes ujung ke ujung (login, usulan, penilaian otomatis, ronde, migrasi)
├── test_mesin.py     tes legalitas, C1-C5 deterministik, engine: hidup, mati, menggantung, tanpa python-chess
└── README.md
```

Tes:

```bash
.venv/bin/python test_gdss.py
.venv/bin/python test_e2e.py
.venv/bin/python test_mesin.py   # skenario yang butuh python-chess/Stockfish dilewati bila belum ada
```

## API

| Metode | Path | Keterangan |
|---|---|---|
| POST | `/api/daftar` | `{"username", "nama", "sandi"}` → akun baru, langsung masuk (400 bila tidak valid, 409 bila nama pengguna terpakai) |
| POST | `/api/login` | `{"username", "sandi"}` → set cookie sesi |
| POST | `/api/keluar` | keluar akun; pemain otomatis keluar dari pertandingannya |
| GET | `/api/me` | pengguna yang sedang masuk |
| GET | `/api/lobi` | pertandingan yang berlangsung (anggota, gaya tersedia, penuh atau tidak) dan pertandingan milik pemain |
| POST | `/api/pertandingan/buat` | `{"nama", "gaya"}` → pembuat menjadi Ketua |
| POST | `/api/pertandingan/gabung` | `{"id" atau "kode", "gaya"}` → 409 bila penuh, sudah berakhir, gaya terpakai, atau pemain masih di pertandingan lain |
| POST | `/api/pertandingan/keluar` | keluar dari pertandingan; mengakhirinya bila pemain terakhir |
| GET | `/api/ronde` | keadaan ronde pertandingan pemain (`pertandingan: null` bila di lobi): kasus, peserta + status usulan, usulan sendiri, langkah sah, penilaian individual, hasil terakhir. Tidak pernah memanggil engine. |
| POST | `/api/usul` | `{"langkah": "e2e4"}` → usulan satu langkah, tervalidasi legalitasnya. Bila ini usulan terakhir, respons berisi `penilaian_siap: true`. |
| POST | `/api/konsensus` | **hanya Ketua pertandingan (403 untuk lainnya)**: voting Borda atas penilaian individual, lalu langkah pemenang dimainkan dan lawan membalas. 409 bila belum lengkap atau sudah dikonsensuskan. |
| POST | `/api/ulang` | permainan baru dari posisi awal di pertandingan yang sama; riwayat lama tersimpan |

Endpoint alur lama (`/api/nilai`, `/api/kasus`, `/api/kasus-baru`, `/api/usul-kandidat`) menjawab **410 Gone**.

Semua endpoint: pemeriksaan asal permintaan (Origin), cek sesi, validasi tipe masukan, dan kueri
berparameter.

## Keamanan singkat

Kata sandi disimpan sebagai hash PBKDF2 dengan garam. Sesi memakai cookie HttpOnly dan
SameSite=Strict, berlaku 8 jam. Login dibatasi setelah lima kali gagal. Permintaan POST dengan
Origin asing ditolak. Hanya Ketua yang boleh menjalankan konsensus (dicek di server, bukan hanya disembunyikan di tampilan). Semua kueri SQL
berparameter, teks dari server dimasukkan ke halaman lewat `textContent`, dan Content-Security-Policy
melarang skrip inline. Aplikasi ini untuk demo kelompok di jaringan lokal, bukan untuk dipasang di
internet publik tanpa HTTPS.
