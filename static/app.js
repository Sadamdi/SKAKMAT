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

// Glyph solid untuk kedua warna; warna bidak dibedakan lewat CSS. U+FE0E memaksa tampilan teks, bukan emoji.
const GLYPH = { k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
const NAMA_BIDAK = { k: "raja", q: "menteri", r: "benteng", b: "gajah", n: "kuda", p: "pion" };
let data = null;
let tandaForm = "";

async function api(path, body, signal) {
  const opsi = body === undefined ? { signal } : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal,
  };
  let r;
  try {
    r = await fetch(path, opsi);
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new Error("Tidak dapat menghubungi server. Periksa koneksi lalu coba lagi.");
  }
  let j = {};
  try { j = await r.json(); } catch (e) { /* abaikan */ }
  if (!r.ok) {
    const err = new Error(j.galat || "Terjadi kesalahan.");
    err.status = r.status;
    throw err;
  }
  return j;
}

// Wadah pesan selalu ada di DOM (role="status"/"alert"); bila kosong disembunyikan lewat CSS :empty.
function pesan(teks, galat, id = "pesan") {
  const p = $(id);
  p.textContent = teks || "";
  p.classList.toggle("galat", !!galat);
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
  const kecil = ch.toLowerCase();
  if (ch && GLYPH[kecil]) {
    const putih = ch !== kecil;
    e.textContent = GLYPH[kecil] + "\uFE0E";
    e.classList.add(putih ? "putih" : "hitam");
    e.setAttribute("role", "img");
    e.setAttribute("aria-label", `${"abcdefgh"[c]}${8 - r}: ${NAMA_BIDAK[kecil]} ${putih ? "putih" : "hitam"}`);
  } else {
    e.setAttribute("aria-hidden", "true");
  }
  return e;
}

// Tabel dengan caption (tersembunyi visual), scope kolom/baris, dan aria-label.
function tabel(t, judul, kepala, baris, kelasBaris) {
  t.replaceChildren();
  t.setAttribute("aria-label", judul);
  t.append(el("caption", "sr", judul));
  const thead = el("thead");
  const th = el("tr");
  kepala.forEach((h, i) => {
    const c = el("th", i === 0 ? "kiri" : "", h);
    c.scope = "col";
    th.append(c);
  });
  thead.append(th);
  const tbody = el("tbody");
  baris.forEach((b, idx) => {
    const tr = el("tr", kelasBaris && kelasBaris(idx));
    b.forEach((v, i) => {
      const c = el(i === 0 ? "th" : "td", i === 0 ? "kiri" : "", v);
      if (i === 0) c.scope = "row";
      tr.append(c);
    });
    tbody.append(tr);
  });
  t.append(thead, tbody);
}

// Label skala 1..5; untuk kriteria cost nilai besar berarti risiko besar (buruk).
const SKALA = {
  benefit: ["sangat buruk", "buruk", "cukup", "baik", "sangat baik"],
  cost: ["risiko sangat kecil", "risiko kecil", "risiko sedang", "risiko besar", "risiko sangat besar"],
};
const KET_COST = "cost: makin besar makin berisiko";

function formNilai() {
  const t = $("tabelNilai");
  const judul = "Formulir penilaian kandidat langkah pada lima kriteria, skala 1 sampai 5";
  t.replaceChildren();
  t.setAttribute("aria-label", judul);
  t.append(el("caption", "sr", judul));
  const kep = el("tr");
  const thK = el("th", "kiri", "Kandidat");
  thK.scope = "col";
  kep.append(thK);
  data.kriteria.forEach((k) => {
    const cost = k.jenis === "cost";
    const th = el("th", cost ? "cost" : "");
    th.scope = "col";
    th.append(el("span", "kode", `${k.kode} ${k.nama}`));
    th.append(el("span", "bobot", `bobot ${k.bobot}% · ${cost ? KET_COST : "benefit"}`));
    kep.append(th);
  });
  const thead = el("thead");
  thead.append(kep);
  const tbody = el("tbody");
  data.kasus.kandidat.forEach((nama, i) => {
    const tr = el("tr");
    const thNama = el("th", "kiri", nama);
    thNama.scope = "row";
    tr.append(thNama);
    data.kriteria.forEach((k, j) => {
      const cost = k.jenis === "cost";
      const td = el("td", cost ? "cost" : "");
      // data-label dipakai CSS untuk tampilan kartu di layar sempit.
      td.dataset.label = `${k.kode} ${k.nama}${cost ? ` (${KET_COST})` : ""}`;
      const s = el("select");
      s.id = `n_${i}_${j}`;
      s.setAttribute("aria-label", `${nama}, ${k.kode} ${k.nama}${cost ? `, ${KET_COST}` : ""}`);
      SKALA[cost ? "cost" : "benefit"].forEach((ket, v) => s.append(new Option(`${v + 1} – ${ket}`, String(v + 1))));
      s.value = data.skor_saya ? String(data.skor_saya[i][j]) : "3";
      s.disabled = !!data.konsensus;
      td.append(s);
      tr.append(td);
    });
    tbody.append(tr);
  });
  t.append(thead, tbody);
  infoKirim(false);
}

