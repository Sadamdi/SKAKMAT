"use strict";
// Semua teks dari server dimasukkan lewat textContent, tidak pernah innerHTML.
// Satu-satunya input pengguna di aplikasi ini adalah menggerakkan bidak di papan (selain login).

const $ = (id) => document.getElementById(id);
const el = (tag, kelas, teks) => {
  const e = document.createElement(tag);
  if (kelas) e.className = kelas;
  if (teks !== undefined) e.textContent = teks;
  return e;
};
const f = (x, k = 4) => Number(x).toFixed(k).replace(".", ",");

const GLYPH = { k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
const NAMA_BIDAK = { k: "raja", q: "menteri", r: "benteng", b: "gajah", n: "kuda", p: "pion" };
const BERKAS = "abcdefgh";
const gerakDikurangi = matchMedia("(prefers-reduced-motion: reduce)");
let data = null;          // keadaan ronde bila sedang berada di pertandingan
let sudahMasuk = false;   // sudah login (di lobi atau di pertandingan)

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

function pesan(teks, galat, id = "pesan") {
  const p = $(id);
  p.textContent = teks || "";
  p.classList.toggle("galat", !!galat);
}

// Tabel dengan caption (tersembunyi visual), scope kolom/baris, dan aria-label.
function tabel(t, judul, kepala, baris, kelasBaris) {
  t.replaceChildren();
  t.setAttribute("aria-label", judul);
  t.append(el("caption", "sr", judul));
  const thead = el("thead");
  const tr0 = el("tr");
  kepala.forEach((h, i) => {
    const c = el("th", i === 0 ? "kiri" : "");
    if (h instanceof Node) c.append(h); else c.textContent = h;
    c.scope = "col";
    tr0.append(c);
  });
  thead.append(tr0);
  const tbody = el("tbody");
  baris.forEach((b, idx) => {
    const tr = el("tr", kelasBaris && kelasBaris(idx));
    b.forEach((v, i) => {
      const c = el(i === 0 ? "th" : "td", i === 0 ? "kiri" : "");
      if (v instanceof Node) c.append(v); else c.textContent = v;
      if (i === 0) c.scope = "row";
      tr.append(c);
    });
    tbody.append(tr);
  });
  t.append(thead, tbody);
}

// ------------------------------------------------------------------ identitas anggota
// Warna + inisial yang sama di seluruh halaman. Urutan = urutan peserta dari server; jumlah tidak di-hardcode.
const JUMLAH_WARNA = 4;
function inisial(nama) {
  return String(nama).trim().split(/\s+/).map((w) => (/^\d+$/.test(w) ? w : w.charAt(0).toUpperCase())).join("").slice(0, 3);
}
function orangDenganId(id) {
  return (data.peserta || []).find((p) => p.id === id) || { id, nama: `Anggota #${id}`, gaya: "", gaya_nama: "" };
}
function kelasDm(id) {
  const i = (data.peserta || []).findIndex((p) => p.id === id);
  return `dm-${((i < 0 ? 0 : i) % JUMLAH_WARNA) + 1}`;
}
function lencana(orang) {
  const e = el("span", `lencana ${kelasDm(orang.id)}`, inisial(orang.nama));
  e.setAttribute("aria-hidden", "true");   // nama selalu ditulis di sebelahnya
  return e;
}
// Lencana + nama + gaya. Gaya ditulis sebagai teks, jadi pembedanya tidak hanya warna.
function namaDm(orang, tambahan = "", denganGaya = true) {
  const w = el("span", `nama-dm ${kelasDm(orang.id)}`);
  w.append(lencana(orang), el("span", "", orang.nama + tambahan));
  if (denganGaya && orang.gaya_nama) w.append(el("span", "tag-gaya", orang.gaya_nama));
  if (orang.ketua) w.append(el("span", "tag-gaya tag-ketua", "Ketua"));
  return w;
}

// ------------------------------------------------------------------ papan
let pilih = null;          // petak bidak yang sedang dipilih, mis. "e2"
let gerak = {};            // petak asal -> [{ke, uci, san}] langkah sah ronde ini
let interaktif = false;
let mengirim = false;
let tandaPapan = "";
let tampilan = null;       // {fen, sorot} yang sedang digambar (berubah saat animasi papan)

function isiFen(fen) {
  const out = {};
  fen.split(" ")[0].split("/").forEach((b, r) => {
    let c = 0;
    for (const ch of b) {
      if (/\d/.test(ch)) c += Number(ch);
      else { out[BERKAS[c] + (8 - r)] = ch; c++; }
    }
  });
  return out;
}
const timPutih = () => data.kasus.sisi_tim === "putih";
const namaBidak = (ch) => `${NAMA_BIDAK[ch.toLowerCase()]} ${ch === ch.toUpperCase() ? "putih" : "hitam"}`;

// Elemen dekoratif: label petak sudah menyebut koordinat, jadi disembunyikan dari pembaca layar.
function hiasan(kelas, teks) {
  const e = el("span", kelas, teks);
  e.setAttribute("aria-hidden", "true");
  return e;
}

// Gambar papan untuk fen. sorot: {terakhir: [petak...], usul: {petak: kelasDm}, tanda: {petak: [orang...]}}
function gambarPapan(fen, sorot = {}) {
  tampilan = { fen, sorot };
  const papan = $("papan");
  const fokusSq = papan.contains(document.activeElement) ? document.activeElement.dataset.sq : null;
  papan.replaceChildren();
  const isi = isiFen(fen);
  const putihBawah = timPutih();
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 8; c++) {
      const berkas = putihBawah ? c : 7 - c;
      const baris = putihBawah ? 8 - r : r + 1;
      const sq = BERKAS[berkas] + baris;
      const b = el("button", "petak " + ((berkas + baris) % 2 === 1 ? "g" : "t"));
      b.type = "button";
      b.dataset.sq = sq;
      b.tabIndex = -1;
      const ch = isi[sq];
      if (ch) {
        const putih = ch === ch.toUpperCase();
        const s = el("span", "bidak " + (putih ? "putih" : "hitam"), GLYPH[ch.toLowerCase()] + "︎");
        s.setAttribute("aria-hidden", "true");
        b.append(s);
        b.dataset.warna = putih ? "w" : "b";
      }
      if (r === 7) b.append(hiasan("koord berkas", BERKAS[berkas]));
      if (c === 0) b.append(hiasan("koord baris", String(baris)));
      if ((sorot.terakhir || []).includes(sq)) b.classList.add("terakhir");
      if (sorot.usul && sorot.usul[sq]) b.classList.add("usul", sorot.usul[sq]);
      const tanda = sorot.tanda && sorot.tanda[sq];
      if (tanda) {
        const w = el("span", "tanda-usul");
        tanda.forEach((o) => w.append(lencana(o)));
        b.append(w);
      }
      papan.append(b);
    }
  }
  perbaruiTanda();
  if (fokusSq) {
    const t = papan.querySelector(`[data-sq="${fokusSq}"]`);
    if (t && t.tabIndex === 0) t.focus();
  }
}

