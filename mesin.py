"""Validasi langkah, pengukuran kriteria C1-C5, dan balasan lawan untuk SKAKMAT (python-chess + Stockfish).

Engine di sini HANYA alat ukur: Stockfish dipakai untuk mengukur C2 (variasi utama sebelum material
dihitung), sebagai angka pembanding yang ditampilkan, dan untuk memainkan langkah lawan. Engine tidak
memilih langkah tim dan tidak menjadi kriteria TOPSIS. Pemilihan langkah tim tetap TOPSIS + Borda (gdss.py).

python-chess wajib untuk alur bermain (legalitas, posisi setelah langkah). Stockfish opsional: tanpa
Stockfish, C2 dihitung secara statis dan lawan memakai aturan sederhana; hasil ditandai di respons.

Lokasi Stockfish: variabel lingkungan SKAKMAT_STOCKFISH (path program), atau "stockfish" di PATH.
SKAKMAT_STOCKFISH=mati mematikan engine dengan sengaja.
"""
import math
import os
import re
import shutil
import threading
import time

try:
    import chess
    import chess.engine
except ImportError:      # python-chess belum dipasang: validasi legalitas & engine dilewati
    chess = None

# Batas kerja engine. Setiap permintaan dibatasi kedalaman DAN waktu; proses engine juga punya
# batas waktu sendiri untuk start dan untuk setiap perintah, jadi permintaan tidak bisa menggantung.
WAKTU_ANALISIS = 1.5      # detik, per analisis
WAKTU_START = 5.0         # detik, menunggu engine siap
WAKTU_ANTRE = 3.0         # detik, menunggu giliran bila engine sedang dipakai permintaan lain

_kunci = threading.Lock()     # satu proses engine sekaligus
_gagal = {"sampai": 0.0, "alasan": ""}   # engine yang baru gagal tidak dicoba lagi sampai waktu ini
JEDA_COBA_LAGI = 30.0         # detik sebelum engine yang gagal dicoba lagi
_NOMOR = re.compile(r"^\s*\d+\s*\.+\s*")


class EngineTidakTersedia(Exception):
    """Engine tidak bisa dipakai; pesan = alasan yang aman ditampilkan ke pengguna."""

    def __init__(self, kode, alasan):
        super().__init__(alasan)
        self.kode, self.alasan = kode, alasan


def tidak_tersedia(kode, alasan):
    return {"tersedia": False, "kode": kode, "alasan": alasan}


def pustaka_ada():
    return chess is not None


def path_engine():
    p = os.environ.get("SKAKMAT_STOCKFISH")
    if p is not None:
        return None if p.strip().lower() in ("", "mati", "off") else p
    return shutil.which("stockfish")


# ------------------------------------------------------------------ legalitas
_STATUS = [
    ("STATUS_NO_WHITE_KING", "tidak ada raja putih"),
    ("STATUS_NO_BLACK_KING", "tidak ada raja hitam"),
    ("STATUS_TOO_MANY_KINGS", "raja lebih dari satu untuk satu warna"),
    ("STATUS_TOO_MANY_WHITE_PAWNS", "pion putih lebih dari 8"),
    ("STATUS_TOO_MANY_BLACK_PAWNS", "pion hitam lebih dari 8"),
    ("STATUS_PAWNS_ON_BACKRANK", "ada pion di baris 1 atau 8"),
    ("STATUS_TOO_MANY_WHITE_PIECES", "bidak putih lebih dari 16"),
    ("STATUS_TOO_MANY_BLACK_PIECES", "bidak hitam lebih dari 16"),
    ("STATUS_BAD_CASTLING_RIGHTS", "hak rokade tidak cocok dengan letak raja/benteng"),
    ("STATUS_INVALID_EP_SQUARE", "petak en passant tidak mungkin"),
    ("STATUS_OPPOSITE_CHECK", "raja pihak yang tidak berjalan sedang diskak"),
    ("STATUS_TOO_MANY_CHECKERS", "raja diskak oleh terlalu banyak bidak"),
    ("STATUS_IMPOSSIBLE_CHECK", "susunan skak tidak mungkin terjadi"),
]