function infoKirim(berubah) {
  $("infoKirim").textContent = data.konsensus ? "Penilaian dikunci karena konsensus sudah dijalankan."
    : berubah ? "Ada perubahan yang belum dikirim."
      : (data.skor_saya ? "Anda sudah mengirim penilaian." : "Anda belum mengirim penilaian.");
}

function tabelTopsis(t, judul, hasil, kandidat) {
  tabel(t, judul, ["Kandidat", "D+", "D−", "Skor preferensi (V)", "Peringkat"],
    kandidat.map((n, i) => [n, f(hasil.d_plus[i]), f(hasil.d_min[i]), f(hasil.v[i]), String(hasil.rank[i])]),
    (i) => (hasil.rank[i] === 1 ? "menang" : ""));
}

// Status tombol dihitung terpisah dari render agar bisa dipulihkan setelah permintaan selesai.
function aturTombol() {
  if (!data) return;
  $("btnKirim").disabled = !!data.konsensus;
  $("btnKonsensus").disabled = !data.semua_sudah || !!data.konsensus;
}

// ------------------------------------------------------------------ identitas decision maker
// Setiap decision maker mendapat warna aksen + inisial yang sama di seluruh halaman.
// Kunci = tingkat jabatan (ada di status, individual, dan pengguna). Jumlah orang tidak di-hardcode:
// urutan diambil dari data.status, warna berputar bila lebih dari empat.
const JUMLAH_WARNA = 4;
function inisial(nama) {
  return String(nama).trim().split(/\s+/).map((w) => (/^\d+$/.test(w) ? w : w.charAt(0).toUpperCase())).join("").slice(0, 3);
}
function identitas(orang) {
  const urut = data.status.findIndex((s) => s.tingkat === orang.tingkat);
  const i = urut < 0 ? 0 : urut;
  return { kelas: `dm-${(i % JUMLAH_WARNA) + 1}`, inisial: inisial(orang.nama), koordinator: orang.tingkat === 1 };
}
// Lencana: lingkaran berwarna (koordinator: kotak membulat) berisi inisial. Dekoratif bagi pembaca layar
// karena nama selalu ditulis di sebelahnya.
function lencana(orang) {
  const id = identitas(orang);
  const e = el("span", `lencana ${id.kelas}${id.koordinator ? " koord" : ""}`, id.inisial);
  e.setAttribute("aria-hidden", "true");
  return e;
}
function tagPeran(orang) {
  return orang.tingkat === 1 ? el("span", "tag-peran", "koordinator") : null;
}
// Lencana + nama (+ tag koordinator) sebagai satu kesatuan.
function namaDm(orang, tambahan = "") {
  const w = el("span", `nama-dm ${identitas(orang).kelas}`);
  w.append(lencana(orang), el("span", "", orang.nama + tambahan));
  const t = tagPeran(orang);
  if (t) w.append(t);
  return w;
}