// Kelas dan label tiap petak sesuai keadaan pilihan. Hanya bidak yang bisa bergerak (dan, setelah
// memilih, petak tujuannya) yang bisa dicapai dengan Tab.
function perbaruiTanda() {
  const isi = isiFen(tampilan.fen);
  const tujuan = pilih && gerak[pilih] ? gerak[pilih] : [];
  $("papan").querySelectorAll(".petak").forEach((b) => {
    const sq = b.dataset.sq;
    const bisa = interaktif && !!gerak[sq];
    const t = tujuan.find((x) => x.ke === sq);
    b.classList.toggle("bisa", bisa);
    b.classList.toggle("dipilih", sq === pilih);
    b.classList.toggle("tujuan", !!t);
    b.classList.toggle("makan", !!t && !!isi[sq]);
    b.tabIndex = bisa || t ? 0 : -1;
    let label = `${sq}, ${isi[sq] ? namaBidak(isi[sq]) : "kosong"}`;
    if (sq === pilih) label += ", dipilih. Pilih petak tujuan atau tekan Esc untuk batal";
    else if (t) label += `, tujuan sah: ${t.san}`;
    else if (bisa) label += ", dapat digerakkan";
    if (b.classList.contains("terakhir")) label += ", langkah terakhir";
    b.setAttribute("aria-label", label);
    if (bisa) b.setAttribute("aria-pressed", String(sq === pilih)); else b.removeAttribute("aria-pressed");
  });
}

function pesanPapan(teks, galat) {
  const p = $("pesanPapan");
  p.textContent = teks || "";
  p.classList.toggle("galat", !!galat);
}

function batalPilih(teks, galat) {
  const lama = pilih;
  pilih = null;
  perbaruiTanda();
  if (lama) {   // bidak "kembali": fokus tetap di bidak asal
    const b = $("papan").querySelector(`[data-sq="${lama}"]`);
    if (b && document.activeElement && $("papan").contains(document.activeElement)) b.focus();
  }
  if (teks !== undefined) pesanPapan(teks, galat);
}

function klikPetak(sq, keyboard) {
  if (!data || mengirim) return;
  const isi = isiFen(tampilan.fen);
  if (!interaktif) {
    if (isi[sq]) pesanPapan(alasanTidakInteraktif(), false);
    return;
  }
  if (!pilih) {
    if (gerak[sq]) {
      pilih = sq;
      perbaruiTanda();
      pesanPapan(`${namaBidak(isi[sq])} di ${sq} dipilih. Pilih petak tujuan (${gerak[sq].length} pilihan).`);
      if (keyboard) {
        const t = $("papan").querySelector(".petak.tujuan");
        if (t) t.focus();
      }
    } else if (isi[sq] && (isi[sq] === isi[sq].toUpperCase()) === timPutih()) {
      pesanPapan(`${namaBidak(isi[sq])} di ${sq} tidak punya langkah sah saat ini.`, true);
    } else if (isi[sq]) {
      pesanPapan(`Hanya bidak ${data.kasus.sisi_tim} (tim Anda) yang bisa digerakkan.`, true);
    }
    return;
  }
  if (sq === pilih) return batalPilih("Pilihan dibatalkan.");
  if (gerak[sq]) {   // ganti ke bidak lain milik tim
    pilih = null;
    return klikPetak(sq, keyboard);
  }
  const t = gerak[pilih].find((x) => x.ke === sq);
  if (!t) return batalPilih(`Langkah tidak sah: ${namaBidak(isi[pilih])} di ${pilih} tidak bisa ke ${sq}. Bidak kembali ke tempatnya.`, true);
  kirimUsulan(t);
}

function alasanTidakInteraktif() {
  if (!data.server.python_chess) return "Server tidak bisa memeriksa langkah (python-chess tidak terpasang), jadi papan hanya bisa dilihat.";
  if (data.kasus.selesai || (data.konsensus && data.konsensus.akhir)) return "Permainan sudah selesai. Tekan Ronde baru untuk bermain lagi.";
  if (animasiPapanJalan) return "Sedang memperlihatkan langkah ronde sebelumnya…";
  return "Semua anggota sudah dinilai. Menunggu Ketua menjalankan konsensus.";
}

async function kirimUsulan(t) {
  mengirim = true;
  $("papan").classList.add("sibuk");
  $("papan").setAttribute("aria-busy", "true");
  pesanPapan(`Mengirim usulan ${t.san}…`);
  try {
    const j = await api("/api/usul", { langkah: t.uci });
    pilih = null;
    if (j.penilaian_siap) {
      pesanPapan(`Usulan ${j.usulan.san} terkirim. Usulan Anda yang terakhir; penilaian individual selesai, menunggu Ketua menjalankan konsensus.`);
    } else if (j.galat_penilaian) {
      pesanPapan(`Usulan ${j.usulan.san} tersimpan, tapi penilaian individual gagal dibuat: ${j.galat_penilaian}`, true);
    } else {
      pesanPapan(`Usulan ${j.usulan.san} terkirim. Masih bisa diganti dengan menggerakkan bidak lain sampai semua anggota mengusulkan.`);
    }
    await muat(true);
  } catch (e) {
    if (e.status === 401) return tampilLogin(SESI_HABIS);
    batalPilih(`${e.message} Bidak kembali ke tempatnya.`, true);
    await muat(true);
  } finally {
    mengirim = false;
    $("papan").classList.remove("sibuk");
    $("papan").removeAttribute("aria-busy");
  }
}