def papan(fen):
    """(Board, None) bila posisi sah menurut aturan catur, selain itu (None, pesan)."""
    try:
        b = chess.Board(fen)
    except ValueError as e:
        return None, f"FEN tidak sah: {e}."
    st = b.status()
    if st != chess.STATUS_VALID:
        sebab = [t for nama, t in _STATUS if st & getattr(chess, nama, 0)]
        return None, "Posisi tidak sah menurut aturan catur: " + ("; ".join(sebab) or "status tidak valid") + "."
    return b, None


def baca_langkah(b, teks):
    """Ubah teks kandidat (mis. '5. d4', 'Nf3', '5... O-O', 'e2e4') menjadi Move sah, atau (None, pesan)."""
    inti = _NOMOR.sub("", teks).strip()
    if not inti:
        return None, f'"{teks}" tidak berisi langkah.'
    try:
        return b.parse_san(inti), None
    except chess.AmbiguousMoveError:
        return None, f'"{teks}" ambigu: lebih dari satu bidak bisa melangkah ke sana. Sebutkan petak/kolom asal (mis. Nbd2).'
    except chess.IllegalMoveError:
        return None, f'"{teks}" bukan langkah sah untuk {"putih" if b.turn else "hitam"} di posisi ini.'
    except chess.InvalidMoveError:
        pass
    try:
        m = chess.Move.from_uci(inti)
        if m in b.legal_moves:
            return m, None
    except ValueError:
        pass
    return None, f'"{teks}" tidak dikenali sebagai notasi langkah (pakai SAN seperti e4, Nf3, O-O, exd5).'


def validasi_kasus(fen, kandidat):
    """Pesan galat bila posisi atau kandidat tidak sah, atau None. None juga bila python-chess tidak ada
    (pemanggil sebaiknya memberi peringatan bahwa legalitas tidak diperiksa)."""
    if not pustaka_ada():
        return None
    b, pesan = papan(fen)
    if pesan:
        return pesan
    if b.is_game_over():
        return "Posisi sudah selesai (skakmat atau remis); tidak ada langkah yang bisa dinilai."
    langkah = []
    for i, k in enumerate(kandidat, start=1):
        m, pesan = baca_langkah(b, k)
        if pesan:
            return f"Kandidat {i}: {pesan}"
        if m in langkah:
            return f"Kandidat {langkah.index(m) + 1} dan {i} adalah langkah yang sama ({b.san(m)})."
        langkah.append(m)
    return None


# ------------------------------------------------------------------ engine
def _buka_engine():
    if not pustaka_ada():
        raise EngineTidakTersedia("pustaka_tidak_ada", "Pustaka python-chess tidak terpasang di server.")
    p = path_engine()
    if not p:
        raise EngineTidakTersedia("engine_tidak_ada", "Program Stockfish tidak ditemukan di server.")
    if time.monotonic() < _gagal["sampai"]:
        raise EngineTidakTersedia("engine_gagal", _gagal["alasan"] + " (dicoba lagi sebentar lagi)")
    try:
        e = chess.engine.SimpleEngine.popen_uci(p, timeout=WAKTU_START)
    except Exception:
        _catat_gagal("Stockfish gagal dijalankan di server.")
        raise EngineTidakTersedia("engine_gagal", "Stockfish gagal dijalankan di server.")
    e.timeout = WAKTU_ANALISIS + 3.0       # batas tiap perintah ke engine
    try:
        e.configure({"Threads": 1, "Hash": 64})
    except Exception:
        pass
    return e


def mainkan(fen, uci):
    """(fen setelah langkah, SAN langkah). Langkah harus sudah divalidasi."""
    b = chess.Board(fen)
    m = chess.Move.from_uci(uci)
    san = b.san(m)
    b.push(m)
    return b.fen(), san


def status_akhir(fen, tim):
    """Keterangan bila permainan selesai di posisi fen, dari sudut pandang tim (True = putih), selain itu None."""
    b = chess.Board(fen)
    if b.is_checkmate():
        return "Skakmat. Tim menang." if b.turn != tim else "Skakmat. Tim kalah."
    if b.is_stalemate():
        return "Remis: pat (tidak ada langkah sah, raja tidak diskak)."
    if b.is_insufficient_material():
        return "Remis: material tidak cukup untuk skakmat."
    if b.is_seventyfive_moves():
        return "Remis: aturan 75 langkah."
    if b.is_fivefold_repetition():
        return "Remis: posisi terulang lima kali."
    return None


