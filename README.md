# SKAKMAT: GDSS Pemilihan Langkah Catur

Sistem Kolaborasi Analis untuk Keputusan Melangkah Antar Tim. Project akhir Praktikum Sistem Informasi,
Kelompok 2, Kelas B.

Website GDSS dengan empat decision maker (Kapten, Analis 1, Analis 2, Analis 3). Setiap akun menilai
tiga kandidat langkah catur secara individual (TOPSIS). Setelah keempatnya selesai, akun Kapten
(jabatan tertinggi) menjalankan konsensus dengan voting Borda. Semua akun dapat melihat hasilnya.

## Cara menjalankan

Kebutuhan:

| Komponen | Wajib? | Untuk apa |
|---|---|---|
| Python 3.9 atau lebih baru | wajib | server, TOPSIS, Borda |
| `chess` (python-chess) 1.11.2 | disarankan | memeriksa legalitas posisi FEN dan kandidat langkah |
| Program Stockfish | opsional | pembanding engine dan usulan kandidat |

Tanpa python-chess dan Stockfish aplikasi **tetap berjalan**, tapi kandidat langkah tidak diperiksa
legalitasnya (server memberi peringatan) dan bagian pembanding engine menampilkan "tidak tersedia".

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

`python app.py` (tanpa venv) juga jalan, hanya saja tanpa validasi legalitas dan tanpa engine.

Buka http://127.0.0.1:8000 di browser. Berhenti dengan Ctrl+C.

Supaya anggota kelompok lain bisa membuka dari laptop atau HP di jaringan yang sama:

```bash
.venv/bin/python app.py --host 0.0.0.0 --port 8000
```

lalu buka `http://<alamat-IP-laptop>:8000`.

Basis data SQLite `skakmat.db` dibuat otomatis saat pertama dijalankan. Hapus berkas itu untuk
mengulang dari awal.

## Akun

| Akun | Kata sandi | Peran |
|---|---|---|
| kapten | kapten123 | Jabatan tertinggi, menjalankan konsensus |
| analis1 | analis123-1 | Decision maker |
| analis2 | analis123-2 | Decision maker |
| analis3 | analis123-3 | Decision maker |

Kata sandi di atas hanya akun demo. Ubah pada daftar `AKUN` di `app.py` sebelum basis data dibuat.

## Alur penggunaan

1. Masuk dengan salah satu akun. Posisi papan, riwayat langkah, dan tiga kandidat langkah tampil.
2. Setiap decision maker menilai tiap kandidat pada lima kriteria (skala 1 sampai 5), lalu menekan
   **Kirim penilaian**. Penilaian bisa diubah sampai konsensus dijalankan. Hasil TOPSIS pribadi langsung tampil.
3. Setelah keempat akun menilai, Kapten menekan **Jalankan konsensus (Borda)**.
4. Seluruh akun melihat langkah terpilih, tabel Borda, dan penilaian individual semua anggota.
5. Kapten dapat **Mengulangi putaran** atau **Membuat kasus baru** (FEN posisi, riwayat, tiga kandidat).
   Posisi dan ketiga kandidat diperiksa legalitasnya; kandidat ilegal ditolak dengan alasan. Tombol
   **Usulkan kandidat dari engine** (opsional) mengisi tiga kandidat dari Stockfish; boleh diubah.

## Metode

Kriteria (skala 1 sampai 5):

| Kode | Kriteria | Bobot | Jenis |
|---|---|---|---|
| C1 | Keamanan raja | 25 | benefit |
| C2 | Keamanan material | 20 | benefit |
| C3 | Penguasaan pusat papan | 20 | benefit |
| C4 | Peluang serangan | 20 | benefit |
| C5 | Risiko serangan balik lawan | 15 | cost |

**TOPSIS (individual):** normalisasi vektor per kriteria, dikali bobot, solusi ideal positif dan negatif
(benefit dan cost dibedakan), jarak D+ dan D−, skor preferensi V = D− / (D+ + D−), lalu peringkat.