function renderStatus() {
  const st = $("status");
  st.replaceChildren();
  data.status.forEach((s) => {
    const li = el("li", identitas(s).kelas);
    li.append(namaDm(s, s.id === data.pengguna.id ? " (Anda · perangkat ini)" : ""));
    li.append(el("span", s.sudah ? "ok" : "tunggu", s.sudah ? "✓ sudah menilai" : "○ belum menilai"));
    st.append(li);
  });
  const belumOrang = data.status.filter((s) => !s.sudah);
  const belum = belumOrang.map((s) => s.nama);
  const rs = $("ringkasStatus");
  if (data.konsensus) rs.textContent = "Konsensus sudah dijalankan; penilaian dikunci.";
  else if (belum.length) {
    rs.replaceChildren("Menunggu penilaian dari: ");
    belumOrang.forEach((s, i) => {
      if (i) rs.append(", ");
      rs.append(namaDm(s));
    });
    rs.append(".");
  } else rs.textContent = `Semua ${data.status.length} decision maker sudah menilai.`;
  rs.classList.toggle("tunggu-kotak", !data.konsensus && belum.length > 0);
  $("infoKonsensus").textContent = data.konsensus ? "Konsensus untuk kasus ini sudah dijalankan."
    : belum.length ? `Tombol konsensus aktif setelah semua menilai. Belum menilai: ${belum.join(", ")}.`
      : "Semua sudah menilai. Konsensus siap dijalankan.";
}

function render() {
  const { pengguna, kasus } = data;
  $("namaAkun").textContent = `${pengguna.nama}${pengguna.tingkat === 1 ? " (koordinator)" : ""}`;
  $("lencanaAkun").replaceChildren(lencana(pengguna));
  $("judulKasus").textContent = kasus.judul;
  // Satu tim, satu sisi papan: sisi tim = pihak yang berjalan menurut FEN.
  const sisi = kasus.fen.split(" ")[1] === "w" ? "putih" : "hitam";
  $("tim").textContent = `Satu tim memainkan bidak ${sisi}. ${data.status.length} decision maker menilai dari perangkat masing-masing; `
    + "Kapten ikut menilai dan menjadi koordinator yang menjalankan konsensus.";
  gambarPapan(kasus.fen);
  $("riwayat").textContent = kasus.riwayat || "(belum ada langkah)";
  const ol = $("kandidat");
  ol.replaceChildren();
  kasus.kandidat.forEach((k) => ol.append(el("li", "", k)));
  renderStatus();
  // Form nilai hanya digambar ulang bila kasus, penilaian tersimpan, atau status konsensus berubah,
  // supaya pilihan yang belum dikirim tidak tertimpa oleh penyegaran berkala.
  const tanda = JSON.stringify([kasus.id, data.skor_saya, !!data.konsensus]);
  if (tanda !== tandaForm) { formNilai(); tandaForm = tanda; }

  const saya = !!data.topsis_saya;
  $("kartuSaya").classList.toggle("sembunyi", !saya);
  if (saya) tabelTopsis($("tabelSaya"), "Hasil TOPSIS penilaian Anda", data.topsis_saya, kasus.kandidat);

  const kapten = pengguna.tingkat === 1;
  $("kartuKapten").classList.toggle("sembunyi", !kapten);
  aturTombol();

  const k = data.konsensus;
  $("belumKonsensus").classList.toggle("sembunyi", !!k);
  $("hasilKonsensus").classList.toggle("sembunyi", !k);
  if (k) {
    const p = $("pemenang");
    p.replaceChildren("Langkah terpilih: ", el("strong", "", k.pemenang), ` (dijalankan oleh ${k.dijalankan_oleh})`);
    const b = k.borda;
    tabel($("tabelBorda"), "Hasil voting Borda kelompok", ["Kandidat", "Poin Borda", "Nilai Borda", "Peringkat"],
      kasus.kandidat.map((n, i) => [n, f(b.poin[i]), f(b.nilai[i]), String(b.rank[i])]),
      (i) => (b.rank[i] === 1 ? "menang" : ""));
    const wadah = $("semuaIndividual");
    wadah.replaceChildren();
    (data.individual || []).forEach((ind) => {
      const blok = el("div", `blok-individual ${identitas(ind).kelas}`);
      const h = el("h4");
      h.append(namaDm(ind));
      blok.append(h);
      const t = el("table");
      tabelTopsis(t, `Hasil TOPSIS ${ind.nama}`, ind.topsis, kasus.kandidat);
      const gulir = el("div", "gulir");
      gulir.append(t);
      blok.append(gulir);
      wadah.append(blok);
    });
    renderAnimasi(k);
  } else {
    hentikanAnimasi();
    tandaAnimasi = "";
  }
  renderEngine();
}

// ------------------------------------------------------------------ animasi penggabungan Borda
// Yang dianimasikan hanyalah penjumlahan: poin Borda tiap penilai (bobot peringkat × V) ditumpuk per
// kandidat, satu penilai per langkah, lalu kandidat dengan total terbesar ditandai. Tidak ada analisis
// posisi di sini. Hasil akhir (teks pemenang + tabel Borda di atas) sudah tampil sebelum animasi mulai.
const JEDA_LANGKAH = 350;
const gerakDikurangi = matchMedia("(prefers-reduced-motion: reduce)");
let tandaAnimasi = "";
let pewaktu = [];
let modelAnimasi = null;

