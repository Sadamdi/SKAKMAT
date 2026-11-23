# Cara kerja SKAKMAT dan buktinya

Dokumen ini menjelaskan apa yang dilakukan aplikasi, bagaimana keputusan kelompok dihitung, dan bukti bahwa
semuanya berjalan seperti itu.

## 1. Gambaran satu kalimat

Beberapa orang (maksimal 3 per pertandingan) bermain catur **bersama melawan komputer**. Saat giliran tim, tiap
orang mengusulkan langkah, **TOPSIS** menilai usulan menurut gaya main tiap orang, dan **Ketua** menjalankan
**voting Borda** untuk memutuskan satu langkah. Saat giliran lawan, komputer membalas dengan catur biasa.

## 2. Siapa melakukan apa

| Tahap | Pelaku | Teknik |
|---|---|---|
| Daftar, masuk, buat atau gabung pertandingan | Pemain | Akun dengan kata sandi hash PBKDF2, sesi cookie |
| Mengusulkan langkah | Tiap anggota | Menggerakkan bidak; server memeriksa legalitas (python-chess) |
| Mengukur nilai C1 sampai C5 | Mesin | Dihitung dari posisi setelah langkah (python-chess + Stockfish) |
| **Penilaian individual** | Otomatis, per anggota | **TOPSIS** dengan bobot gaya main anggota itu |
| **Konsensus kelompok** | **Ketua** (pembuat pertandingan) | **Voting Borda** atas ketiga peringkat TOPSIS |
| **Balasan lawan** | Komputer | Stockfish kedalaman 10 (catur biasa, bukan TOPSIS) |

Jadi: giliran tim = metode pengambilan keputusan kelompok (TOPSIS lalu Borda); giliran lawan = algoritma catur.

## 3. Pertandingan, lobi, dan keanggotaan

- Setelah masuk, pemain ada di **lobi**: daftar pertandingan, form buat, dan gabung dengan kode.
- Satu pemain hanya di satu pertandingan. Pertandingan menampung maksimal 3 pemain, dengan gaya main berbeda
  (Menyerang, Seimbang, Bertahan).
- **Ketua** = pembuat pertandingan, satu-satunya yang boleh menjalankan konsensus (diperiksa di server).
- Boleh **keluar** dan **bergabung** kapan saja. Aturan yang berlaku saat anggota berubah:

| Kejadian | Akibat |
|---|---|
| Anggota keluar saat ronde berjalan | Usulannya dibuang; yang tersisa tidak menunggunya. Bila semua yang tersisa sudah mengusulkan, penilaian dibuat dari mereka saja |
| Anggota baru bergabung di tengah ronde | Penilaian lama dibatalkan; ronde menunggu usulan anggota baru |
| Ketua keluar | Anggota yang bergabung paling awal menjadi Ketua |
| Semua pemain keluar, atau logout, atau diam 2 menit | Pertandingan berakhir otomatis ("Semua pemain keluar") dan hilang dari lobi |
| Logout | Otomatis keluar dari pertandingan |

## 4. Cara keputusan dihitung (contoh nyata)

Ronde 1, posisi Giuoco Piano (putih berjalan). Tiga anggota mengusulkan **d3** (Seimbang), **O-O** (Bertahan),
dan **d4** (Menyerang).

**Langkah 1, nilai kriteria diukur mesin** (skala 1 sampai 5, C5 adalah cost):

| Alternatif | C1 Keamanan raja | C2 Keamanan material | C3 Pusat papan | C4 Peluang serangan | C5 Risiko balik (cost) |
|---|---|---|---|---|---|
| d3 | 3,00 | 3,00 | 3,00 | 3,51 | 1,50 |
| O-O | 4,17 | 2,08 | 2,51 | 3,25 | 2,43 |
| d4 | 3,64 | 2,08 | 3,92 | 3,91 | 1,98 |

**Langkah 2, TOPSIS tiap anggota.** Contoh gaya Seimbang (bobot 25, 20, 20, 20, 15):

1. Normalisasi vektor per kriteria: r(i,j) = x(i,j) / akar(jumlah kuadrat kolom j). Misal C1: d3 = 0,4765, O-O = 0,6623, d4 = 0,5782.
2. Kalikan bobot (dalam bentuk pecahan): y(i,j) = w(j) x r(i,j).
3. Solusi ideal: A+ = nilai terbaik tiap kolom (terbesar untuk benefit, **terkecil untuk cost**), A- = terburuk.
   Di sini A+ = (0,1656; 0,1428; 0,1416; 0,1266; 0,0647) dan A- = (0,1191; 0,0990; 0,0907; 0,1052; 0,1049).
4. Jarak ke A+ dan A-: D+ = (0,0586; 0,0811; 0,0528) dan D- = (0,0626; 0,0465; 0,0638) untuk (d3, O-O, d4).
5. Skor preferensi V = D- / (D+ + D-) = (0,5165; 0,3642; 0,5471), jadi peringkat **d4 (1), d3 (2), O-O (3)**.

