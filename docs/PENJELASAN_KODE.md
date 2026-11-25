# Penjelasan kode per berkas

Peta untuk membaca kode SKAKMAT. Urutan baca yang disarankan: `gdss.py` (paling pendek, inti perhitungan),
`mesin.py`, `app.py`, lalu `static/app.js`.

## gdss.py (159 baris): TOPSIS dan Borda

Python murni, tanpa pustaka luar. Semua fungsi murni (masukan sama, keluaran sama) sehingga mudah diuji.

| Bagian | Fungsi |
|---|---|
| `KRITERIA` | lima kriteria C1 sampai C5 dengan bobot dasar dan jenis benefit/cost |
| `validasi_nilai`, `validasi_matriks` | memastikan matriks keputusan berisi angka 1 sampai 5 dengan ukuran benar |
| `peringkat(nilai)` | peringkat 1 = nilai terbesar; seri diputus indeks lebih kecil |
| `topsis(skor, kriteria)` | satu penilai: normalisasi vektor, bobot, solusi ideal (cost dibalik), jarak, skor V, peringkat. Mengembalikan semua tahap (r, y, A+, A−, D+, D−, V, rank) supaya bisa ditampilkan |
| `borda(hasil_per_penilai)` | bobot n−p+1, poin = Σ bobot × V, nilai = poin/total, peringkat |
| `PROFIL` | tiga gaya main dengan bobot masing-masing |
| `kriteria_profil(gaya)` | salinan `KRITERIA` dengan bobot gaya itu |
| `konsensus_gaya(matriks, gaya_penilai, dukungan)` | menjalankan `topsis` per anggota lalu `borda`, dengan aturan seri (dukungan, jumlah peringkat, urutan usulan) |

## mesin.py (516 baris): papan catur dan pengukuran

Pembungkus python-chess dan Stockfish. Bila pustaka atau engine tidak ada, fungsi mengembalikan
`tidak_tersedia(kode, alasan)` dan server tetap hidup.

| Bagian | Fungsi |
|---|---|
| Konstanta | `KEDALAMAN_KRITERIA=12`, `KEDALAMAN_LAWAN=10`, `WAKTU_ANALISIS=1,5 s`, `PUSAT=(d4,e4,d5,e5)`, nilai bidak |
| `papan`, `baca_langkah`, `validasi_kasus` | membaca FEN dan teks langkah (UCI atau SAN) dengan pesan galat jelas |
| `validasi_usulan(fen, teks)` | langkah sah atau tidak untuk posisi itu |
| `langkah_sah`, `mainkan`, `status_akhir` | daftar langkah sah (untuk menandai petak), menjalankan langkah, deteksi skakmat/pat/remis |
| `_buka_engine`, `path_engine` | mencari dan membuka Stockfish; lokasi bisa lewat `SKAKMAT_STOCKFISH` (`mati` = tanpa engine) |
| `_skala`, `_skala_positif` | pemetaan `tanh` ke skala 1 sampai 5 |
| `_c1` ... `_c5` | pengukur lima kriteria (rumus di [ALGORITMA.md](ALGORITMA.md) bagian 3) |
| `_c2_statis`, `_c2_engine` | C2 tanpa engine / dengan variasi utama Stockfish |
| `nilai_kriteria(fen, daftar_uci)` | titik masuk: mengukur semua alternatif, memakai cache, jatuh ke C2 statis bila engine gagal. Mengembalikan matriks dan rincian tiap angka |
| `langkah_lawan(fen)` | balasan lawan: Stockfish kedalaman 10, atau aturan sederhana (ambil skakmat, tangkapan untung) bila tanpa engine |
| `_kunci` | satu analisis engine sekali jalan agar tidak menumpuk |

## app.py (884 baris): server, basis data, alur

FastAPI. Handler API sinkron dijalankan di thread pool (`run_in_threadpool`) karena SQLite dan engine memblokir.