function hentikanAnimasi() {
  pewaktu.forEach(clearTimeout);
  pewaktu = [];
}

// Hitung sumbangan poin tiap penilai dari data yang sudah dikirim server (rank, V, bobot Borda).
// Bila jumlahnya tidak sama dengan poin Borda dari server, animasi tidak ditampilkan.
function hitungSumbangan(k) {
  const ind = data.individual || [];
  const b = k.borda;
  const n = data.kasus.kandidat.length;
  if (!ind.length || !b.bobot_borda) return null;
  const sumbangan = ind.map((o) => data.kasus.kandidat.map((_, i) => b.bobot_borda[o.topsis.rank[i] - 1] * o.topsis.v[i]));
  for (let i = 0; i < n; i++) {
    const total = sumbangan.reduce((a, s) => a + s[i], 0);
    if (Math.abs(total - b.poin[i]) > 1e-9) return null;
  }
  return { ind, sumbangan, maks: Math.max(...b.poin) || 1 };
}

function renderAnimasi(k) {
  const tanda = JSON.stringify([data.kasus.id, k.borda.poin]);
  if (tanda === tandaAnimasi) return;
  tandaAnimasi = tanda;
  hentikanAnimasi();
  const m = hitungSumbangan(k);
  modelAnimasi = m;
  $("animasi").classList.toggle("sembunyi", !m);
  if (!m) return;
  const kandidat = data.kasus.kandidat;
  const b = k.borda;
  $("judulAnimasi").textContent = `Bagaimana ${m.ind.length} peringkat individual digabung`;
  $("ketAnimasi").textContent = `Tiap penilai menyumbang poin ke setiap kandidat: bobot peringkatnya (${b.bobot_borda.join(", ")} untuk peringkat 1, 2, 3) `
    + "dikali skor preferensi V dari TOPSIS-nya. Poin dari semua penilai dijumlahkan; kandidat dengan total terbesar menjadi keputusan kelompok.";

  // Batang bertumpuk per kandidat; satu segmen per penilai, warna = identitas penilai.
  const batang = $("batang");
  batang.replaceChildren();
  kandidat.forEach((nama, i) => {
    const baris = el("div", "batang-baris");
    baris.dataset.kandidat = String(i);
    baris.append(el("span", "batang-nama", nama));
    const jalur = el("div", "batang-jalur");
    m.ind.forEach((o, d) => {
      const seg = el("span", `segmen ${identitas(o).kelas}`);
      seg.dataset.penilai = String(d);
      const lebar = (m.sumbangan[d][i] / m.maks) * 100;
      seg.dataset.lebar = lebar.toFixed(3);
      if (lebar >= 9) seg.textContent = identitas(o).inisial;
      jalur.append(seg);
    });
    baris.append(jalur, el("span", "batang-total", f(0)));
    batang.append(baris);
  });

  // Tabel peringkat individual: dari mana poin tiap kandidat berasal.
  tabel($("tabelPeringkat"), "Sumbangan poin Borda tiap penilai per kandidat",
    ["Penilai", ...kandidat],
    [...m.ind.map((o, d) => [o.nama, ...kandidat.map((_, i) => `#${o.topsis.rank[i]} → ${b.bobot_borda[o.topsis.rank[i] - 1]} × ${f(o.topsis.v[i])} = ${f(m.sumbangan[d][i])}`)]),
      ["Total poin", ...kandidat.map((_, i) => f(b.poin[i]))]],
    (r) => (r === m.ind.length ? "total" : identitas(m.ind[r]).kelas));
  // Lencana di kolom penilai.
  $("tabelPeringkat").querySelectorAll("tbody tr").forEach((tr, r) => {
    if (r < m.ind.length) tr.firstChild.replaceChildren(namaDm(m.ind[r]));
  });
  putarAnimasi();
}

