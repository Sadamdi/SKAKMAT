# Algoritma SKAKMAT

Dokumen ini menjelaskan seluruh perhitungan dari awal sampai akhir: dari langkah yang diusulkan sampai
langkah yang dimainkan tim. Contoh angka memakai ronde 1 posisi Giuoco Piano (hitungan lengkap ada di
[CARA_KERJA.md](CARA_KERJA.md)). Kode yang dibahas: `mesin.py` (pengukuran), `gdss.py` (TOPSIS dan Borda),
`app.py` (alur).

## 1. Peta besar

```
 usulan tiap anggota ──► [1] gabungkan jadi alternatif
                              │
                              ▼
                    [2] mesin mengukur C1..C5 tiap alternatif      (mesin.py)
                              │   hasil: matriks keputusan X (m alternatif × 5 kriteria), nilai 1..5
                              ▼
                    [3] TOPSIS sekali per anggota, bobot = gayanya  (gdss.topsis)
                              │   hasil: skor V dan peringkat per anggota  → "penilaian individual"
                              ▼
                    [4] Ketua menekan konsensus → voting Borda      (gdss.borda)
                              │   hasil: satu pemenang
                              ▼
                    [5] langkah pemenang dimainkan di papan
                              ▼
                    [6] lawan membalas dengan Stockfish (catur biasa, tanpa TOPSIS)
                              ▼
                         ronde berikutnya
```

Tahap 1 sampai 3 berjalan otomatis begitu anggota terakhir mengusulkan. Tahap 4 sampai 6 berjalan saat Ketua
menekan tombol konsensus.

## 2. Tahap 1: usulan menjadi alternatif

Tiap anggota mengirim satu langkah (misalnya `d2d4`). Server memeriksa legalitasnya dengan python-chess
(`mesin.validasi_usulan`). Usulan boleh diganti selama belum semua anggota mengusulkan.

Bila dua anggota mengusulkan langkah yang sama, keduanya digabung menjadi **satu alternatif** dengan
`dukungan = 2`. Jadi tiga anggota bisa menghasilkan 1, 2, atau 3 alternatif (`app.siapkan_penilaian`).
Urutan alternatif mengikuti waktu usulan masuk.

## 3. Tahap 2: mesin mengukur C1 sampai C5

Setiap alternatif dimainkan dulu di salinan papan, lalu posisi **setelah langkah** diukur untuk tim yang
baru berjalan. Semua nilai dipetakan ke skala 1 sampai 5 dengan `tanh` supaya satu kriteria tidak
menenggelamkan yang lain. Dua fungsi pemetaan:

| Fungsi | Rumus | Dipakai bila |
|---|---|---|
| `_skala(x, s)` | `3 + 2·tanh(x/s)`, 0 menjadi 3 | nilai mentah bisa negatif (selisih) |
| `_skala_positif(x, s)` | `1 + 4·tanh(max(x,0)/s)`, 0 menjadi 1 | nilai mentah tidak negatif |

| Kriteria | Nilai mentah | Skala | Arah |
|---|---|---|---|
| C1 Keamanan raja | `perisai_pion − serangan_ke_zona_raja` (pion tim tepat di depan raja, dikurangi jumlah penyerang lawan ke petak raja dan sekelilingnya) | `_skala(·, 3)` | makin besar makin baik |
| C2 Keamanan material | perubahan selisih material setelah variasi utama Stockfish dimainkan (4 ply, diperpanjang sampai 8 selama masih tangkapan). Tanpa engine: perubahan material dikurangi ancaman tangkapan terbesar lawan | `_skala(·, 2)` | makin besar makin baik |
| C3 Penguasaan pusat | untuk d4, e4, d5, e5: `penyerang tim − penyerang lawan + (1 bila diduduki tim, −1 bila diduduki lawan)`, dijumlah | `_skala(·, 4)` | makin besar makin baik |
| C4 Peluang serangan | `bidak lawan yang diserang + 2·(memberi skak) + mobilitas/10` | `_skala_positif(·, 8)` | makin besar makin baik |
| C5 Risiko balik | `untung tangkapan terbaik lawan + 0,5·min(jumlah langkah skak lawan, 4)` | `_skala_positif(·, 4)` | **cost**: makin kecil makin baik |

Nilai bidak: pion 1, kuda 3, gajah 3, benteng 5, menteri 9. "Untung tangkapan" = nilai korban dikurangi nilai
pemakan bila korban masih dilindungi (`mesin._ancaman_tangkap`). Bila langkah itu langsung skakmat, nilainya
dipaksa C1=C2=C4=5 dan C5=1.

Hasilnya matriks `X[i][j]` (alternatif i, kriteria j). Matriks yang sama dipakai semua anggota. Ia
**deterministik**: posisi yang sama selalu menghasilkan angka yang sama (Stockfish 1 thread, hash dibersihkan,
kedalaman 12), dan hasilnya disimpan di cache.

Stockfish di tahap ini hanya **mengukur** (variasi utama untuk C2). Ia tidak memilih langkah dan tidak ikut
voting.

## 4. Tahap 3: TOPSIS per anggota (penilaian individual)