# ------------------------------------------------------------------ kriteria C1-C5 otomatis
# Nilai C1-C5 untuk satu usulan langkah dihitung pada POSISI HIPOTETIS SETELAH langkah itu dijalankan.
# Semua angka dipetakan ke skala 1..5 yang sama dengan skala penilaian manual di laporan, lewat fungsi
# tanh yang mulus dan tetap (tidak bergantung pada alternatif lain), jadi posisi yang sama selalu
# menghasilkan angka yang sama dan tidak ada satu kriteria yang mendominasi karena satuannya besar.
#
# Dasar tiap ukuran adalah istilah evaluasi catur yang baku (lihat chessprogramming.org: King Safety,
# Material, Center Control, Mobility, Threats):
#   C1 keamanan raja   : perisai pion di depan raja dikurangi jumlah serangan lawan ke zona raja.
#   C2 keamanan material: perubahan saldo material setelah variasi utama Stockfish (pertukaran
#                         diselesaikan dulu). Tanpa Stockfish: saldo material dikurangi ancaman
#                         tangkapan terbesar lawan (perkiraan statis, ditandai di hasil).
#   C3 penguasaan pusat : (serangan + penempatan tim di d4, e4, d5, e5) dikurangi milik lawan.
#   C4 peluang serangan : bidak lawan yang terserang + skak + mobilitas tim.
#   C5 risiko balasan   : keuntungan tangkapan yang tersedia bagi lawan + langkah skak lawan (COST).
# Engine HANYA mengukur (C2 dan pembanding nilai); engine tidak memilih langkah dan bukan kriteria ke-6.
KEDALAMAN_KRITERIA = 12     # kedalaman Stockfish untuk variasi utama C2 (deterministik: 1 thread, hash dibersihkan)
KEDALAMAN_LAWAN = 10        # kedalaman Stockfish saat memainkan balasan lawan
PLY_MATERIAL = 4            # langkah variasi utama yang dimainkan sebelum material dihitung
PLY_MATERIAL_MAKS = 8       # ... diperpanjang selama langkah berikutnya masih tangkapan
PUSAT = ("d4", "e4", "d5", "e5")
_cache_kriteria = {}        # (fen, uci, mode) -> hasil satu alternatif

if chess is not None:
    NILAI_BIDAK = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def _skala(x, s):
    """Peta bilangan bertanda ke (1, 5): 0 -> 3. Dipakai bila nilai bisa negatif (selisih)."""
    return round(3 + 2 * math.tanh(x / s), 4)


def _skala_positif(x, s):
    """Peta bilangan >= 0 ke [1, 5): 0 -> 1."""
    return round(1 + 4 * math.tanh(max(x, 0) / s), 4)


def _saldo(b, tim):
    """Material tim dikurangi material lawan (pion=1, kuda=gajah=3, benteng=5, menteri=9)."""
    return sum(NILAI_BIDAK[p.piece_type] * (1 if p.color == tim else -1) for p in b.piece_map().values())


def _ancaman_tangkap(b, tim):
    """Dengan lawan berjalan di b: keuntungan tangkapan per bidak tim yang bisa dimakan lawan.
    Untung = nilai korban, dikurangi nilai pemakan bila korban dilindungi tim. Hanya yang untung > 0.
    Mengembalikan {petak: untung terbesar}."""
    out = {}
    for m in b.legal_moves:
        if not b.is_capture(m):
            continue
        korban_sq = m.to_square if not b.is_en_passant(m) else m.to_square + (8 if tim == chess.WHITE else -8)
        korban = b.piece_at(korban_sq)
        if korban is None:
            continue
        pemakan = b.piece_at(m.from_square)
        dilindungi = b.is_attacked_by(tim, korban_sq)
        untung = NILAI_BIDAK[korban.piece_type] - (NILAI_BIDAK[pemakan.piece_type] if dilindungi else 0)
        if untung > 0:
            out[korban_sq] = max(out.get(korban_sq, 0), untung)
    return out