function setLangkah(d) {
  // d = jumlah penilai yang sudah ditumpuk (0..n); d = n+1 berarti pemenang ditandai.
  const m = modelAnimasi;
  const b = data.konsensus.borda;
  const n = m.ind.length;
  $("batang").querySelectorAll(".batang-baris").forEach((baris) => {
    const i = Number(baris.dataset.kandidat);
    let total = 0;
    baris.querySelectorAll(".segmen").forEach((seg) => {
      const p = Number(seg.dataset.penilai);
      const tampil = p < d;
      seg.style.width = tampil ? seg.dataset.lebar + "%" : "0%";
      seg.classList.toggle("baru", p === d - 1 && d <= n);
      if (tampil) total += m.sumbangan[p][i];
    });
    baris.querySelector(".batang-total").textContent = f(d > n ? b.poin[i] : total);
    baris.classList.toggle("menang", d > n && b.rank[i] === 1);
  });
  $("tabelPeringkat").querySelectorAll("tbody tr").forEach((tr, r) => {
    tr.classList.toggle("aktif", r === d - 1 && d <= n);
  });
  $("langkahAnim").textContent = d === 0 ? "Mulai dari nol poin."
    : d <= n ? `Menambahkan poin dari ${m.ind[d - 1].nama} (${d} dari ${n} penilai).`
      : `Semua poin terkumpul. Keputusan kelompok: ${data.konsensus.pemenang}.`;
}

function putarAnimasi() {
  hentikanAnimasi();
  if (!modelAnimasi) return;
  const n = modelAnimasi.ind.length;
  const diam = gerakDikurangi.matches;
  $("btnPutar").classList.toggle("sembunyi", diam);
  if (diam) return setLangkah(n + 1);   // kurangi gerakan: langsung hasil akhir
  setLangkah(0);
  for (let d = 1; d <= n + 1; d++) pewaktu.push(setTimeout(() => setLangkah(d), d * JEDA_LANGKAH));
}

// ------------------------------------------------------------------ pembanding engine
// Engine hanya pembanding, bukan kriteria: nilainya tidak ikut TOPSIS maupun Borda.
// Bila server tidak mengirim field `engine` atau engine tidak tersedia, tampilkan status jujur tanpa angka.
const SELISIH_TIPIS = 20;   // centipawn (0,2 pion): di bawah ini dua langkah dianggap praktis setara

// Nilai engine dari sudut pandang tim (pihak yang berjalan).
function nilaiEngine(x) {
  if (x.mat !== null && x.mat !== undefined) return x.mat > 0 ? `mat dalam ${x.mat}` : `dimat dalam ${-x.mat}`;
  const pion = x.cp / 100;
  return (pion > 0 ? "+" : pion < 0 ? "−" : "±") + Math.abs(pion).toFixed(2).replace(".", ",");
}
// Selisih dalam centipawn; null bila salah satu bernilai mat (tidak bisa dikurangkan secara bermakna).
const selisihCp = (a, b) => (a.cp === null || b.cp === null ? null : Math.abs(a.cp - b.cp));