Nilai C sama untuk semua, tetapi **bobot** tiap anggota berbeda menurut gaya mainnya:

| Gaya | C1 | C2 | C3 | C4 | C5 |
|---|---|---|---|---|---|
| Menyerang | 20 | 15 | 20 | 30 | 15 |
| Seimbang | 25 | 20 | 20 | 20 | 15 |
| Bertahan | 30 | 30 | 15 | 10 | 15 |

Untuk setiap anggota, `gdss.topsis(X, kriteria_dengan_bobot_gayanya)` melakukan:

1. **Bobot pecahan:** `w_j = bobot_j / jumlah bobot`.
2. **Normalisasi vektor:** `r_ij = x_ij / √(Σ_i x_ij²)`.
3. **Terbobot:** `y_ij = w_j · r_ij`.
4. **Solusi ideal:** untuk benefit `A⁺_j = max_i y_ij`, `A⁻_j = min_i y_ij`. Untuk cost (C5) dibalik:
   `A⁺_j = min`, `A⁻_j = max`.
5. **Jarak:** `D⁺_i = √Σ_j (y_ij − A⁺_j)²`, `D⁻_i = √Σ_j (y_ij − A⁻_j)²`.
6. **Skor preferensi:** `V_i = D⁻_i / (D⁺_i + D⁻_i)`. Bila penyebut 0, `V = 0,5`.
7. **Peringkat:** V terbesar = peringkat 1 (`gdss.peringkat`; V sama diputus indeks lebih kecil).

Hasil tahap ini disimpan di tabel `penilaian_individual` dan langsung terlihat oleh semua anggota. Contoh
ronde 1: gaya Menyerang dan Seimbang memilih d4, gaya Bertahan memilih d3.

## 5. Tahap 4: voting Borda oleh Ketua

`gdss.borda` menggabungkan ketiga peringkat. Untuk n alternatif, peringkat p mendapat bobot Borda `n − p + 1`
(3, 2, 1 untuk tiga alternatif).

```
poin_i  = Σ_anggota ( bobot_borda(peringkat anggota atas i) × V_i anggota itu )
nilai_i = poin_i / Σ poin
```

Alternatif dengan `nilai` terbesar menang. Contoh ronde 1:

| Alternatif | Poin | Nilai | Peringkat |
|---|---|---|---|
| d4 | 3×0,6108 + 3×0,5473 + 2×0,4226 = 4,3194 | 0,4727 | 1 |
| d3 | 2×0,5134 + 2×0,5179 + 3×0,5621 = 3,7491 | 0,4103 | 2 |
| O-O | 1×(0,3172+0,3624+0,3896) = 1,0693 | 0,1170 | 3 |

**Aturan seri** (`gdss.konsensus_gaya`): bila nilai Borda sama (dibulatkan 12 desimal), menang yang
(1) didukung lebih banyak usulan, lalu (2) jumlah peringkat TOPSIS-nya lebih kecil, lalu (3) diusulkan lebih
dulu.

**Kenapa Borda berguna:** satu anggota memilih d3, dua memilih d4, tetapi Borda memakai *kekuatan* preferensi
(V), bukan sekadar hitung suara. Pada 4997 matriks acak, pemenang Borda berbeda dari pemenang TOPSIS satu
gaya pada 49 kasus (`test_gdss.py`).

**Kenapa hanya Ketua:** tugas dosen meminta konsensus dijalankan akun berjabatan tertinggi. Server menolak akun
lain dengan HTTP 403 (bukan hanya menyembunyikan tombol).

## 6. Tahap 5 dan 6: langkah dimainkan, lawan membalas

`app.jalankan_konsensus`:

1. Langkah pemenang dimainkan (`mesin.mainkan`), riwayat ditambah.
2. Bila permainan belum selesai, `mesin.langkah_lawan` memilih balasan.
   - **Dengan Stockfish:** `engine.play` kedalaman 10, batas waktu 1,5 detik. Ini catur biasa, tidak ada
     TOPSIS.
   - **Tanpa Stockfish (cadangan):** langkah yang langsung skakmat bila ada, kalau tidak tangkapan paling
     menguntungkan, kalau tidak langkah pertama menurut urutan UCI.
3. Ronde baru dibuat dengan posisi hasil balasan; seluruh jejak (usulan, nilai, TOPSIS, Borda, pemenang,
   balasan) disimpan di tabel `konsensus`.
4. Permainan berakhir bila skakmat, pat, atau remis (`mesin.status_akhir`).

## 7. Aturan anggota dan pertandingan

| Kejadian | Akibat |
|---|---|
| Pemain keluar saat ronde berjalan | usulannya dibuang; penilaian yang sudah dibuat dibuang dan dibuat ulang bila semua yang tersisa sudah mengusulkan |
| Pemain baru bergabung di tengah ronde | penilaian lama dibuang; ronde menunggu usulannya |
| Ketua keluar | anggota yang bergabung paling awal menjadi Ketua |
| Tidak ada pemain tersisa (keluar, logout, atau diam 120 detik) | pertandingan berstatus `selesai` |

Semuanya lewat satu fungsi, `app.setelah_perubahan_anggota`, jadi aturannya konsisten untuk semua jalur.