// --- seret (pointer events: mouse, sentuh, pena). Klik-klik tetap jalan; seret hanya jalan pintas.
let seret = null;
let abaikanKlik = false;
$("papan").addEventListener("pointerdown", (ev) => {
  const b = ev.target.closest(".petak");
  if (!b || !interaktif || mengirim || ev.button !== 0 || !gerak[b.dataset.sq]) return;
  seret = { sq: b.dataset.sq, x: ev.clientX, y: ev.clientY, id: ev.pointerId, hantu: null, asal: b };
});
document.addEventListener("pointermove", (ev) => {
  if (!seret || ev.pointerId !== seret.id) return;
  if (!seret.hantu) {
    if (Math.hypot(ev.clientX - seret.x, ev.clientY - seret.y) < 6) return;
    if (pilih !== seret.sq) { pilih = seret.sq; perbaruiTanda(); }
    const glyph = seret.asal.querySelector(".bidak");
    const h = el("div", "hantu bidak " + (glyph.classList.contains("putih") ? "putih" : "hitam"), glyph.textContent);
    h.style.fontSize = getComputedStyle(seret.asal).fontSize;
    h.setAttribute("aria-hidden", "true");
    document.body.append(h);
    seret.hantu = h;
    seret.asal.classList.add("diseret");
  }
  seret.hantu.style.left = ev.clientX + "px";
  seret.hantu.style.top = ev.clientY + "px";
});
function akhiriSeret(ev, jatuhkan) {
  if (!seret || ev.pointerId !== seret.id) return;
  const s = seret;
  seret = null;
  if (!s.hantu) return;            // tidak bergeser: biarkan event click menangani
  s.hantu.remove();
  s.asal.classList.remove("diseret");
  abaikanKlik = true;
  setTimeout(() => { abaikanKlik = false; }, 0);
  if (!jatuhkan) return batalPilih("Seret dibatalkan.");
  const target = document.elementFromPoint(ev.clientX, ev.clientY);
  const b = target && target.closest && target.closest("#papan .petak");
  if (!b) return batalPilih("Bidak dilepas di luar papan. Bidak kembali ke tempatnya.", true);
  if (b.dataset.sq === s.sq) return pesanPapan(`Bidak di ${s.sq} dipilih. Pilih petak tujuan.`);
  klikPetak(b.dataset.sq, false);
}
document.addEventListener("pointerup", (ev) => akhiriSeret(ev, true));
document.addEventListener("pointercancel", (ev) => akhiriSeret(ev, false));
$("papan").addEventListener("click", (ev) => {
  const b = ev.target.closest(".petak");
  if (!b || abaikanKlik) return;
  klikPetak(b.dataset.sq, ev.detail === 0);   // detail 0 = diaktifkan keyboard (Enter/Spasi)
});
$("papan").addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && pilih) { ev.preventDefault(); batalPilih("Pilihan dibatalkan."); }
});

// ------------------------------------------------------------------ keadaan ronde
const uciKe = (u) => [u.slice(0, 2), u.slice(2, 4)];

// Posisi yang ditampilkan: bila permainan selesai oleh langkah tim, ronde aktif sudah dinilai dan
// papannya adalah posisi setelah langkah pemenang.
function fenSekarang() {
  return data.konsensus ? data.konsensus.fen_setelah : data.kasus.fen;
}
function sorotSekarang() {
  const sorot = { usul: {} };
  const h = data.hasil_terakhir;
  if (h && !data.konsensus) {   // langkah terakhir: pilihan kelompok + balasan lawan
    sorot.terakhir = [...uciKe(h.pemenang.uci), ...(h.lawan ? uciKe(h.lawan.uci) : [])];
  } else if (h) {
    sorot.terakhir = uciKe(h.pemenang.uci);
  }
  if (data.usulan_saya && !data.konsensus) {
    uciKe(data.usulan_saya.uci).forEach((sq) => { sorot.usul[sq] = kelasDm(data.pengguna.id); });
  }
  return sorot;
}

function renderRonde() {
  const { kasus, pengguna } = data;
  $("identitasAkun").replaceChildren(...namaDm(orangDenganId(pengguna.id)).childNodes);
  $("identitasAkun").className = `nama-dm ${kelasDm(pengguna.id)}`;
  $("judulRonde").textContent = `Permainan ${kasus.permainan} · Ronde ${kasus.nomor}`;
  const pt = data.pertandingan;
  $("infoMatch").replaceChildren(el("strong", "", pt.nama), ` · kode ${pt.kode} · ${pt.anggota.length} dari 3 pemain · Ketua: ${pt.ketua || "-"}`);
  const akhir = kasus.selesai || (data.konsensus && data.konsensus.akhir);
  $("giliran").textContent = akhir ? "Permainan selesai" : `Tim Anda: ${kasus.sisi_tim}, giliran melangkah`;
  $("selesai").classList.toggle("sembunyi", !akhir);
  $("selesai").textContent = akhir ? `${akhir} Tekan Ronde baru untuk bermain lagi dari posisi awal.` : "";
  $("riwayat").textContent = data.konsensus
    ? `${kasus.riwayat_teks} ${kasus.riwayat.length % 2 === 0 ? `${kasus.riwayat.length / 2 + 1}. ` : ""}${data.konsensus.pemenang.san}`
    : kasus.riwayat_teks || "(belum ada langkah)";

  // usulan sendiri
  const us = $("usulanSaya");
  if (akhir) us.textContent = "Tidak ada ronde yang berjalan.";
  else if (data.usulan_saya) {
    us.replaceChildren("Anda mengusulkan ", el("strong", "", data.usulan_saya.san),
      data.semua_sudah ? "." : ". Bisa diganti dengan menggerakkan bidak lain sampai semua anggota mengusulkan.");
  } else us.textContent = "Belum. Gerakkan satu bidak putih di papan untuk mengusulkan langkah.";

  // status tim
  const st = $("status");
  st.replaceChildren();
  data.peserta.forEach((p) => {
    const li = el("li", kelasDm(p.id));
    li.append(namaDm(p, p.id === pengguna.id ? " (Anda)" : ""));
    li.append(el("span", p.sudah ? "ok" : "tunggu", p.sudah ? "✓ sudah mengusulkan" : "○ belum mengusulkan"));
    st.append(li);
  });
  const belum = data.peserta.filter((p) => !p.sudah);
  const rs = $("ringkasStatus");
  if (akhir) rs.textContent = "Permainan selesai.";
  else if (belum.length) {
    rs.replaceChildren("Menunggu usulan dari: ");
    belum.forEach((p, i) => { if (i) rs.append(", "); rs.append(namaDm(p, "", false)); });
    rs.append(".");
  } else rs.textContent = data.penilaian ? "Semua anggota sudah dinilai; menunggu Ketua menjalankan konsensus." : "Semua anggota sudah mengusulkan.";
  rs.classList.toggle("tunggu-kotak", !akhir && belum.length > 0);

  // papan: hanya digambar ulang bila ada yang berubah, supaya pilihan & fokus tidak hilang saat penyegaran
  gerak = {};
  (data.langkah_sah || []).forEach((m) => { (gerak[m.dari] = gerak[m.dari] || []).push(m); });
  interaktif = data.langkah_sah.length > 0 && !animasiPapanJalan;
  if (pilih && !gerak[pilih]) pilih = null;
  const tanda = JSON.stringify([fenSekarang(), sorotSekarang(), interaktif]);
  if (!animasiPapanJalan && tanda !== tandaPapan) {
    tandaPapan = tanda;
    gambarPapan(fenSekarang(), sorotSekarang());
  } else if (!animasiPapanJalan) perbaruiTanda();
  if (!data.server.python_chess) pesanPapan(alasanTidakInteraktif(), true);
  renderIndividual();
}