function renderEngine() {
  const e = data && data.engine;
  const st = $("statusEngine");
  $("wadahEngine").classList.add("sembunyi");
  $("ketEngine").classList.add("sembunyi");
  st.className = "status-engine kosong";
  if (!e) {
    st.textContent = "Pembanding engine belum tersedia. Server belum menyediakan peringkat engine, jadi belum ada yang dibandingkan.";
    return;
  }
  const k = data.konsensus;
  if (!e.tersedia || !k || !Array.isArray(e.kandidat) || e.kandidat.length !== data.kasus.kandidat.length) {
    st.textContent = "Pembanding engine tidak tersedia" + (e.tersedia ? ": data engine tidak lengkap." : e.alasan ? `: ${e.alasan}` : ".");
    return;
  }
  const kandidat = data.kasus.kandidat;
  const iKel = kandidat.indexOf(k.pemenang);
  const kel = e.kandidat[iKel];
  const terbaik = e.kandidat.filter((x) => x.peringkat === 1);
  st.className = "status-engine " + (kel && kel.peringkat === 1 ? "sepakat" : "beda");
  if (kel && kel.peringkat === 1) {
    st.textContent = `Sepakat: langkah pilihan kelompok (${k.pemenang}) juga peringkat 1 menurut engine.`;
  } else {
    const d = kel && terbaik[0] ? selisihCp(kel, terbaik[0]) : null;
    st.textContent = `Berbeda: kelompok memilih ${k.pemenang} (peringkat ${kel ? kel.peringkat : "?"} menurut engine), `
      + `sedangkan engine paling menilai ${terbaik.map((x) => x.langkah).join(" / ")}.`
      + (d === null ? "" : d <= SELISIH_TIPIS
        ? ` Selisih nilainya hanya ${(d / 100).toFixed(2).replace(".", ",")} pion, praktis setara.`
        : ` Selisih nilainya ${(d / 100).toFixed(2).replace(".", ",")} pion.`);
  }
  tabel($("tabelEngine"), "Peringkat kelompok dibandingkan peringkat engine",
    ["Kandidat", "Peringkat kelompok (Borda)", "Peringkat engine", `Nilai engine (pion, sudut ${e.sudut_pandang || "tim"})`, "Perbandingan"],
    kandidat.map((n, i) => {
      const x = e.kandidat[i];
      const sama = x.peringkat === k.borda.rank[i];
      return [n, String(k.borda.rank[i]), String(x.peringkat), nilaiEngine(x), sama ? "= sama" : "≠ berbeda"];
    }),
    (i) => (k.borda.rank[i] === 1 ? "menang" : ""));
  $("tabelEngine").querySelectorAll("tbody tr").forEach((tr) => {
    const sel = tr.lastChild;
    sel.className = sel.textContent.startsWith("=") ? "cocok" : "tidak-cocok";
  });
  $("wadahEngine").classList.remove("sembunyi");
  const ket = $("ketEngine");
  ket.textContent = `Engine hanya pembanding: nilainya tidak ikut dihitung dalam TOPSIS maupun Borda. `
    + `Dianalisis ${e.engine || "engine"}${e.batas ? `, kedalaman ${e.batas.kedalaman}, maksimal ${String(e.batas.waktu_detik).replace(".", ",")} detik` : ""}. `
    + "Nilai positif berarti menguntungkan tim; selisih kecil (di bawah 0,2 pion) praktis setara.";
  ket.classList.remove("sembunyi");
}

// ------------------------------------------------------------------ pemuatan dan penyegaran
const JEDA_SEGAR = 15000;
const SESI_HABIS = "Sesi berakhir, silakan masuk lagi.";
let pengendali = null;   // AbortController untuk /api/kasus yang sedang berjalan (maksimal satu)
let waktuMuat = 0;
let sibuk = 0;           // jumlah aksi pengguna yang sedang dikirim

const jam = (t) => new Date(t).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

function infoSegar(teks) {
  $("infoSegar").textContent = teks !== undefined ? teks : !data ? ""
    : `Diperbarui pukul ${jam(waktuMuat)}. ` + (data.konsensus
      ? "Hasil sudah final; penyegaran otomatis berhenti."
      : `Diperbarui otomatis tiap ${JEDA_SEGAR / 1000} detik.`);
}

// paksa = true membatalkan permintaan yang sedang berjalan (dipakai setelah aksi pengguna);
// penyegaran berkala (paksa = false) dilewati bila masih ada permintaan berjalan.
async function muat(paksa) {
  if (pengendali) {
    if (!paksa) return;
    pengendali.abort();
  }
  const ini = new AbortController();
  pengendali = ini;
  infoSegar("Menyegarkan…");
  $("infoSegar").parentElement.setAttribute("aria-busy", "true");
  try {
    data = await api("/api/kasus", undefined, ini.signal);
    waktuMuat = Date.now();
    tampilApp();
    pesan("");
    render();
  } catch (e) {
    if (e.name === "AbortError") return;
    if (e.status === 401) return tampilLogin(data ? SESI_HABIS : "");
    pesan(e.message, true);
  } finally {
    if (pengendali === ini) {
      pengendali = null;
      $("infoSegar").parentElement.removeAttribute("aria-busy");
      infoSegar();
    }
  }
}

function tampilApp() {
  $("viewMuat").classList.add("sembunyi");
  $("viewLogin").classList.add("sembunyi");
  $("viewApp").classList.remove("sembunyi");
  $("akun").classList.remove("sembunyi");
}
function tampilLogin(info) {
  if (pengendali) { pengendali.abort(); pengendali = null; }
  data = null;
  tandaForm = "";
  $("viewMuat").classList.add("sembunyi");
  $("viewApp").classList.add("sembunyi");
  $("akun").classList.add("sembunyi");
  $("viewLogin").classList.remove("sembunyi");
  $("infoLogin").textContent = info || "";
  if (info) $("inUser").focus();
}