| Bagian | Isi |
|---|---|
| Konstanta | `MAKS_ANGGOTA=3`, `TIMEOUT_AKTIF=120 s`, akun demo, posisi awal |
| Basis data | `db()`, `siapkan_db()` (skema v3, migrasi: DB lama dicadangkan), tabel `pengguna`, `sesi`, `pertandingan`, `anggota`, `kasus`, `usulan`, `penilaian_individual`, `konsensus` |
| Akun | `hash_sandi` (PBKDF2), `buat_sesi`, `pengguna_dari_cookie`, `post_daftar`, `post_login`, `post_keluar` |
| Pertandingan | `buat_pertandingan`, `gabung_pertandingan`, `keluar_pertandingan`, `pilih_gaya`, `anggota_aktif`, `ringkas_pertandingan` |
| `setelah_perubahan_anggota` | satu pintu untuk semua perubahan anggota: akhiri bila kosong, pindahkan Ketua, buang dan buat ulang penilaian |
| `bersihkan_tidak_aktif`, `denyut` | pemain diam 120 detik dikeluarkan; tiap permintaan menandai pemain aktif |
| Ronde | `permainan_baru`, `buat_ronde`, `kasus_aktif`, `status_usulan` |
| **`siapkan_penilaian`** | tahap 1: gabung usulan, `mesin.nilai_kriteria`, `gdss.konsensus_gaya` per anggota, simpan |
| **`jalankan_konsensus`** | tahap 2: Borda, mainkan pemenang, balasan lawan, ronde baru, simpan jejak |
| Endpoint | `post_buat`, `post_gabung`, `post_keluar_pertandingan`, `get_lobi`, `get_ronde`, `post_usul`, `post_konsensus` (403 bila bukan Ketua), `post_ulang` |
| `api(fungsi)` | pembungkus: buka koneksi, cek sesi (401), `denyut`, jalankan handler |
| Keamanan | middleware `kepala_dan_asal` (header CSP, cek Origin), batas laju login/daftar, cookie HttpOnly/SameSite=Strict, `berkas_statis` dengan proteksi path traversal |
| `_kunci_ronde` | kunci agar dua usulan serentak atau konsensus ganda tidak merusak data |

Tabel kunci dan relasi: `pertandingan` 1—n `anggota`; `pertandingan` 1—n `kasus` (satu per ronde); `kasus`
1—n `usulan`; `kasus` 1—1 `penilaian_individual` lalu 1—1 `konsensus`.

## static/ (front end tanpa framework)

| Berkas | Isi |
|---|---|
| `index.html` | kerangka halaman: form masuk/daftar, lobi, papan, kartu penilaian, hasil |
| `style.css` | tata letak responsif (papan persegi), mode terang/gelap, kontras WCAG AA |
| `app.js` | semua perilaku di bawah |

Fungsi penting di `app.js`:

| Fungsi | Tugas |
|---|---|
| `api(path, body)` | pembungkus `fetch` JSON dengan pesan galat |
| `muat()` | memanggil `/api/ronde`; kosong = tampilkan lobi, ada = gambar ronde. Dipanggil tiap 4 detik |
| `muatLobi`, `aksiLobi`, `tandaLobi` | lobi; hanya digambar ulang bila isinya berubah supaya klik tidak hilang |
| `gambarPapan(fen)` | menggambar papan dan bidak dari FEN |
| `klikPetak`, `akhiriSeret`, `kirimUsulan` | memilih bidak, menandai tujuan sah, mengirim `/api/usul` |
| `renderRonde`, `renderIndividual` | status tim, usulan, kartu penilaian TOPSIS per anggota, tombol konsensus (hanya Ketua) |
| `renderHasil`, `renderAnimasi` | tabel Borda, animasi poin, kalimat penjelas, pembanding engine |
| `tampilLogin`, `tampilDaftar`, `tampilApp` | berpindah tampilan |

Aturan keamanan klien: semua teks dari server dimasukkan dengan `textContent` (tanpa `innerHTML`), tanpa skrip
inline (CSP `default-src 'self'`).

## Tes

| Berkas | Isi |
|---|---|
| `test_gdss.py` | TOPSIS cocok dengan NumPy (200 matriks acak, tiga profil), Borda mengubah hasil pada kasus nyata |
| `test_mesin.py` (48) | legalitas, C1–C5 deterministik dan benar arahnya, engine hidup/mati/menggantung, tanpa python-chess |
| `test_e2e.py` (113) | daftar/login, lobi, buat/gabung/keluar, Ketua, 403/409, satu ronde penuh, pertandingan paralel, pemain diam, migrasi DB, skakmat |
