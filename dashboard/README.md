# Kartu Risiko Pi

Dashboard statis untuk penilaian risiko dan tanya jawab. Antarmuka menyediakan formulir 12 nilai, kartu hasil, tanya jawab, dan pengaturan koneksi Raspberry Pi. Font, ikon, dan skrip disajikan dari build lokal.

## Jalankan di laptop

Dengan Node.js 20.3 atau lebih baru, jalankan perintah berikut dari folder proyek:

```powershell
npm.cmd run build
npm.cmd start
```

Buka `http://127.0.0.1:4173/` di Edge atau Chrome. Build dan server tidak memerlukan instalasi paket. Gunakan `Ctrl+C` untuk menghentikan server jika dijalankan di terminal. `PROTOTYPE_PORT` mengatur port jika port standar sedang dipakai.

Mode demo terbuka dengan data contoh yang memiliki dua nilai opsional kosong. Pilih skenario **Risiko rendah**, **Data opsional kosong**, atau **Peringatan tekanan darah**, lalu tekan **Isi contoh** dan **Hitung risiko**. Untuk hasil berdasarkan nilai lain, gunakan API Raspberry Pi.

## Hubungkan Raspberry Pi

1. Di **Pengaturan**, pilih **Raspberry Pi**, isi alamat API lokal dan bearer token, lalu tekan **Tes koneksi**. Jika dashboard disajikan langsung oleh FastAPI di port `8000`, alamat default mengikuti origin halaman; alamat `192.168.50.2:8000` hanya fallback untuk server pengembangan.
2. Dashboard membaca `/v1/health` dan `/v1/meta` untuk menentukan kesiapan penilaian dan tanya jawab. Kartu, peringatan, dan persentase berasal dari respons API. Chat mengirim `session_id` dan `message` melalui endpoint milik penilaian tersebut.
3. Jika dashboard berjalan pada laptop dan IP Pi berbeda, konfigurasi CORS FastAPI untuk origin persis `http://127.0.0.1:4173`. Izinkan `GET`, `POST`, dan header `Authorization`, `Content-Type`, serta `X-Client-Version`. Ekspos `Retry-After` dan `X-Request-ID` jika API menggunakannya.

Untuk deploy satu origin di jaringan offline, salin isi `dist/` ke Pi dan sajikan di `/` melalui FastAPI. Daftarkan route `/v1/...` sebelum memasang direktori statis pada `/`. Buka `http://<IP-Pi>:8000/` dan gunakan alamat yang sama untuk Base URL di Pengaturan. Node.js hanya diperlukan untuk build dan server demo lokal. Pi dapat menyajikan `dist/` langsung melalui FastAPI.

Dashboard menyimpan alamat dan pilihan mode di browser. Token, isian kesehatan, kartu, serta percakapan berada dalam memori tab. Setelah memuat ulang halaman, masukkan token lagi untuk mode Raspberry Pi.

## Pengujian

```powershell
npm.cmd test
```

Pengujian browser opsional memakai Microsoft Edge yang sudah terpasang. Jalankan `npm.cmd ci` sekali untuk memasang Playwright Core, jalankan server lokal, lalu jalankan `npm.cmd run test:e2e` dari terminal lain. Hasil tangkapan layar disimpan di `test-results/`. Tes browser memblokir permintaan eksternal dan memakai respons API tiruan untuk memeriksa integrasi kontrak.