// ------------------------------------------------------------------ penilaian individual (sebelum konsensus Ketua)
let tandaIndividual = "";

function renderIndividual() {
  const pen = data.penilaian;
  $("kartuIndividual").classList.toggle("sembunyi", !pen);
  $("btnMundur").classList.toggle("sembunyi", !data.bisa_mundur);
  $("btnKonsensus").classList.toggle("sembunyi", !pen || !data.bisa_konsensus);
  $("ketKonsensus").classList.toggle("sembunyi", !pen || !data.bisa_konsensus);
  if (!pen) { tandaIndividual = ""; return; }
  const ketua = data.peserta.find((p) => p.ketua);
  $("ketKonsensus").textContent = "Semua anggota sudah dinilai. Tekan tombol di atas untuk memutuskan langkah kelompok dengan voting Borda.";
  $("infoKonsensus").textContent = data.bisa_konsensus
    ? "Semua anggota sudah dinilai. Sebagai Ketua (jabatan tertinggi), Anda menjalankan voting Borda untuk memutuskan langkah kelompok."
    : `Semua anggota sudah dinilai. Menunggu Ketua (${ketua ? ketua.nama : "-"}) menjalankan konsensus.`;
  const tanda = String(pen.kasus_id);
  if (tanda === tandaIndividual) return;
  tandaIndividual = tanda;
  const alt = pen.alternatif;
  const du = $("daftarUsulanInd");
  du.replaceChildren();
  alt.forEach((a) => a.pengusul.forEach((pid) => {
    const li = el("li");
    li.append(namaDm(orangDenganId(pid)), el("span", "langkah", a.san));
    if (a.dukungan > 1) li.append(el("span", "dukungan", `usulan ganda: ${a.dukungan} orang`));
    du.append(li);
  }));
  const kepala = [el("span", "", "Alternatif")];
  data.kriteria.forEach((k) => {
    const s = el("span");
    s.append(el("span", "kode", `${k.kode} ${k.nama}`), el("span", "ket", k.jenis === "cost" ? "cost: makin besar makin buruk" : "benefit"));
    kepala.push(s);
  });
  tabel($("tabelKriteriaInd"), "Nilai C1 sampai C5 tiap alternatif, diukur mesin", kepala,
    alt.map((a, i) => [`${a.san}${a.dukungan > 1 ? ` (${a.dukungan} usulan)` : ""}`, ...pen.kriteria.nilai[i].map((v) => f(v, 2))]));
  tandaiCost($("tabelKriteriaInd"));
  const wadah = $("tigaIndividual");
  wadah.replaceChildren();
  pen.topsis.forEach((t) => {
    const orang = { ...orangDenganId(t.pengguna_id), nama: t.nama, gaya_nama: t.gaya_nama };
    const blok = el("section", `blok-topsis ${kelasDm(t.pengguna_id)}`);
    const judul = el("h4");
    judul.append(namaDm(orang));
    blok.append(judul, el("p", "bobot", "Bobot " + data.kriteria.map((k, jj) => `${k.kode} ${t.bobot[jj]}`).join(" · ")));
    const tb = el("table");
    tabel(tb, `TOPSIS gaya ${t.gaya_nama} (${t.nama})`, ["Alternatif", "D+", "D−", "V", "Peringkat"],
      alt.map((a, i) => [a.san, f(t.hasil.d_plus[i]), f(t.hasil.d_min[i]), f(t.hasil.v[i]), String(t.hasil.rank[i])]),
      (i) => (t.hasil.rank[i] === 1 ? "menang" : ""));
    const g = el("div", "gulir");
    g.append(tb);
    blok.append(g, el("p", "pilihan", `Pilihan gaya ${t.gaya_nama.toLowerCase()}: ${alt[t.hasil.rank.indexOf(1)].san}`));
    wadah.append(blok);
  });
}

// ------------------------------------------------------------------ animasi papan setelah penilaian
// Bila hasil ronde baru masuk saat halaman terbuka: tampilkan usulan di posisi lama, lalu langkah
// pemenang, lalu balasan lawan. Kurangi gerakan: langsung posisi akhir.
let tandaHasilPapan = null;
let animasiPapanJalan = false;
let pewaktuPapan = [];
const JEDA_PAPAN = 1300;

function mungkinAnimasiPapan() {
  const h = data.hasil_terakhir;
  const id = h ? String(h.kasus_id) : "-";
  const awal = tandaHasilPapan === null;
  if (id === tandaHasilPapan) return;
  tandaHasilPapan = id;
  if (awal || !h) return;
  pewaktuPapan.forEach(clearTimeout);
  pewaktuPapan = [];
  const ringkas = `Ronde ${h.nomor} dinilai: kelompok memainkan ${h.pemenang.san}` + (h.lawan ? `, lawan membalas ${h.lawan.san}.` : ".");
  if (gerakDikurangi.matches) { pesanPapan(ringkas); return; }
  animasiPapanJalan = true;
  interaktif = false;
  pilih = null;
  const tanda = {};
  h.alternatif.forEach((a) => {
    const ke = uciKe(a.uci)[1];
    tanda[ke] = (tanda[ke] || []).concat(a.pengusul.map(orangDenganId));
  });
  gambarPapan(h.fen_sebelum, { tanda });
  pesanPapan(`Ronde ${h.nomor}: usulan ${h.alternatif.map((a) => a.san).join(", ")}.`);
  pewaktuPapan.push(setTimeout(() => {
    gambarPapan(h.fen_setelah, { terakhir: uciKe(h.pemenang.uci) });
    pesanPapan(`Keputusan kelompok (Borda): ${h.pemenang.san}.`);
  }, JEDA_PAPAN));
  pewaktuPapan.push(setTimeout(() => {
    animasiPapanJalan = false;
    tandaPapan = "";
    renderRonde();
    pesanPapan(ringkas);
  }, JEDA_PAPAN * (h.lawan ? 2 : 1)));
}

// ------------------------------------------------------------------ hasil penilaian
let tandaHasil = "";