def _c1(b, tim):
    raja = b.king(tim)
    zona = chess.SquareSet(chess.BB_KING_ATTACKS[raja]) | chess.SquareSet.from_square(raja)
    serangan = sum(len(b.attackers(not tim, sq)) for sq in zona)
    arah = 1 if tim == chess.WHITE else -1
    depan = chess.square_rank(raja) + arah
    perisai = 0
    if 0 <= depan <= 7:
        for f in range(max(0, chess.square_file(raja) - 1), min(7, chess.square_file(raja) + 1) + 1):
            p = b.piece_at(chess.square(f, depan))
            perisai += bool(p and p.color == tim and p.piece_type == chess.PAWN)
    return _skala(perisai - serangan, 3), {"perisai_pion": perisai, "serangan_ke_zona_raja": serangan}


def _c3(b, tim):
    bersih = 0
    for nama in PUSAT:
        sq = chess.parse_square(nama)
        p = b.piece_at(sq)
        tempat = (1 if p.color == tim else -1) if p else 0
        bersih += len(b.attackers(tim, sq)) - len(b.attackers(not tim, sq)) + tempat
    return _skala(bersih, 4), {"kontrol_pusat_bersih": bersih}


def _c4(b, tim):
    diserang = sum(1 for sq, p in b.piece_map().items()
                   if p.color != tim and p.piece_type != chess.KING and b.is_attacked_by(tim, sq))
    skak = 1 if b.is_check() else 0          # b: lawan berjalan, jadi is_check = tim baru saja memberi skak
    salin = b.copy(stack=False)
    salin.turn = tim
    salin.ep_square = None
    mobilitas = salin.pseudo_legal_moves.count()
    peluang = diserang + 2 * skak + mobilitas / 10
    return _skala_positif(peluang, 8), {"bidak_lawan_terserang": diserang, "memberi_skak": bool(skak),
                                        "mobilitas": mobilitas}


def _c5(b, tim):
    ancaman = _ancaman_tangkap(b, tim)
    skak = sum(1 for m in b.legal_moves if b.gives_check(m))
    risiko = sum(ancaman.values()) + 0.5 * min(skak, 4)
    return _skala_positif(risiko, 4), {"untung_tangkapan_lawan": sum(ancaman.values()),
                                       "langkah_skak_lawan": skak}


def _c2_statis(sebelum, b, tim):
    """Perkiraan tanpa engine: perubahan saldo dikurangi ancaman tangkapan terbesar lawan."""
    ancaman = max(_ancaman_tangkap(b, tim).values(), default=0)
    delta = _saldo(b, tim) - _saldo(sebelum, tim) - ancaman
    return _skala(delta, 2), {"perubahan_material": delta, "metode": "statis"}


def _c2_engine(sebelum, b, tim, info):
    """Mainkan variasi utama Stockfish dari posisi setelah langkah, lalu bandingkan saldo material."""
    akhir = b.copy(stack=False)
    ply = 0
    for m in info.get("pv", []):
        if ply >= PLY_MATERIAL_MAKS or (ply >= PLY_MATERIAL and not akhir.is_capture(m)):
            break
        if m not in akhir.legal_moves:
            break
        akhir.push(m)
        ply += 1
    delta = _saldo(akhir, tim) - _saldo(sebelum, tim)
    return _skala(delta, 2), {"perubahan_material": delta, "metode": "variasi utama engine", "ply": ply}


def _skor_json(s):
    return {"cp": None, "mat": s.mate()} if s.is_mate() else {"cp": s.score(), "mat": None}


def langkah_sah(fen):
    """Daftar langkah sah untuk papan interaktif: dari, ke, uci, san. Promosi selalu menjadi menteri,
    supaya satu-satunya input tetap 'pilih bidak lalu pilih petak'."""
    if not pustaka_ada():
        return []
    b, pesan = papan(fen)
    if pesan:
        return []
    out = []
    for m in b.legal_moves:
        if m.promotion not in (None, chess.QUEEN):
            continue
        out.append({"dari": chess.square_name(m.from_square), "ke": chess.square_name(m.to_square),
                    "uci": m.uci(), "san": b.san(m)})
    return sorted(out, key=lambda x: x["uci"])


