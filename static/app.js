"use strict";
// Semua teks dari server dimasukkan lewat textContent, tidak pernah innerHTML.

const $ = (id) => document.getElementById(id);
const el = (tag, kelas, teks) => {
  const e = document.createElement(tag);
  if (kelas) e.className = kelas;
  if (teks !== undefined) e.textContent = teks;
  return e;
};
const f = (x, k = 4) => Number(x).toFixed(k).replace(".", ",");

const BIDAK = { K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙", k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
let data = null;
let tandaForm = "";

async function api(path, body) {
  const opsi = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const r = await fetch(path, opsi);
  let j = {};
  try { j = await r.json(); } catch (e) { /* abaikan */ }
  if (!r.ok) {
    const err = new Error(j.galat || "Terjadi kesalahan.");
    err.status = r.status;
    throw err;
  }
  return j;
}

function pesan(teks, galat) {
  const p = $("pesan");
  p.textContent = teks;
  p.className = "pesan" + (galat ? " galat" : "");
  if (!teks) p.classList.add("sembunyi");
}

function gambarPapan(fen) {
  const papan = $("papan");
  papan.replaceChildren();
  const baris = fen.split(" ")[0].split("/");
  baris.forEach((b, r) => {
    let c = 0;
    for (const ch of b) {
      if (/\d/.test(ch)) {
        for (let i = 0; i < Number(ch); i++) papan.append(petak(r, c++, ""));
      } else {
        papan.append(petak(r, c++, ch));
      }
    }
  });
  $("giliran").textContent = "Giliran: " + (fen.split(" ")[1] === "w" ? "putih" : "hitam");
}
function petak(r, c, ch) {
  const e = el("div", "petak " + ((r + c) % 2 === 0 ? "t" : "g"));
  if (ch) {
    e.textContent = BIDAK[ch] || "";
    e.classList.add(ch === ch.toUpperCase() ? "putih" : "hitam");
    e.setAttribute("aria-label", ch);
  }
  return e;
}

function tabel(t, kepala, baris, kelasBaris) {
  t.replaceChildren();
  const th = el("tr");
  kepala.forEach((h, i) => th.append(el("th", i === 0 ? "kiri" : "", h)));
  t.append(th);
  baris.forEach((b, idx) => {
    const tr = el("tr", kelasBaris && kelasBaris(idx));
    b.forEach((v, i) => tr.append(el("td", i === 0 ? "kiri" : "", v)));
    t.append(tr);
  });
}

function formNilai() {
  const t = $("tabelNilai");
  t.replaceChildren();
  const kep = el("tr");
  kep.append(el("th", "kiri", "Kandidat"));
  data.kriteria.forEach((k) => kep.append(el("th", "", `${k.kode} ${k.nama} (${k.bobot}%, ${k.jenis})`)));
  t.append(kep);
  data.kasus.kandidat.forEach((nama, i) => {
    const tr = el("tr");
    tr.append(el("td", "kiri", nama));
    data.kriteria.forEach((k, j) => {
      const td = el("td");
      const s = el("select");
      s.id = `n_${i}_${j}`;
      s.setAttribute("aria-label", `${nama} - ${k.nama}`);
      for (let v = 1; v <= 5; v++) s.append(new Option(String(v), String(v)));
      s.value = data.skor_saya ? String(data.skor_saya[i][j]) : "3";
      s.disabled = !!data.konsensus;
      td.append(s);
      tr.append(td);
    });
    t.append(tr);
  });
  $("btnKirim").disabled = !!data.konsensus;
  $("infoKirim").textContent = data.konsensus ? "Penilaian dikunci karena konsensus sudah dijalankan."
    : (data.skor_saya ? "Anda sudah mengirim penilaian." : "Anda belum mengirim penilaian.");
}

function tabelTopsis(t, hasil, kandidat) {
  tabel(t, ["Kandidat", "D+", "D−", "Skor preferensi (V)", "Peringkat"],
    kandidat.map((n, i) => [n, f(hasil.d_plus[i]), f(hasil.d_min[i]), f(hasil.v[i]), String(hasil.rank[i])]),
    (i) => (hasil.rank[i] === 1 ? "menang" : ""));
}

function render() {
  const { pengguna, kasus } = data;
  $("namaAkun").textContent = `${pengguna.nama}${pengguna.tingkat === 1 ? " (jabatan tertinggi)" : ""}`;
  $("judulKasus").textContent = kasus.judul;
  gambarPapan(kasus.fen);
  $("riwayat").textContent = kasus.riwayat || "(belum ada langkah)";
  const ol = $("kandidat");
  ol.replaceChildren();
  kasus.kandidat.forEach((k) => ol.append(el("li", "", k)));
  const st = $("status");
  st.replaceChildren();
  data.status.forEach((s) => {
    const li = el("li");
    li.append(el("span", "", s.nama));
    li.append(el("span", s.sudah ? "ok" : "tunggu", s.sudah ? "sudah menilai" : "belum menilai"));
    st.append(li);
  });
  // Form nilai hanya digambar ulang bila kasus, penilaian tersimpan, atau status konsensus berubah,
  // supaya pilihan yang belum dikirim tidak tertimpa oleh penyegaran berkala.
  const tanda = JSON.stringify([kasus.id, data.skor_saya, !!data.konsensus]);
  if (tanda !== tandaForm) { formNilai(); tandaForm = tanda; }

  const saya = !!data.topsis_saya;
  $("kartuSaya").classList.toggle("sembunyi", !saya);
  if (saya) tabelTopsis($("tabelSaya"), data.topsis_saya, kasus.kandidat);

  const kapten = pengguna.tingkat === 1;
  $("kartuKapten").classList.toggle("sembunyi", !kapten);
  $("btnKonsensus").disabled = !data.semua_sudah || !!data.konsensus;

  const k = data.konsensus;
  $("belumKonsensus").classList.toggle("sembunyi", !!k);
  $("hasilKonsensus").classList.toggle("sembunyi", !k);
  if (k) {
    $("pemenang").textContent = `Langkah terpilih: ${k.pemenang}  (dijalankan oleh ${k.dijalankan_oleh})`;
    const b = k.borda;
    tabel($("tabelBorda"), ["Kandidat", "Poin Borda", "Nilai Borda", "Peringkat"],
      kasus.kandidat.map((n, i) => [n, f(b.poin[i]), f(b.nilai[i]), String(b.rank[i])]),
      (i) => (b.rank[i] === 1 ? "menang" : ""));
    const wadah = $("semuaIndividual");
    wadah.replaceChildren();
    (data.individual || []).forEach((ind) => {
      const blok = el("div", "blok-individual");
      blok.append(el("h4", "", ind.nama));
      const t = el("table");
      tabelTopsis(t, ind.topsis, kasus.kandidat);
      const gulir = el("div", "gulir");
      gulir.append(t);
      blok.append(gulir);
      wadah.append(blok);
    });
  }
}

async function muat() {
  try {
    data = await api("/api/kasus");
    $("viewLogin").classList.add("sembunyi");
    $("viewApp").classList.remove("sembunyi");
    $("akun").classList.remove("sembunyi");
    render();
  } catch (e) {
    if (e.status === 401) return tampilLogin();
    pesan(e.message, true);
  }
}
function tampilLogin() {
  data = null;
  tandaForm = "";
  $("viewApp").classList.add("sembunyi");
  $("akun").classList.add("sembunyi");
  $("viewLogin").classList.remove("sembunyi");
}

$("formLogin").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  $("galatLogin").textContent = "";
  try {
    await api("/api/login", { username: $("inUser").value.trim(), sandi: $("inSandi").value });
    $("inSandi").value = "";
    await muat();
  } catch (e) { $("galatLogin").textContent = e.message; }
});
$("btnKeluar").addEventListener("click", async () => { await api("/api/keluar", {}); tampilLogin(); });