function renderHasil() {
  const h = data.hasil_terakhir;
  $("belumHasil").classList.toggle("sembunyi", !!h);
  $("isiHasil").classList.toggle("sembunyi", !h);
  if (!h) { tandaHasil = ""; hentikanAnimasi(); return; }
  const tanda = String(h.kasus_id);
  if (tanda === tandaHasil) return;
  tandaHasil = tanda;
  const alt = h.alternatif;
  const nama = alt.map((a) => a.san);
  const b = h.borda;

  $("judulHasil").textContent = `Hasil penilaian ronde ${h.nomor}`;
  const p = $("pemenang");
  p.replaceChildren("Langkah terpilih: ", el("strong", "", h.pemenang.san));
  if (h.lawan) p.append(` · lawan membalas ${h.lawan.san}`);
  if (h.akhir) p.append(` · ${h.akhir}`);
  $("banding").textContent = kalimatBanding(h);
  if (h.lawan) $("banding").append(el("span", "catatan", ` Langkah lawan dimainkan oleh ${h.lawan.sumber}.`));

  // 1. usulan
  const du = $("daftarUsulan");
  du.replaceChildren();
  alt.forEach((a) => a.pengusul.forEach((pid) => {
    const li = el("li");
    li.append(namaDm(orangDenganId(pid)), el("span", "langkah", a.san));
    if (a.dukungan > 1) li.append(el("span", "dukungan", `usulan ganda: ${a.dukungan} orang`));
    du.append(li);
  }));

  // 2. C1-C5
  const kr = h.kriteria;
  const sumber = kr.sumber;
  $("sumberKriteria").textContent = sumber.mode === "engine"
    ? `Diukur dengan ${sumber.engine}, kedalaman ${sumber.kedalaman}, dari sudut pandang tim ${sumber.sisi_tim}. Posisi yang sama selalu menghasilkan angka yang sama.`
    : `Stockfish tidak tersedia (${sumber.alasan_statis || "tanpa alasan"}). C2 diukur secara statis; C1, C3, C4, C5 tetap dihitung dari papan.`;
  const kepala = [el("span", "", "Alternatif")];
  data.kriteria.forEach((k) => {
    const s = el("span");
    s.append(el("span", "kode", `${k.kode} ${k.nama}`), el("span", "ket", k.jenis === "cost" ? "cost: makin besar makin buruk" : "benefit"));
    kepala.push(s);
  });
  tabel($("tabelKriteria"), "Nilai C1 sampai C5 tiap alternatif, skala 1 sampai 5, diukur mesin", kepala,
    alt.map((a, i) => [`${a.san}${a.dukungan > 1 ? ` (${a.dukungan} usulan)` : ""}`, ...kr.nilai[i].map((v) => f(v, 2))]));
  tandaiCost($("tabelKriteria"));
  tabel($("tabelRincian"), "Ukuran mentah di balik nilai C1 sampai C5", ["Alternatif", "C1", "C2", "C3", "C4", "C5"],
    alt.map((a, i) => [a.san, ...teksRincian(kr.rincian[i])]));
  tandaiCost($("tabelRincian"));

  // 3. TOPSIS per gaya
  const wadah = $("tigaTopsis");
  wadah.replaceChildren();
  h.topsis.forEach((t) => {
    const orang = { ...orangDenganId(t.pengguna_id), nama: t.nama, gaya_nama: t.gaya_nama };
    const blok = el("section", `blok-topsis ${kelasDm(t.pengguna_id)}`);
    const judul = el("h4");
    judul.append(namaDm(orang));
    blok.append(judul, el("p", "bobot", "Bobot " + data.kriteria.map((k, j) => `${k.kode} ${t.bobot[j]}`).join(" · ")));
    const tb = el("table");
    tabel(tb, `TOPSIS gaya ${t.gaya_nama} (${t.nama})`, ["Alternatif", "D+", "D−", "V", "Peringkat"],
      alt.map((a, i) => [a.san, f(t.hasil.d_plus[i]), f(t.hasil.d_min[i]), f(t.hasil.v[i]), String(t.hasil.rank[i])]),
      (i) => (t.hasil.rank[i] === 1 ? "menang" : ""));
    const g = el("div", "gulir");
    g.append(tb);
    blok.append(g, el("p", "pilihan", `Pilihan gaya ${t.gaya_nama.toLowerCase()}: ${nama[t.hasil.rank.indexOf(1)]}`));
    wadah.append(blok);
  });

  // 4. Borda
  tabel($("tabelBorda"), "Hasil voting Borda kelompok", ["Alternatif", "Dukungan usulan", "Poin Borda", "Nilai Borda", "Peringkat"],
    alt.map((a, i) => [a.san, String(a.dukungan), f(b.poin[i]), f(b.nilai[i]), String(b.rank[i])]),
    (i) => (b.rank[i] === 1 ? "menang" : ""));
  $("aturanSeri").textContent = `Bila nilai Borda sama, pemutusnya: ${b.aturan_seri}. Tidak ada akun yang suaranya lebih berat.`;
  renderAnimasi(h);
  renderEngine(h);
}

function tandaiCost(t) {
  // kolom C5 (indeks 5) adalah cost: beri latar berbeda + keterangan di kepala, bukan hanya warna
  t.querySelectorAll("tr").forEach((tr) => { if (tr.children[5]) tr.children[5].classList.add("cost"); });
}

function teksRincian(r) {
  const c2 = r.C2.metode === "statis" ? "statis" : `${r.C2.ply} ply variasi engine`;
  const tanda = (x) => (x > 0 ? `+${x}` : String(x));
  return [
    `${r.C1.perisai_pion} pion pelindung, ${r.C1.serangan_ke_zona_raja} serangan ke zona raja`,
    `material ${tanda(r.C2.perubahan_material)} (${c2})`,
    `kontrol pusat ${tanda(r.C3.kontrol_pusat_bersih)}`,
    `${r.C4.bidak_lawan_terserang} bidak lawan diserang, mobilitas ${r.C4.mobilitas}${r.C4.memberi_skak ? ", skak" : ""}`,
    `untung tangkapan lawan ${r.C5.untung_tangkapan_lawan}, ${r.C5.langkah_skak_lawan} langkah skak lawan`,
  ];
}