**Borda (kelompok):** untuk tiga kandidat, bobot peringkat 1, 2, 3 adalah 3, 2, 1. Poin kandidat =
jumlah (bobot Borda dari peringkatnya × skor preferensi V) dari seluruh decision maker. Nilai Borda =
poin / total poin. Kandidat dengan nilai Borda tertinggi menjadi keputusan kelompok. Bila nilai
sama persis, peringkat dari Kapten yang menentukan.

Hasil mencerminkan kesepakatan kelompok, bukan jaminan langkah terbaik atau kemenangan. Keputusan
kelompok sepenuhnya berasal dari penilaian anggota; analisis posisi dilakukan anggota lewat kriteria.

### Engine sebagai pembanding, bukan kriteria

Stockfish **tidak** ikut menentukan keputusan. Nilainya tidak masuk TOPSIS maupun Borda, dan tidak
menjadi kriteria ke-6. Alasannya: skala engine (centipawn, tak terbatas, dari sudut satu pihak)
tidak sebanding dengan skala penilaian manusia 1 sampai 5; menggabungkan keduanya tanpa dasar akan
membuat hasil tidak bisa dipertanggungjawabkan.

Engine hanya dipakai untuk:

1. **Memeriksa legalitas** posisi dan kandidat langkah (cukup python-chess, tanpa Stockfish).
2. **Mengusulkan** tiga kandidat untuk Kapten (opsional). Usulan diurutkan menurut abjad, bukan
   menurut nilai engine, supaya tidak membocorkan peringkat engine sebelum anggota menilai.
3. **Membandingkan**, setelah konsensus, peringkat kelompok dengan peringkat engine: tabel
   berdampingan, penanda sama/berbeda, dan keterangan bila selisihnya di bawah 0,2 pion (praktis
   setara). Peringkat engine **ditahan sampai konsensus dijalankan**, supaya anggota tidak terpengaruh.

Batas engine: kedalaman 16 dan maksimal 1,5 detik per analisis, 5 detik untuk start, satu analisis
sekaligus. Hasil disimpan di memori server. Bila engine tidak ada, macet, atau gagal, server
mengirim `{"tersedia": false, "kode": ..., "alasan": ...}` dan seluruh halaman tetap berjalan.

## Tampilan (front end)

Front end ada di `static/` dan hanya memakai HTML, CSS, dan JavaScript biasa (tanpa framework, tanpa
build step). Perubahan pada pembaruan front end:

- **Papan catur:** bidak memakai glyph solid untuk kedua warna; bidak putih diberi garis tepi tebal
  agar terbaca di petak terang. Font simbol disebut eksplisit karena di sebagian sistem font ikon
  (mis. Font Awesome) membuat bidak hitam tidak tampil. Papan tetap persegi di semua lebar layar.
- **Penyegaran otomatis** tiap 15 detik, satu permintaan sekali jalan, berhenti saat tab tidak aktif
  dan setelah konsensus dijalankan (hasil sudah final). Ada keterangan waktu pembaruan terakhir dan
  tombol **Segarkan** manual. Setelah konsensus, perubahan dari Kapten (ulang putaran, kasus baru)
  baru terlihat di akun lain setelah menekan Segarkan atau memuat ulang halaman.
- **Sesi habis** kembali ke halaman masuk dengan pesan "Sesi berakhir, silakan masuk lagi."
- **Status memuat** saat halaman pertama dibuka, dan tombol aksi langsung nonaktif dengan teks
  "Mengirim…", "Menjalankan…", dan seterusnya selama permintaan berjalan (mencegah kirim ganda).
- **Penilaian:** setiap opsi berlabel (mis. "5 – sangat baik"). Kriteria C5 (cost) ditandai jelas;
  opsinya berbunyi "5 – risiko sangat besar". Di layar sempit (HP/tablet) tabel penilaian tampil
  sebagai kartu per kandidat.
