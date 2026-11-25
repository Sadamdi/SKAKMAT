# Panduan Pengguna SKAKMAT

Tutorial dari nol sampai bermain bertiga. Tidak perlu paham pemrograman.

## 1. Pilih cara membuka aplikasi

| Situasi | Cara |
|---|---|
| Hanya ikut main (teman) | Buka alamat `https://....trycloudflare.com` dari pemilik server di browser mana pun. Tidak perlu memasang apa pun. |
| Pemilik server, ingin teman bisa ikut | Bagian 2 (Cloudflare) |
| Mencoba sendiri di laptop | Bagian 3 (lokal) |
| Dipasang di server/VPS | `docker compose up --build`, lihat [ARSITEKTUR.md](ARSITEKTUR.md) |

## 2. Pemilik: nyalakan server dengan alamat internet sementara

Sekali saja, pasang cloudflared:

```powershell
winget install --id Cloudflare.cloudflared
```

Setiap kali mau main:

```powershell
cd "D:\adam kuliah\Semester 5\Information System Praktikum\UAS\SKAKMAT"
powershell -ExecutionPolicy Bypass -File .\jalankan_online.ps1
```

Skrip mencetak satu alamat dan kata sandi acak tiga akun demo. Bagikan alamatnya. Alamat berubah tiap skrip
dijalankan dan mati saat skrip dihentikan (Ctrl+C). Laptop harus tetap menyala dan terhubung internet.

## 3. Menjalankan di laptop sendiri (lokal)

```powershell
cd "D:\adam kuliah\Semester 5\Information System Praktikum\UAS\SKAKMAT"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app.py
```

Buka http://127.0.0.1:8000. Untuk teman di Wi-Fi yang sama: `.venv\Scripts\python app.py --host 0.0.0.0` lalu
buka `http://<IP-laptop>:8000`. Stockfish opsional; tanpa itu aplikasi tetap jalan dengan lawan sederhana.

Untuk mencoba tiga akun di satu laptop, pakai tiga jendela browser berbeda (biasa, penyamaran, browser lain)
supaya cookie tidak bertabrakan.

## 4. Langkah bermain

### 4.1 Daftar atau masuk
- Klik **Daftar akun baru**: nama pengguna 3 sampai 20 karakter (huruf kecil, angka, garis bawah), nama tampilan,
  kata sandi minimal 6 karakter. Atau masuk dengan akun demo `anggota1`, `anggota2`, `anggota3`.

### 4.2 Lobi: buat atau gabung pertandingan
- **Buat pertandingan:** isi nama, pilih gaya main, klik buat. Kamu otomatis menjadi **Ketua**.
- **Gabung:** pilih gaya (yang masih kosong) pada pertandingan di daftar lalu klik **Gabung**, atau masukkan
  **kode 5 karakter** dari temanmu.
- Maksimal 3 pemain per pertandingan, satu pemain hanya di satu pertandingan, tiap pemain gaya berbeda.

### 4.3 Pilih gaya main
| Gaya | Condong ke |
|---|---|
| Menyerang | peluang serangan (C4 berbobot 30) |
| Seimbang | rata |
| Bertahan | keamanan raja dan materi (C1 dan C2 berbobot 30) |

Gaya menentukan bobot TOPSIS milikmu. Gaya yang berbeda membuat peringkat tiap anggota berbeda, dan itulah yang
digabung Borda.

### 4.4 Usulkan langkah (kamu memegang bidak putih)
1. Klik bidak putih, petak tujuan yang sah ditandai.
2. Klik petak tujuan (atau seret bidak). Usulanmu terkirim.
3. Boleh mengganti usulan selama anggota lain belum semua mengusulkan. Usulan anggota lain belum terlihat.
4. Keyboard: Tab ke bidak, Enter, Tab ke tujuan, Enter, Esc untuk batal.

### 4.5 Penilaian individual
Begitu semua anggota mengusulkan, muncul otomatis: nilai C1 sampai C5 tiap usulan dan satu tabel TOPSIS per
anggota (siapa memilih apa menurut gayanya). Usulan terkunci.

### 4.6 Konsensus (hanya Ketua)
Ketua menekan **Jalankan konsensus (voting Borda)**. Anggota lain melihat "menunggu Ketua". Setelah itu semua
orang melihat tabel Borda, animasi poin, langkah pemenang, dan balasan lawan. Ronde berikutnya langsung dibuka.

### 4.7 Keluar dan bergabung lagi
- **Keluar dari pertandingan** (kembali ke lobi) atau **Keluar** (akun). Yang keluar tidak ditunggu.
- Ketua keluar: anggota paling awal menjadi Ketua.
- Semua keluar: pertandingan **berakhir otomatis**.
- Diam (tidak ada aktivitas) 2 menit dianggap keluar. Jangan biarkan tab tersembunyi terlalu lama.

## 5. Contoh satu ronde

Tiga pemain, Ketua = A1 (Menyerang), A2 (Seimbang), A3 (Bertahan).
1. A1 mengusulkan d4, A2 d3, A3 O-O.
2. Penilaian muncul: Menyerang dan Seimbang memeringkat d4 pertama, Bertahan memeringkat d3 pertama.
3. A1 menekan konsensus. Borda: d4 4,3194, d3 3,7491, O-O 1,0693. d4 menang.
4. d4 dimainkan, Stockfish membalas exd4, ronde 2 dimulai.

## 6. Masalah umum

| Gejala | Penyebab dan solusi |
|---|---|
| "Gaya ... sudah dipakai" | pilih gaya lain yang tersisa |
| "Anda masih berada di sebuah pertandingan" | keluar dulu dari pertandingan sebelumnya |
| Tiba-tiba kembali ke lobi | diam lebih dari 2 menit (tab tersembunyi). Gabung lagi |
| Tombol konsensus tidak ada | hanya Ketua yang punya |
| Alamat tidak bisa dibuka | skrip pemilik sudah berhenti atau alamat berubah. Minta alamat baru |
| "Penilaian otomatis tidak bisa dijalankan" | python-chess tidak terpasang di server |
| Lawan terasa lemah | Stockfish tidak ditemukan; set `SKAKMAT_STOCKFISH=<lokasi>` |
| Ingin mengulang dari awal | hapus `skakmat.db` (server mati dulu), atau tombol **Ronde baru** |

## 7. Untuk dosen/penilai: cara memverifikasi

```powershell
.venv\Scripts\python test_gdss.py
.venv\Scripts\python test_mesin.py
.venv\Scripts\python test_e2e.py
```

Hasil yang diharapkan: semua lolos (e2e 113 pemeriksaan, mesin 48 bila Stockfish ada). Bukti hitungan Borda yang
dicocokkan dengan hitungan independen ada di [CARA_KERJA.md](CARA_KERJA.md).