// Kalimat yang menjelaskan peran Borda: siapa yang sepakat dengan keputusan kelompok, siapa tidak.
function kalimatBanding(h) {
  const nama = h.alternatif.map((a) => a.san);
  const menang = h.borda.pemenang;
  if (h.alternatif.length === 1) return `Suara bulat: ketiga anggota mengusulkan ${nama[0]}, jadi hanya ada satu alternatif.`;
  const setuju = h.topsis.filter((t) => t.hasil.rank[menang] === 1);
  const beda = h.topsis.filter((t) => t.hasil.rank[menang] !== 1);
  const sebut = (ts) => ts.map((t) => `${t.nama} (${t.gaya_nama.toLowerCase()})`).join(", ");
  if (!beda.length) return `Ketiga gaya sepakat: ${nama[menang]} peringkat 1 menurut TOPSIS setiap anggota.`;
  return `Gaya tidak sepakat. ${nama[menang]} adalah pilihan ${setuju.length ? sebut(setuju) : "tidak satu pun gaya secara langsung"}; `
    + beda.map((t) => `${t.nama} (${t.gaya_nama.toLowerCase()}) lebih memilih ${nama[t.hasil.rank.indexOf(1)]}`).join(", ")
    + `. Borda menggabungkan ketiga peringkat dan memutuskan ${nama[menang]}.`;
}

// ------------------------------------------------------------------ animasi penggabungan Borda
// Yang dianimasikan hanyalah penjumlahan: poin Borda tiap anggota (bobot peringkat × V) ditumpuk per
// alternatif, satu anggota per langkah. Hasil akhir sudah tertulis di tabel sebelum animasi mulai.
const JEDA_LANGKAH = 450;
let pewaktu = [];
let modelAnimasi = null;

function hentikanAnimasi() {
  pewaktu.forEach(clearTimeout);
  pewaktu = [];
}

function hitungSumbangan(h) {
  const b = h.borda;
  const sumbangan = h.topsis.map((t) => h.alternatif.map((_, i) => b.bobot_borda[t.hasil.rank[i] - 1] * t.hasil.v[i]));
  for (let i = 0; i < h.alternatif.length; i++) {
    if (Math.abs(sumbangan.reduce((a, s) => a + s[i], 0) - b.poin[i]) > 1e-9) return null;
  }
  return { h, sumbangan, maks: Math.max(...b.poin) || 1 };
}

function renderAnimasi(h) {
  hentikanAnimasi();
  const m = hitungSumbangan(h);
  modelAnimasi = m;
  $("animasi").classList.toggle("sembunyi", !m);
  if (!m) return;
  const nama = h.alternatif.map((a) => a.san);
  const b = h.borda;
  $("judulAnimasi").textContent = `Bagaimana ${h.topsis.length} peringkat digabung`;
  $("ketAnimasi").textContent = `Tiap anggota menyumbang poin ke setiap alternatif: bobot peringkatnya (${b.bobot_borda.join(", ")} untuk peringkat ${b.bobot_borda.map((_, i) => i + 1).join(", ")}) `
    + "dikali skor preferensi V dari TOPSIS gayanya. Poin semua anggota dijumlahkan; total terbesar menjadi keputusan kelompok.";
  const batang = $("batang");
  batang.replaceChildren();
  nama.forEach((n, i) => {
    const baris = el("div", "batang-baris");
    baris.dataset.alt = String(i);
    baris.append(el("span", "batang-nama", n));
    const jalur = el("div", "batang-jalur");
    h.topsis.forEach((t, d) => {
      const seg = el("span", `segmen ${kelasDm(t.pengguna_id)}`);
      seg.dataset.penilai = String(d);
      const lebar = (m.sumbangan[d][i] / m.maks) * 100;
      seg.dataset.lebar = lebar.toFixed(3);
      if (lebar >= 9) seg.textContent = inisial(t.nama);
      jalur.append(seg);
    });
    baris.append(jalur, el("span", "batang-total", f(0)));
    batang.append(baris);
  });
  tabel($("tabelPeringkat"), "Sumbangan poin Borda tiap anggota per alternatif", ["Anggota", ...nama],
    [...h.topsis.map((t, d) => [t.nama, ...nama.map((_, i) => `#${t.hasil.rank[i]} → ${b.bobot_borda[t.hasil.rank[i] - 1]} × ${f(t.hasil.v[i])} = ${f(m.sumbangan[d][i])}`)]),
      ["Total poin", ...nama.map((_, i) => f(b.poin[i]))]],
    (r) => (r === h.topsis.length ? "total" : kelasDm(h.topsis[r].pengguna_id)));
  $("tabelPeringkat").querySelectorAll("tbody tr").forEach((tr, r) => {
    const t = h.topsis[r];
    if (t) tr.firstChild.replaceChildren(namaDm({ ...orangDenganId(t.pengguna_id), nama: t.nama, gaya_nama: t.gaya_nama }));
  });
  putarAnimasi();
}

