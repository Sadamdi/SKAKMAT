# SKAKMAT: Catur Konsultasi GDSS

Sistem Kolaborasi Analis untuk Keputusan Melangkah Antar Tim. Project akhir Praktikum Sistem
Informasi, Kelompok 2, Kelas B.

Tiga decision maker membuka papan yang sama dan memainkan bidak putih bersama. Tiap ronde, setiap
anggota mengusulkan satu langkah dengan **menggerakkan bidak di papan**. Begitu ketiga usulan masuk,
**penilaian individual** tiap anggota langsung tersedia: nilai C1–C5 diukur mesin dari posisi papan,
lalu TOPSIS dijalankan untuk tiap anggota dengan bobot gaya mainnya. Sesudah itu **Ketua (akun dengan
jabatan tertinggi) menjalankan konsensus dengan voting Borda** yang menggabungkan ketiga peringkat
menjadi satu keputusan kelompok. Langkah pemenang dimainkan, lawan membalas, dan ronde berikutnya
dimulai. Semua akun dapat melihat hasil konsensus.

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

## Akun

| Akun | Kata sandi | Jabatan | Gaya main | Bobot C1–C5 |
|---|---|---|---|---|
| anggota1 | anggota123-1 | **Ketua** (jabatan tertinggi) | Menyerang | 20 · 15 · 20 · 30 · 15 |
| anggota2 | anggota123-2 | Anggota | Seimbang | 25 · 20 · 20 · 20 · 15 |
| anggota3 | anggota123-3 | Anggota | Bertahan | 30 · 30 · 15 · 10 · 15 |

Ketiganya sama-sama mengusulkan langkah dan menerima hasil. Yang membedakan: **Ketua** satu-satunya yang
boleh menjalankan konsensus Borda (konstanta `KETUA` di `app.py`), dan tiap akun punya gaya main
sendiri. Kata sandi di atas hanya akun demo; ubah pada daftar `AKUN` di `app.py` sebelum basis data
dibuat.

## Alur penggunaan

1. **Masuk** dengan salah satu akun. Papan, ronde, dan riwayat langkah langsung tampil.
2. **Usulkan langkah dengan menggerakkan bidak.** Klik bidak putih (petak tujuan yang sah langsung
   ditandai), lalu klik tujuan. Bisa juga diseret. Dengan keyboard: Tab ke bidak, Enter untuk
   memilih, Tab ke petak tujuan, Enter untuk mengusulkan, Esc untuk batal. Langkah ilegal ditolak
   server dan bidak kembali ke tempatnya dengan pesan singkat.
3. **Usulan masih bisa diganti** (dengan menggerakkan bidak lain) sampai anggota terakhir mengusulkan.
   Usulan anggota lain baru terlihat setelah ronde dinilai, supaya tiap usulan tetap independen.
4. **Begitu usulan ketiga masuk, penilaian individual muncul otomatis** untuk semua akun: nilai C1–C5
   tiap usulan dan satu tabel TOPSIS per anggota. Usulan dikunci pada tahap ini.
5. **Ketua menekan "Jalankan konsensus (voting Borda)".** Akun lain melihat "menunggu Ketua" dan tidak
   punya tombol itu (server menolak dengan 403). Semua akun lalu melihat tabel Borda, animasi
   penggabungan, dan pembanding engine.
6. **Langkah pemenang dimainkan, lawan membalas** (Stockfish), lalu ronde berikutnya siap diisi.
   Riwayat langkah diperbarui. Bila permainan selesai (skakmat/seri), tombol **Ronde baru** memulai
   permainan lagi dari posisi awal; riwayat permainan sebelumnya tetap tersimpan di server.

Tidak ada form isian di aplikasi ini: tidak ada dropdown nilai, tidak ada isian FEN, tidak ada
"buat kasus baru", tidak ada kotak teks. Satu-satunya input adalah gerakan bidak.

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
├── docs/ARSITEKTUR.md   arsitektur, pilihan teknologi, deploy
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
| POST | `/api/login` | `{"username", "sandi"}` → set cookie sesi |
| GET | `/api/me` | pengguna yang sedang masuk |
| GET | `/api/ronde` | keadaan ronde: kasus (FEN, nomor, riwayat, selesai), peserta + status usulan, usulan sendiri, langkah sah, hasil terakhir, status server. Aman dipanggil berkala — tidak pernah memanggil engine. |
| POST | `/api/usul` | `{"langkah": "e2e4"}` → usulan satu langkah, tervalidasi legalitasnya. Bila ini usulan terakhir, respons berisi `dinilai: true` dan hasil konsensus. |
| POST | `/api/konsensus` | **hanya Ketua (403 untuk akun lain)**: voting Borda atas penilaian individual semua anggota, lalu langkah pemenang dimainkan. Ditolak 409 bila belum semua anggota mengusulkan atau ronde sudah dikonsensuskan. |
| POST | `/api/ulang` | ronde baru: permainan baru dari posisi awal, riwayat lama tetap tersimpan |
| POST | `/api/keluar` | hapus sesi |

Endpoint alur lama (`/api/nilai`, `/api/kasus`, `/api/kasus-baru`, `/api/usul-kandidat`) sudah tidak
dipakai dan menjawab **410 Gone** dengan penjelasan.

Semua endpoint: pemeriksaan asal permintaan (Origin), cek sesi, validasi tipe masukan, dan kueri
berparameter.

## Keamanan singkat

Kata sandi disimpan sebagai hash PBKDF2 dengan garam. Sesi memakai cookie HttpOnly dan
SameSite=Strict, berlaku 8 jam. Login dibatasi setelah lima kali gagal. Permintaan POST dengan
Origin asing ditolak. Hanya Ketua yang boleh menjalankan konsensus (dicek di server, bukan hanya disembunyikan di tampilan). Semua kueri SQL
berparameter, teks dari server dimasukkan ke halaman lewat `textContent`, dan Content-Security-Policy
melarang skrip inline. Aplikasi ini untuk demo kelompok di jaringan lokal, bukan untuk dipasang di
internet publik tanpa HTTPS.