def validasi_usulan(fen, teks):
    """(Move, None) bila teks (UCI seperti 'e2e4', atau SAN) adalah langkah sah di fen, selain itu (None, pesan).
    Pion yang mencapai baris akhir tanpa keterangan promosi dianggap promosi menteri."""
    if not pustaka_ada():
        return None, "Pustaka python-chess tidak terpasang di server; usulan langkah tidak bisa diperiksa."
    b, pesan = papan(fen)
    if pesan:
        return None, pesan
    if b.is_game_over():
        return None, "Permainan sudah selesai; tidak ada langkah yang bisa diusulkan."
    if not isinstance(teks, str) or not 2 <= len(teks.strip()) <= 10:
        return None, "Langkah tidak dikenali."
    t = teks.strip()
    if re.fullmatch(r"[a-h][1-8][a-h][1-8]", t):
        m = chess.Move.from_uci(t)
        if b.piece_type_at(m.from_square) == chess.PAWN and chess.square_rank(m.to_square) in (0, 7):
            m.promotion = chess.QUEEN
        if m in b.legal_moves:
            return m, None
        return None, f"Langkah {t[:2]}-{t[2:]} tidak sah untuk {'putih' if b.turn else 'hitam'} di posisi ini."
    m, pesan = baca_langkah(b, t)
    return (m, None) if m else (None, pesan)


def nilai_kriteria(fen, daftar_uci):
    """Nilai C1..C5 tiap alternatif (urutan sama dengan daftar_uci), dihitung dari posisi setelah langkah.

    Mengembalikan {"tersedia": True, "sumber": {...}, "alternatif": [{"uci","san","nilai":[5],"rincian","engine"}]}
    atau tidak_tersedia(...). Bila Stockfish tidak bisa dipakai untuk SALAH SATU alternatif, semua alternatif
    memakai C2 statis supaya kelimanya diukur dengan cara yang sama.
    """
    if not pustaka_ada():
        return tidak_tersedia("pustaka_tidak_ada", "Pustaka python-chess tidak terpasang di server.")
    sebelum, pesan = papan(fen)
    if pesan:
        return tidak_tersedia("posisi_tidak_sah", pesan)
    tim = sebelum.turn
    langkah = []
    for u in daftar_uci:
        m, pesan = validasi_usulan(fen, u)
        if pesan:
            return tidak_tersedia("langkah_tidak_sah", pesan)
        langkah.append(m)

    posisi = []
    for m in langkah:
        b = sebelum.copy(stack=False)
        b.push(m)
        posisi.append(b)

    info_engine, nama, alasan = None, None, None
    kunci_engine = [(fen, m.uci(), "engine") for m in langkah]
    if path_engine() and all(k in _cache_kriteria for k in kunci_engine):
        return _rakit(sebelum, langkah, [_cache_kriteria[k] for k in kunci_engine], "engine")
    try:
        info_engine, nama = _analisis_banyak(posisi, KEDALAMAN_KRITERIA)
    except EngineTidakTersedia as e:
        alasan = e.alasan

    hasil = []
    for m, b in zip(langkah, posisi):
        c1, r1 = _c1(b, tim)
        c3, r3 = _c3(b, tim)
        c4, r4 = _c4(b, tim)
        c5, r5 = _c5(b, tim)
        eng = None
        if info_engine is not None:
            info = info_engine[len(hasil)]
            c2, r2 = _c2_engine(sebelum, b, tim, info)
            eng = {**_skor_json(info["score"].pov(tim)), "kedalaman": info.get("depth"), "engine": nama,
                   # kedalaman di bawah target = dihentikan batas waktu; hasil seperti ini bisa berbeda antar
                   # jalannya, jadi ditandai dan tidak disimpan di cache.
                   "terpotong_waktu": bool(info.get("pv")) and (info.get("depth") or 0) < KEDALAMAN_KRITERIA}
        else:
            c2, r2 = _c2_statis(sebelum, b, tim)
        if b.is_checkmate():          # langkah yang langsung memenangkan permainan
            c1, c2, c4, c5 = 5.0, 5.0, 5.0, 1.0
        satu = {"uci": m.uci(), "san": sebelum.san(m), "nilai": [c1, c2, c3, c4, c5],
                "rincian": {"C1": r1, "C2": r2, "C3": r3, "C4": r4, "C5": r5}, "engine": eng}
        hasil.append(satu)
        if info_engine is not None and not eng["terpotong_waktu"]:
            if len(_cache_kriteria) > 2048:
                _cache_kriteria.clear()
            _cache_kriteria[(fen, m.uci(), "engine")] = satu
    return _rakit(sebelum, langkah, hasil, "engine" if info_engine is not None else "statis", nama, alasan)