$("btnKirim").addEventListener("click", async () => {
  const skor = data.kasus.kandidat.map((_, i) => data.kriteria.map((__, j) => Number($(`n_${i}_${j}`).value)));
  try {
    await api("/api/nilai", { skor });
    pesan("Penilaian tersimpan.", false);
    await muat();
  } catch (e) { pesan(e.message, true); }
});
$("btnKonsensus").addEventListener("click", async () => {
  try {
    await api("/api/konsensus", {});
    pesan("Konsensus Borda selesai dijalankan.", false);
    await muat();
  } catch (e) { pesan(e.message, true); }
});
$("btnUlang").addEventListener("click", async () => {
  if (!confirm("Hapus semua penilaian dan hasil konsensus pada kasus ini?")) return;
  try { await api("/api/ulang", {}); pesan("Putaran penilaian diulang.", false); await muat(); }
  catch (e) { pesan(e.message, true); }
});
$("formKasus").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    await api("/api/kasus-baru", {
      judul: $("kJudul").value, fen: $("kFen").value, riwayat: $("kRiwayat").value,
      kandidat: [$("kK1").value, $("kK2").value, $("kK3").value],
    });
    $("formKasus").reset();
    pesan("Kasus baru dibuat.", false);
    await muat();
  } catch (e) { pesan(e.message, true); }
});

// Penyegaran berkala agar status penilaian dan hasil konsensus muncul tanpa muat ulang halaman.
setInterval(() => {
  const aktif = document.activeElement;
  if (data && !(aktif && aktif.tagName === "SELECT")) muat();
}, 8000);
muat();
