# SKAKMAT: GDSS Pemilihan Langkah Catur

Sistem Kolaborasi Analis untuk Keputusan Melangkah Antar Tim. Project akhir Praktikum Sistem Informasi,
Kelompok 2, Kelas B.

Website GDSS dengan empat decision maker (Kapten, Analis 1, Analis 2, Analis 3). Setiap akun menilai
tiga kandidat langkah catur secara individual (TOPSIS). Setelah keempatnya selesai, akun Kapten
(jabatan tertinggi) menjalankan konsensus dengan voting Borda. Semua akun dapat melihat hasilnya.

## Cara menjalankan

Hanya butuh Python 3.9 atau lebih baru. Tidak ada paket yang perlu diinstal.

```bash
cd "D:\adam kuliah\Semester 5\Information System Praktikum\UAS\SKAKMAT"
python app.py
```

Buka http://127.0.0.1:8000 di browser. Berhenti dengan Ctrl+C.

Supaya anggota kelompok lain bisa membuka dari laptop atau HP di jaringan yang sama:

```bash
python app.py --host 0.0.0.0 --port 8000
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

Hasil mencerminkan kesepakatan kelompok, bukan jaminan langkah terbaik atau kemenangan. Sistem tidak
menganalisis posisi secara otomatis; analisis dilakukan anggota lewat penilaian kriteria.

## Struktur berkas

```
SKAKMAT/
├── app.py            server HTTP, API, basis data, login
├── gdss.py           perhitungan TOPSIS dan Borda
├── static/           index.html, style.css, app.js
├── test_gdss.py      tes algoritma (dibandingkan dengan NumPy bila terpasang)
├── test_e2e.py       tes ujung ke ujung (login, hak akses, konsensus)
└── README.md
```

Tes:

```bash
python test_gdss.py
python test_e2e.py
```

## Keamanan singkat

Kata sandi disimpan sebagai hash PBKDF2 dengan garam. Sesi memakai cookie HttpOnly dan SameSite=Strict.
Login dibatasi setelah lima kali gagal. Permintaan POST dengan Origin asing ditolak. Hanya akun Kapten yang
bisa menjalankan konsensus, mengulang putaran, dan membuat kasus. Semua kueri SQL berparameter, teks dari
server dimasukkan ke halaman lewat `textContent`, dan Content-Security-Policy melarang skrip inline.
Aplikasi ini untuk demo kelompok di jaringan lokal, bukan untuk dipasang di internet publik tanpa HTTPS.