// Galat aksi: sesi habis kembali ke login dengan penjelasan, selain itu tampil di wadah pesan terkait.
function tanganiGalat(e, id) {
  if (e.status === 401) return tampilLogin(SESI_HABIS);
  pesan(e.message, true, id);
}

// Tombol langsung dinonaktifkan dan teksnya berubah selama permintaan, mencegah kirim ganda.
async function kirimDengan(tombol, teksSibuk, kerja) {
  if (tombol.disabled) return;
  const teksAsli = tombol.textContent;
  tombol.disabled = true;
  tombol.textContent = teksSibuk;
  tombol.setAttribute("aria-busy", "true");
  sibuk++;
  try {
    await kerja();
  } finally {
    sibuk--;
    tombol.textContent = teksAsli;
    tombol.disabled = false;
    tombol.removeAttribute("aria-busy");
    aturTombol();
  }
}

// ------------------------------------------------------------------ validasi FEN di sisi klien
// Mencerminkan fen_valid() di app.py, tetapi dengan pesan yang menunjuk letak kesalahan.
// Server tetap menjadi pemeriksa akhir.
function cekFen(fen) {
  const bagian = fen.trim().split(/\s+/);
  if (bagian.length < 2 || !bagian[0]) {
    return "FEN harus berisi minimal dua bagian yang dipisah spasi: susunan bidak dan giliran (w atau b).";
  }
  const baris = bagian[0].split("/");
  if (baris.length !== 8) return `Susunan bidak harus 8 baris yang dipisah "/", bukan ${baris.length} baris.`;
  for (let i = 0; i < 8; i++) {
    let n = 0;
    for (const ch of baris[i]) {
      if (/[1-8]/.test(ch)) n += Number(ch);
      else if ("prnbqkPRNBQK".includes(ch)) n += 1;
      else return `Karakter "${ch}" pada baris ke-${i + 1} tidak dikenal. Pakai huruf bidak (KQRBNP / kqrbnp) atau angka 1–8.`;
    }
    if (n !== 8) return `Baris ke-${i + 1} ("${baris[i]}") berisi ${n} petak; setiap baris harus tepat 8 petak.`;
  }
  if (bagian[1] !== "w" && bagian[1] !== "b") return `Giliran harus "w" (putih) atau "b" (hitam), bukan "${bagian[1]}".`;
  return "";
}

// ------------------------------------------------------------------ peristiwa
$("formLogin").addEventListener("submit", (ev) => {
  ev.preventDefault();
  $("galatLogin").textContent = "";
  kirimDengan($("btnMasuk"), "Memeriksa…", async () => {
    try {
      await api("/api/login", { username: $("inUser").value.trim(), sandi: $("inSandi").value });
      $("inSandi").value = "";
      $("infoLogin").textContent = "";
      await muat(true);
    } catch (e) { $("galatLogin").textContent = e.message; }
  });
});
$("btnKeluar").addEventListener("click", () => kirimDengan($("btnKeluar"), "Keluar…", async () => {
  try {
    await api("/api/keluar", {});
    tampilLogin("");
  } catch (e) {
    if (e.status === 401) tampilLogin("");
    else pesan(e.message, true);
  }
}));
$("btnPutar").addEventListener("click", putarAnimasi);
gerakDikurangi.addEventListener("change", () => { if (modelAnimasi && data && data.konsensus) putarAnimasi(); });
$("btnSegar").addEventListener("click", () => kirimDengan($("btnSegar"), "Menyegarkan…", () => muat(true)));