(Angka di layar sedikit berbeda di digit terakhir karena aplikasi memakai nilai C tanpa pembulatan.)

Hasil tiga anggota, dengan bobot gayanya masing-masing:

| Alternatif | V Menyerang | Peringkat | V Seimbang | Peringkat | V Bertahan | Peringkat |
|---|---|---|---|---|---|---|
| d3 | 0,5134 | 2 | 0,5179 | 2 | 0,5621 | **1** |
| O-O | 0,3172 | 3 | 0,3624 | 3 | 0,3896 | 3 |
| d4 | 0,6108 | **1** | 0,5473 | **1** | 0,4226 | 2 |

Penilaian individual selesai di sini. Gaya Bertahan memilih d3, dua gaya lain memilih d4.

**Langkah 3, voting Borda oleh Ketua.** Untuk 3 alternatif, peringkat 1, 2, 3 diberi bobot 3, 2, 1. Poin sebuah
alternatif = jumlah (bobot Borda x V) dari semua anggota; nilai Borda = poin / total poin.

| Alternatif | Perhitungan poin | Poin | Nilai Borda | Peringkat |
|---|---|---|---|---|
| d4 | 3 x 0,6108 + 3 x 0,5473 + 2 x 0,4226 | 4,3194 | 0,4727 | **1** |
| d3 | 2 x 0,5134 + 2 x 0,5179 + 3 x 0,5621 | 3,7491 | 0,4103 | 2 |
| O-O | 1 x (0,3172 + 0,3624 + 0,3896) | 1,0693 | 0,1170 | 3 |

**d4** menjadi keputusan kelompok walau satu anggota memilih d3. Lawan (Stockfish) lalu membalas exd4 dan ronde 2
dimulai. Bila nilai Borda sama persis, pemutusnya berturut-turut dukungan usulan, jumlah peringkat TOPSIS, dan
urutan usulan.

## 5. Bukti

**a. Tes otomatis** (semuanya lolos, Stockfish 19 aktif; log di `agents/uas/outputs/logs/` pada folder kerja):

| Berkas | Isi yang dibuktikan |
|---|---|
| `test_gdss.py` | TOPSIS cocok dengan NumPy pada 200 matriks acak, juga untuk tiga profil gaya (200 matriks pecahan). Pada 4997 matriks acak, peringkat tiga gaya berbeda di 3083 kasus dan pemenang Borda berbeda dari TOPSIS tunggal di 49 kasus (jadi Borda memang mengubah hasil) |
| `test_mesin.py` (48) | Legalitas langkah, C1 sampai C5 deterministik dan benar arahnya (rokade lebih aman bagi raja, d4 menguasai pusat, pengorbanan gajah merugikan material), cache engine, Stockfish hidup, mati, menggantung, tanpa python-chess |
| `test_e2e.py` (113) | Pendaftaran dan validasinya, lobi, buat dan gabung, pertandingan penuh, gaya ganda ditolak, Ketua, 403/409, satu ronde penuh, anggota keluar dan bergabung di tengah ronde, Ketua berpindah, logout, pertandingan berakhir otomatis, pemain diam, dua pertandingan paralel, dua usulan serentak, migrasi basis data, langkah skakmat, kata sandi dari lingkungan |

**b. Hasil Borda = hitungan independen.** `test_e2e.py` menghitung ulang TOPSIS dan Borda di luar server
(`gdss.py`) dan membandingkannya dengan angka dari API sampai selisih di bawah 1e-12.

**c. Uji di browser** dengan akun yang didaftarkan lewat tampilan: daftar akun, lobi dengan pertandingan orang lain,
bergabung, usulan lewat klik di papan, penilaian individual, konsensus oleh Ketua (anggota biasa tidak punya
tombolnya), balasan Stockfish 19, keluar dari pertandingan, membuat pertandingan sendiri (menjadi Ketua), dan
pertandingan berakhir otomatis saat pemain terakhir logout (tercatat di tabel `pertandingan`: status `selesai`,
alasan "Semua pemain keluar dari pertandingan."). Screenshot di `agents/uas/outputs/screens/`.

**d. Uji lewat alamat internet** (Cloudflare Quick Tunnel): halaman 200, API tanpa login 401, kata sandi
bawaan ditolak saat memakai sandi acak, cookie sesi HttpOnly dan Secure, satu ronde penuh tiga akun.

## 6. Batasan

- Satu proses server; kunci ronde dan batas login ada di memori proses.
- Lawan memakai Stockfish kedalaman 10, bukan kekuatan penuh; tanpa Stockfish memakai aturan sederhana
  (ambil skakmat satu langkah, tangkapan menguntungkan, selain itu langkah pertama menurut urutan UCI).
- Hasil mencerminkan kesepakatan kelompok menurut kriteria yang diukur, bukan jaminan langkah terbaik.
- Akun demo memakai kata sandi bawaan; ganti lewat variabel `SKAKMAT_SANDI_<USERNAME>` bila dibuka di internet.