def _rakit(sebelum, langkah, hasil, mode, nama=None, alasan=None):
    if mode == "engine" and nama is None:
        nama = next((h["engine"]["engine"] for h in hasil if h["engine"]), "Stockfish")
    sumber = {"mode": mode, "engine": nama if mode == "engine" else None,
              "kedalaman": KEDALAMAN_KRITERIA if mode == "engine" else None,
              "sisi_tim": "putih" if sebelum.turn else "hitam"}
    if alasan:
        sumber["alasan_statis"] = alasan
    return {"tersedia": True, "sumber": sumber, "alternatif": hasil}


def _catat_gagal(alasan):
    """Kegagalan diingat sebentar supaya engine yang macet tidak membuat setiap permintaan menunggu lagi."""
    _gagal.update(sampai=time.monotonic() + JEDA_COBA_LAGI, alasan=alasan)


def _analisis_banyak(daftar_posisi, kedalaman):
    """Analisis beberapa posisi dalam satu proses engine. Tiap posisi diawali 'ucinewgame' (hash dikosongkan)
    dan dibatasi kedalaman, sehingga hasilnya deterministik. Batas waktu tetap ada sebagai pengaman."""
    if not _kunci.acquire(timeout=WAKTU_ANTRE):
        raise EngineTidakTersedia("engine_sibuk", "Engine sedang dipakai permintaan lain.")
    try:
        e = _buka_engine()
        try:
            out = []
            for b in daftar_posisi:
                if b.is_game_over():
                    out.append({"score": chess.engine.PovScore(
                        chess.engine.Mate(0) if b.is_checkmate() else chess.engine.Cp(0), b.turn), "pv": [], "depth": 0})
                    continue
                out.append(e.analyse(b, chess.engine.Limit(depth=kedalaman, time=WAKTU_ANALISIS), game=object()))
            return out, e.id.get("name", "Stockfish")
        except Exception:
            _catat_gagal("Engine gagal menganalisis atau melebihi batas waktu.")
            raise EngineTidakTersedia("engine_gagal", "Engine gagal menganalisis atau melebihi batas waktu.")
        finally:
            try:
                e.quit()
            except Exception:
                e.close()
    finally:
        _kunci.release()


def langkah_lawan(fen):
    """Balasan lawan untuk posisi fen (lawan berjalan). Stockfish kedalaman rendah bila ada; tanpa engine
    dipakai aturan sederhana yang deterministik: tangkapan paling menguntungkan, selain itu langkah
    pertama menurut urutan UCI. Mengembalikan (Move, keterangan sumber) atau (None, alasan)."""
    if not pustaka_ada():
        return None, "Pustaka python-chess tidak terpasang di server."
    b, pesan = papan(fen)
    if pesan:
        return None, pesan
    if b.is_game_over():
        return None, "Permainan sudah selesai."
    if not _kunci.acquire(timeout=WAKTU_ANTRE):
        e_alasan = "Engine sedang dipakai permintaan lain."
    else:
        e_alasan = None
        try:
            e = _buka_engine()
            try:
                hasil = e.play(b, chess.engine.Limit(depth=KEDALAMAN_LAWAN, time=WAKTU_ANALISIS), game=object())
                if hasil.move in b.legal_moves:
                    return hasil.move, f"{e.id.get('name', 'Stockfish')}, kedalaman {KEDALAMAN_LAWAN}"
            except Exception:
                e_alasan = "Engine gagal memilih balasan."
                _catat_gagal(e_alasan)
            finally:
                try:
                    e.quit()
                except Exception:
                    e.close()
        except EngineTidakTersedia as x:
            e_alasan = x.alasan
        finally:
            _kunci.release()
    sah = sorted(b.legal_moves, key=lambda m: m.uci())
    terbaik = max(sah, key=lambda m: (_untung_sederhana(b, m), -sah.index(m)))
    return terbaik, f"aturan sederhana tanpa engine ({e_alasan})"


def _untung_sederhana(b, m):
    if not b.is_capture(m):
        return 0
    korban = b.piece_at(m.to_square)
    nilai = NILAI_BIDAK[korban.piece_type] if korban else 1
    pemakan = NILAI_BIDAK[b.piece_type_at(m.from_square)]
    b2 = b.copy(stack=False)
    b2.push(m)
    return nilai - (pemakan if b2.is_attacked_by(b2.turn, m.to_square) else 0)