$("tabelNilai").addEventListener("change", () => { if (data) infoKirim(true); });
$("btnKirim").addEventListener("click", () => kirimDengan($("btnKirim"), "Mengirim…", async () => {
  const skor = data.kasus.kandidat.map((_, i) => data.kriteria.map((__, j) => Number($(`n_${i}_${j}`).value)));
  pesan("", false, "pesanNilai");
  try {
    await api("/api/nilai", { skor });
    pesan(`Penilaian tersimpan pukul ${jam(Date.now())}.`, false, "pesanNilai");
    await muat(true);
  } catch (e) { tanganiGalat(e, "pesanNilai"); }
}));
$("btnKonsensus").addEventListener("click", () => kirimDengan($("btnKonsensus"), "Menjalankan…", async () => {
  pesan("", false, "pesanKapten");
  try {
    await api("/api/konsensus", {});
    pesan("Konsensus Borda selesai dijalankan.", false, "pesanKapten");
    await muat(true);
  } catch (e) { tanganiGalat(e, "pesanKapten"); }
}));
$("btnUlang").addEventListener("click", () => {
  if (!confirm("Hapus semua penilaian dan hasil konsensus pada kasus ini?")) return;
  kirimDengan($("btnUlang"), "Mengulang…", async () => {
    pesan("", false, "pesanKapten");
    try {
      await api("/api/ulang", {});
      pesan("Putaran penilaian diulang. Semua decision maker perlu menilai lagi.", false, "pesanKapten");
      await muat(true);
    } catch (e) { tanganiGalat(e, "pesanKapten"); }
  });
});
$("kFen").addEventListener("input", () => {
  $("kFen").removeAttribute("aria-invalid");
  $("galatKasus").textContent = "";
});
$("btnUsul").addEventListener("click", () => {
  const salah = cekFen($("kFen").value);
  $("infoUsul").textContent = "";
  if (salah) {
    $("galatKasus").textContent = "Isi FEN yang sah dulu. " + salah;
    $("kFen").setAttribute("aria-invalid", "true");
    $("kFen").focus();
    return;
  }
  kirimDengan($("btnUsul"), "Meminta usulan…", async () => {
    $("galatKasus").textContent = "";
    try {
      const j = await api("/api/usul-kandidat", { fen: $("kFen").value.trim() });
      ["kK1", "kK2", "kK3"].forEach((id, i) => { $(id).value = j.kandidat[i]; });
      $("infoUsul").textContent = "Kandidat diisi dari usulan engine (urut abjad, bukan peringkat engine). Boleh diubah sebelum disimpan.";
    } catch (e) {
      if (e.status === 401) tampilLogin(SESI_HABIS);
      else $("galatKasus").textContent = e.message;
    }
  });
});
$("formKasus").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const salah = cekFen($("kFen").value);
  if (salah) {
    $("galatKasus").textContent = "FEN ditolak: " + salah;
    $("kFen").setAttribute("aria-invalid", "true");
    $("kFen").focus();
    return;
  }
  kirimDengan($("btnSimpan"), "Menyimpan…", async () => {
    $("galatKasus").textContent = "";
    try {
      const j = await api("/api/kasus-baru", {
        judul: $("kJudul").value, fen: $("kFen").value, riwayat: $("kRiwayat").value,
        kandidat: [$("kK1").value, $("kK2").value, $("kK3").value],
      });
      $("formKasus").reset();
      $("infoUsul").textContent = "";
      pesan("Kasus baru dibuat. Penilaian dimulai dari awal." + (j.peringatan ? ` ${j.peringatan}` : ""), false, "pesanKapten");
      await muat(true);
    } catch (e) {
      if (e.status === 401) return tampilLogin(SESI_HABIS);
      $("galatKasus").textContent = e.message;
      // Pesan server "Kandidat N: ..." menunjuk kolom yang salah; tandai kolom itu.
      const m = /^Kandidat (\d)/.exec(e.message);
      if (m && $(`kK${m[1]}`)) { $(`kK${m[1]}`).setAttribute("aria-invalid", "true"); $(`kK${m[1]}`).focus(); }
    }
  });
});
["kK1", "kK2", "kK3"].forEach((id) => $(id).addEventListener("input", () => $(id).removeAttribute("aria-invalid")));

// Penyegaran berkala agar status penilaian dan hasil konsensus muncul tanpa muat ulang halaman.
// Dilewati bila: belum masuk, hasil sudah final, tab tidak aktif, permintaan/aksi masih berjalan,
// atau pengguna sedang memilih nilai pada dropdown.
function perluSegar() {
  if (!data || data.konsensus || document.hidden || pengendali || sibuk) return false;
  const aktif = document.activeElement;
  return !(aktif && aktif.tagName === "SELECT");
}
setInterval(() => { if (perluSegar()) muat(false); }, JEDA_SEGAR);
document.addEventListener("visibilitychange", () => {
  if (perluSegar() && Date.now() - waktuMuat >= JEDA_SEGAR) muat(false);
});

// Muat awal: /api/me tidak menghasilkan 401 saat belum masuk, jadi konsol tetap bersih.
(async () => {
  try {
    const me = await api("/api/me");
    if (me.pengguna) await muat(true);
    else tampilLogin("");
  } catch (e) {
    tampilLogin("");
    $("galatLogin").textContent = e.message;
  }
})();