- **Status penilaian** menampilkan siapa saja yang belum menilai; Panel Kapten menjelaskan kenapa
  tombol konsensus belum aktif.
- **Kasus baru:** FEN diperiksa di browser dengan pesan yang menunjuk letak kesalahan (server tetap
  memeriksa ulang).
- **Identitas decision maker:** tiap anggota punya warna aksen dan inisial (K, A1, A2, A3) yang sama
  di status penilaian, ringkasan "menunggu", tabel individual, dan animasi. Kapten berlencana kotak
  dengan tag **koordinator**. Keterangan tim menegaskan: satu tim, satu sisi papan, tiap orang di
  perangkat masing-masing.
- **Animasi penggabungan Borda:** batang bertumpuk menunjukkan poin tiap penilai (bobot peringkat × V)
  ditambahkan satu per satu ke setiap kandidat, lalu pemenang ditandai (sekitar 1,7 detik, bisa
  diputar ulang). Hasil akhir dan tabel Borda sudah tampil sebelum animasi selesai. Bila sistem
  meminta "kurangi gerakan" (`prefers-reduced-motion`), hasil akhir langsung tampil tanpa animasi.
- **Pembanding engine:** lihat bagian Metode di atas.
- **Aksesibilitas:** tabel punya caption, `scope`, dan `aria-label`; pesan memakai `role="status"`
  atau `role="alert"`; fokus keyboard terlihat; kontras warna memenuhi WCAG AA di mode terang dan gelap.

Semua teks dari server tetap dimasukkan lewat `textContent`, tanpa skrip atau style inline (sesuai CSP).

## Struktur berkas

```
SKAKMAT/
├── app.py            server HTTP, API, basis data, login
├── gdss.py           perhitungan TOPSIS dan Borda
├── mesin.py          legalitas langkah (python-chess) dan pembanding engine (Stockfish)
├── static/           index.html, style.css, app.js
├── requirements.txt  paket Python (chess)
├── test_gdss.py      tes algoritma (dibandingkan dengan NumPy bila terpasang)
├── test_e2e.py       tes ujung ke ujung (login, hak akses, konsensus)
├── test_mesin.py     tes legalitas dan engine: hidup, mati, menggantung, tanpa python-chess
└── README.md
```

Tes:

```bash
python test_gdss.py
.venv/bin/python test_e2e.py
.venv/bin/python test_mesin.py   # skenario yang butuh python-chess/Stockfish dilewati bila belum ada
```

## API tambahan

| Metode | Path | Keterangan |
|---|---|---|
| GET | `/api/kasus` | field baru `engine`: `{"tersedia": true, "engine", "batas", "sudut_pandang", "kandidat": [{"langkah", "san", "cp", "mat", "peringkat"}]}` atau `{"tersedia": false, "kode", "alasan"}`. Field lama tidak berubah. |
| POST | `/api/usul-kandidat` | `{"fen"}` → `{"ok", "kandidat": [3 langkah, urut abjad]}`. Kapten saja. 400 bila posisi tidak sah, 503 bila engine tidak tersedia. |
| POST | `/api/kasus-baru` | tambahan: 400 bila posisi/kandidat ilegal; tanpa python-chess respons membawa `peringatan`. |

## Keamanan singkat

Kata sandi disimpan sebagai hash PBKDF2 dengan garam. Sesi memakai cookie HttpOnly dan SameSite=Strict.
Login dibatasi setelah lima kali gagal. Permintaan POST dengan Origin asing ditolak. Hanya akun Kapten yang
bisa menjalankan konsensus, mengulang putaran, dan membuat kasus. Semua kueri SQL berparameter, teks dari
server dimasukkan ke halaman lewat `textContent`, dan Content-Security-Policy melarang skrip inline.
Aplikasi ini untuk demo kelompok di jaringan lokal, bukan untuk dipasang di internet publik tanpa HTTPS.