function setLangkah(d) {
  const m = modelAnimasi;
  const b = m.h.borda;
  const n = m.h.topsis.length;
  $("batang").querySelectorAll(".batang-baris").forEach((baris) => {
    const i = Number(baris.dataset.alt);
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
  $("tabelPeringkat").querySelectorAll("tbody tr").forEach((tr, r) => tr.classList.toggle("aktif", r === d - 1 && d <= n));
  $("langkahAnim").textContent = d === 0 ? "Mulai dari nol poin."
    : d <= n ? `Menambahkan poin dari ${m.h.topsis[d - 1].nama}, gaya ${m.h.topsis[d - 1].gaya_nama.toLowerCase()} (${d} dari ${n}).`
      : `Semua poin terkumpul. Keputusan kelompok: ${m.h.pemenang.san}.`;
}

function putarAnimasi() {
  hentikanAnimasi();
  if (!modelAnimasi) return;
  const n = modelAnimasi.h.topsis.length;
  const diam = gerakDikurangi.matches;
  $("btnPutar").classList.toggle("sembunyi", diam);
  if (diam) return setLangkah(n + 1);
  setLangkah(0);
  for (let d = 1; d <= n + 1; d++) pewaktu.push(setTimeout(() => setLangkah(d), d * JEDA_LANGKAH));
}

// ------------------------------------------------------------------ pembanding engine
// Nilai engine untuk tiap alternatif hanya ditampilkan sebagai pembanding: tidak ikut TOPSIS maupun Borda.
function nilaiEngine(x) {
  if (x.mat !== null && x.mat !== undefined) return x.mat > 0 ? `mat dalam ${x.mat}` : x.mat < 0 ? `dimat dalam ${-x.mat}` : "skakmat";
  const pion = x.cp / 100;
  return (pion > 0 ? "+" : pion < 0 ? "−" : "±") + Math.abs(pion).toFixed(2).replace(".", ",");
}
// Angka urut dari sudut pandang tim: mat untuk tim paling tinggi, dimat paling rendah.
const urutEngine = (x) => (x.mat === null || x.mat === undefined ? x.cp : x.mat > 0 ? 1e6 - x.mat : x.mat === 0 ? 2e6 : -1e6 - x.mat);

function renderEngine(h) {
  const st = $("statusEngine");
  const eng = h.kriteria.engine || [];
  $("wadahEngine").classList.add("sembunyi");
  st.className = "status-engine kosong";
  if (!eng.length || eng.some((x) => !x)) {
    st.textContent = "Pembanding engine tidak tersedia untuk ronde ini: Stockfish tidak dipakai saat penilaian. Keputusan kelompok tidak terpengaruh.";
    return;
  }
  const nama = h.alternatif.map((a) => a.san);
  const skor = eng.map(urutEngine);
  const peringkat = skor.map((s) => 1 + skor.filter((x) => x > s).length);
  const menang = h.borda.pemenang;
  const sepakat = peringkat[menang] === 1;
  st.className = "status-engine " + (sepakat ? "sepakat" : "beda");
  st.textContent = (sepakat ? `Sepakat: ${nama[menang]} juga dinilai paling baik oleh engine.`
    : `Berbeda: kelompok memilih ${nama[menang]}, sedangkan engine sendiri paling menilai ${nama.filter((_, i) => peringkat[i] === 1).join(" / ")}.`)
    + " Engine tidak ikut memilih; angka ini hanya pembanding.";
  if (nama.length > 1) {
    tabel($("tabelEngine"), "Peringkat kelompok dibandingkan penilaian engine", ["Alternatif", "Peringkat kelompok (Borda)", "Peringkat engine", `Nilai engine (pion, sudut tim ${h.kriteria.sumber.sisi_tim})`],
      nama.map((n, i) => [n, String(h.borda.rank[i]), String(peringkat[i]), nilaiEngine(eng[i])]),
      (i) => (h.borda.rank[i] === 1 ? "menang" : ""));
    $("wadahEngine").classList.remove("sembunyi");
  }
}

// ------------------------------------------------------------------ pemuatan dan penyegaran
const JEDA_SEGAR = 4000;
const SESI_HABIS = "Sesi berakhir, silakan masuk lagi.";
let pengendali = null;
let waktuMuat = 0;
let sibuk = 0;

const jam = (t) => new Date(t).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
function infoSegar(teks) {
  $("infoSegar").textContent = teks !== undefined ? teks : !data ? ""
    : `Diperbarui pukul ${jam(waktuMuat)}; diperbarui otomatis tiap ${JEDA_SEGAR / 1000} detik.`;
}

async function muat(paksa) {
  if (pengendali) {
    if (!paksa) return;
    pengendali.abort();
  }
  const ini = new AbortController();
  pengendali = ini;
  try {
    const d = await api("/api/ronde", undefined, ini.signal);
    waktuMuat = Date.now();
    sudahMasuk = true;
    if (!d.pertandingan) {          // belum atau tidak lagi berada di pertandingan: tampilkan lobi
      const tadi = !!data;
      data = null;
      tandaPapan = ""; tandaHasil = ""; tandaHasilPapan = null; pilih = null;
      hentikanAnimasi();
      pesanPapan("");              // pesan papan dari pertandingan sebelumnya tidak ikut terbawa
      await muatLobi(d.pengguna, tadi ? "Kamu sudah tidak berada di pertandingan." : "", ini.signal);
      return;
    }
    data = d;
    tandaLobi = "";
    tampilApp();
    pesan("");
    mungkinAnimasiPapan();
    renderRonde();
    renderHasil();
  } catch (e) {
    if (e.name === "AbortError") return;
    if (e.status === 401) return tampilLogin(sudahMasuk ? SESI_HABIS : "");
    pesan(e.message, true);
  } finally {
    if (pengendali === ini) {
      pengendali = null;
      infoSegar();
    }
  }
}

function tampilApp() {
  $("viewMuat").classList.add("sembunyi");
  $("viewLogin").classList.add("sembunyi");
  $("viewLobi").classList.add("sembunyi");
  $("viewApp").classList.remove("sembunyi");
  $("akun").classList.remove("sembunyi");
}
function tampilLogin(info) {
  if (pengendali) { pengendali.abort(); pengendali = null; }
  data = null;
  sudahMasuk = false;
  tandaLobi = "";
  tandaPapan = ""; tandaHasil = ""; tandaHasilPapan = null; pilih = null;
  $("viewMuat").classList.add("sembunyi");
  $("viewApp").classList.add("sembunyi");
  $("viewLobi").classList.add("sembunyi");
  $("akun").classList.add("sembunyi");
  $("viewLogin").classList.remove("sembunyi");
  $("infoLogin").textContent = info || "";
  if (info) $("inUser").focus();
}

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
  }
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
$("btnRondeBaru").addEventListener("click", () => {
  if (!confirm("Mulai permainan baru dari posisi awal? Usulan yang belum dinilai di ronde ini akan ditinggalkan.")) return;
  kirimDengan($("btnRondeBaru"), "Memulai…", async () => {
    try {
      await api("/api/ulang", {});
      pilih = null;
      pesanPapan("Permainan baru dimulai dari posisi awal.");
      await muat(true);
    } catch (e) {
      if (e.status === 401) return tampilLogin(SESI_HABIS);
      pesan(e.message, true);
    }
  });
});
$("btnKonsensus").addEventListener("click", () => kirimDengan($("btnKonsensus"), "Menjalankan…", async () => {
  try {
    await api("/api/konsensus", {});
    pesan("Konsensus Borda dijalankan.", false);
    await muat(true);
  } catch (e) {
    if (e.status === 401) return tampilLogin(SESI_HABIS);
    pesan(e.message, true);
  }
}));
$("btnMundur").addEventListener("click", () => {
  if (!window.confirm("Kembali ke giliran sebelumnya? Langkah terakhir dibatalkan dan semua anggota mengusulkan ulang.")) return;
  kirimDengan($("btnMundur"), "Kembali…", async () => {
    try {
      await api("/api/mundur", {});
      pesan("Kembali ke giliran sebelumnya.", false);
      await muat(true);
    } catch (e) {
      if (e.status === 401) return tampilLogin(SESI_HABIS);
      pesan(e.message, true);
    }
  });
});
$("btnPutar").addEventListener("click", putarAnimasi);
gerakDikurangi.addEventListener("change", () => { if (modelAnimasi) putarAnimasi(); });
$("btnSegar").addEventListener("click", () => kirimDengan($("btnSegar"), "Menyegarkan…", () => muat(true)));


// ------------------------------------------------------------------ lobi: daftar, buat, gabung, keluar
function isiPilihanGaya(sel, profil, daftar) {
  sel.replaceChildren();
  daftar.forEach((g) => sel.append(new Option(profil[g].nama + " (bobot " + profil[g].bobot.join("/") + ")", g)));
}

let tandaLobi = "";   // isi daftar yang sedang digambar; daftar hanya digambar ulang bila berubah

async function muatLobi(pengguna, info, signal) {
  const l = await api("/api/lobi", undefined, signal);
  $("viewMuat").classList.add("sembunyi");
  $("viewLogin").classList.add("sembunyi");
  $("viewApp").classList.add("sembunyi");
  $("viewLobi").classList.remove("sembunyi");
  $("akun").classList.remove("sembunyi");
  $("identitasAkun").className = "nama-dm";
  $("identitasAkun").textContent = (pengguna || l.pengguna).nama;
  if (info) pesan(info, false, "pesanLobi"); else if (!$("pesanLobi").classList.contains("galat")) pesan("", false, "pesanLobi");
  const semua = Object.keys(l.profil);
  if (!$("selGayaBuat").options.length) {
    isiPilihanGaya($("selGayaBuat"), l.profil, semua);
    isiPilihanGaya($("selGayaKode"), l.profil, semua);
  }
  // Digambar ulang hanya bila isinya berubah, supaya pilihan gaya dan klik tombol tidak hilang saat penyegaran berkala.
  const tanda = JSON.stringify(l.daftar.map((m) => [m.id, m.nama, m.kode, m.anggota.map((a) => [a.id, a.gaya, a.ketua]), m.gaya_tersedia]));
  if (tanda === tandaLobi) return;
  tandaLobi = tanda;
  const wadah = $("daftarMatch");
  wadah.replaceChildren();
  if (!l.daftar.length) wadah.append(el("p", "catatan", "Belum ada pertandingan yang berlangsung. Buat yang pertama di atas."));
  l.daftar.forEach((m) => {
    const baris = el("div", "baris-match");
    const kiri = el("div", "kiri-match");
    kiri.append(el("strong", "", m.nama), el("span", "catatan", ` · kode ${m.kode} · Ketua ${m.ketua || "-"}`));
    kiri.append(el("div", "catatan", m.anggota.map((a) => `${a.nama} (${a.gaya_nama}${a.ketua ? ", Ketua" : ""})`).join("; ")));
    const kanan = el("div", "form-baris");
    if (m.penuh) kanan.append(el("span", "catatan", `Penuh (${m.anggota.length}/${l.maks_anggota})`));
    else {
      const sel = el("select");
      sel.setAttribute("aria-label", `Gaya main untuk ${m.nama}`);
      isiPilihanGaya(sel, l.profil, m.gaya_tersedia);
      const tombol = el("button", "", `Gabung (${m.anggota.length}/${l.maks_anggota})`);
      tombol.type = "button";
      tombol.addEventListener("click", () => gabungKe({ id: m.id, gaya: sel.value }, tombol));
      kanan.append(sel, tombol);
    }
    baris.append(kiri, kanan);
    wadah.append(baris);
  });
}

function aksiLobi(tombol, teksSibuk, jalur, isi) {
  return kirimDengan(tombol, teksSibuk, async () => {
    try {
      await api(jalur, isi);
      pesan("", false, "pesanLobi");
      await muat(true);
    } catch (e) {
      if (e.status === 401) return tampilLogin(SESI_HABIS);
      pesan(e.message, true, "pesanLobi");
      try { await muatLobi(null, "", undefined); } catch (e2) { /* biarkan pesan galat tampil */ }
      pesan(e.message, true, "pesanLobi");
    }
  });
}
const gabungKe = (isi, tombol) => aksiLobi(tombol, "Bergabung…", "/api/pertandingan/gabung", isi);

$("formBuat").addEventListener("submit", (ev) => {
  ev.preventDefault();
  aksiLobi($("btnBuat"), "Membuat…", "/api/pertandingan/buat", { nama: $("inNamaMatch").value, gaya: $("selGayaBuat").value });
});
$("formKode").addEventListener("submit", (ev) => {
  ev.preventDefault();
  aksiLobi($("btnKode"), "Bergabung…", "/api/pertandingan/gabung", { kode: $("inKode").value, gaya: $("selGayaKode").value });
});
$("btnSegarLobi").addEventListener("click", () => kirimDengan($("btnSegarLobi"), "Menyegarkan…", () => muat(true)));
$("btnKeluarMatch").addEventListener("click", () => {
  if (!confirm("Keluar dari pertandingan? Usulanmu di ronde ini dibuang. Bila semua pemain keluar, pertandingan berakhir.")) return;
  kirimDengan($("btnKeluarMatch"), "Keluar…", async () => {
    try {
      await api("/api/pertandingan/keluar", {});
      pilih = null;
      await muat(true);
    } catch (e) {
      if (e.status === 401) return tampilLogin(SESI_HABIS);
      pesan(e.message, true);
    }
  });
});

// ------------------------------------------------------------------ daftar akun baru
function tampilDaftar(daftar) {
  $("formLogin").classList.toggle("sembunyi", daftar);
  $("formDaftar").classList.toggle("sembunyi", !daftar);
  $("judulLogin").textContent = daftar ? "Daftar akun baru" : "Masuk";
  (daftar ? $("dfUser") : $("inUser")).focus();
}
$("btnKeDaftar").addEventListener("click", () => tampilDaftar(true));
$("btnKeMasuk").addEventListener("click", () => tampilDaftar(false));
$("formDaftar").addEventListener("submit", (ev) => {
  ev.preventDefault();
  $("galatDaftar").textContent = "";
  kirimDengan($("btnDaftar"), "Mendaftar…", async () => {
    try {
      await api("/api/daftar", { username: $("dfUser").value.trim().toLowerCase(), nama: $("dfNama").value.trim(), sandi: $("dfSandi").value });
      $("dfSandi").value = "";
      $("infoLogin").textContent = "";
      await muat(true);
    } catch (e) { $("galatDaftar").textContent = e.message; }
  });
});

// Penyegaran berkala: status anggota lain dan hasil penilaian muncul tanpa muat ulang halaman.
// Dilewati saat belum masuk, tab tidak aktif, permintaan/aksi berjalan, bidak sedang dipilih/diseret,
// atau animasi papan sedang berjalan.
function perluSegar() {
  return sudahMasuk && !document.hidden && !pengendali && !sibuk && !mengirim && !seret && !pilih && !animasiPapanJalan;
}
setInterval(() => { if (perluSegar()) muat(false); }, JEDA_SEGAR);
document.addEventListener("visibilitychange", () => {
  if (perluSegar() && Date.now() - waktuMuat >= JEDA_SEGAR) muat(false);
});

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
