"""Validasi legalitas langkah dan pembanding engine (Stockfish) untuk SKAKMAT.

Engine di sini HANYA pembanding: hasilnya tidak masuk ke TOPSIS maupun Borda. Skala engine
(centipawn) tidak sebanding dengan skala penilaian manusia 1 sampai 5, jadi tidak digabung.

Modul ini opsional. Bila pustaka python-chess atau program Stockfish tidak ada, aplikasi tetap
berjalan seperti semula; fungsi di sini mengembalikan penanda "tidak tersedia" beserta alasannya.

Lokasi Stockfish: variabel lingkungan SKAKMAT_STOCKFISH (path program), atau "stockfish" di PATH.
SKAKMAT_STOCKFISH=mati mematikan engine dengan sengaja.
"""
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
KEDALAMAN = 16
WAKTU_ANALISIS = 1.5      # detik, per analisis
WAKTU_START = 5.0         # detik, menunggu engine siap
WAKTU_ANTRE = 3.0         # detik, menunggu giliran bila engine sedang dipakai permintaan lain
JUMLAH_USUL = 3

_kunci = threading.Lock()     # satu proses engine sekaligus
_cache = {}                   # (fen, kandidat...) -> hasil peringkat (hanya hasil yang deterministik)
_gagal = {}                   # (fen, kandidat...) -> (waktu, hasil) kegagalan sementara, diingat sebentar
JEDA_COBA_LAGI = 30.0         # detik sebelum engine yang gagal dicoba lagi untuk kasus yang sama
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
    try:
        e = chess.engine.SimpleEngine.popen_uci(p, timeout=WAKTU_START)
    except Exception:
        raise EngineTidakTersedia("engine_gagal", "Stockfish gagal dijalankan di server.")
    e.timeout = WAKTU_ANALISIS + 3.0       # batas tiap perintah ke engine
    try:
        e.configure({"Threads": 1, "Hash": 64})
    except Exception:
        pass
    return e


def _analisis(b, multipv, root_moves=None):
    if not _kunci.acquire(timeout=WAKTU_ANTRE):
        raise EngineTidakTersedia("engine_sibuk", "Engine sedang dipakai permintaan lain. Coba lagi sebentar.")
    try:
        e = _buka_engine()
        try:
            hasil = e.analyse(b, chess.engine.Limit(depth=KEDALAMAN, time=WAKTU_ANALISIS),
                              multipv=multipv, root_moves=root_moves)
            nama = e.id.get("name", "Stockfish")
        except Exception:
            raise EngineTidakTersedia("engine_gagal", "Engine gagal menganalisis atau melebihi batas waktu.")
        finally:
            try:
                e.quit()
            except Exception:
                e.close()
        return hasil, nama
    finally:
        _kunci.release()


def _skor(s):
    """Skor dari sudut pandang pihak yang berjalan, dalam bentuk yang aman di-JSON-kan."""
    if s.is_mate():
        return {"cp": None, "mat": s.mate()}
    return {"cp": s.score(), "mat": None}


def peringkat_kasus(fen, kandidat):
    """Peringkat engine untuk kandidat kasus. Selalu mengembalikan dict dengan kunci 'tersedia'."""
    kunci = (fen, *kandidat)
    if kunci in _cache:
        return _cache[kunci]
    if kunci in _gagal and time.monotonic() - _gagal[kunci][0] < JEDA_COBA_LAGI:
        return _gagal[kunci][1]
    if not pustaka_ada():
        return tidak_tersedia("pustaka_tidak_ada", "Pustaka python-chess tidak terpasang di server.")
    b, pesan = papan(fen)           # FEN diperiksa dulu; FEN tidak sah tidak pernah masuk ke engine
    if pesan:
        return _simpan(kunci, tidak_tersedia("posisi_tidak_sah", pesan + " Engine tidak dijalankan."))
    langkah = []
    for i, k in enumerate(kandidat, start=1):
        m, pesan = baca_langkah(b, k)
        if pesan:
            return _simpan(kunci, tidak_tersedia("kandidat_tidak_sah", f"Kandidat {i}: {pesan} Engine tidak dijalankan."))
        langkah.append(m)
    if len(set(langkah)) != len(langkah):
        return _simpan(kunci, tidak_tersedia("kandidat_tidak_sah", "Ada kandidat yang merupakan langkah sama. Engine tidak dijalankan."))
    try:
        info, nama = _analisis(b, multipv=len(langkah), root_moves=langkah)
    except EngineTidakTersedia as e:
        # Kegagalan sementara tidak disimpan permanen; diingat sebentar supaya engine yang macet
        # tidak membuat setiap permintaan menunggu batas waktu lagi.
        hasil = tidak_tersedia(e.kode, e.alasan)
        if e.kode != "engine_sibuk":
            _gagal[kunci] = (time.monotonic(), hasil)
        return hasil
    skor = {}
    for baris in info:
        if baris.get("pv") and "score" in baris:
            skor[baris["pv"][0]] = baris["score"].pov(b.turn)
    if set(skor) != set(langkah):
        return tidak_tersedia("engine_gagal", "Engine tidak mengembalikan nilai untuk semua kandidat.")
    # Peringkat kompetisi: nilai sama -> peringkat sama (1, 1, 3).
    peringkat = [1 + sum(skor[x] > skor[m] for x in langkah) for m in langkah]
    hasil = {
        "tersedia": True,
        "engine": nama,
        "batas": {"kedalaman": KEDALAMAN, "waktu_detik": WAKTU_ANALISIS},
        "sudut_pandang": "putih" if b.turn else "hitam",
        "kandidat": [{"langkah": k, "san": b.san(m), **_skor(skor[m]), "peringkat": p}
                     for k, m, p in zip(kandidat, langkah, peringkat)],
    }
    return _simpan(kunci, hasil)


def _simpan(kunci, hasil):
    if len(_cache) > 256:
        _cache.clear()
    _cache[kunci] = hasil
    return hasil


def usul_kandidat(fen):
    """Tiga langkah teratas menurut engine, dalam format kandidat ('5. d4' / '5... Nf6').

    Mengembalikan (daftar, None) atau (None, (status_http, pesan)). Urutan dikembalikan menurut abjad,
    BUKAN menurut nilai engine, supaya usulan tidak membocorkan peringkat engine sebelum anggota menilai.
    """
    if not pustaka_ada():
        return None, (503, "Usulan engine tidak tersedia: pustaka python-chess tidak terpasang di server.")
    b, pesan = papan(fen)
    if pesan:
        return None, (400, pesan)
    sah = list(b.legal_moves)
    if b.is_game_over() or not sah:
        return None, (400, "Posisi sudah selesai (skakmat atau remis); tidak ada langkah untuk diusulkan.")
    if len(sah) < JUMLAH_USUL:
        return None, (400, f"Posisi ini hanya punya {len(sah)} langkah sah; perlu {JUMLAH_USUL} kandidat.")
    try:
        info, nama = _analisis(b, multipv=JUMLAH_USUL)
    except EngineTidakTersedia as e:
        return None, (503, "Usulan engine tidak tersedia: " + e.alasan)
    langkah = [baris["pv"][0] for baris in info if baris.get("pv")][:JUMLAH_USUL]
    if len(langkah) < JUMLAH_USUL:
        return None, (503, "Usulan engine tidak tersedia: engine mengembalikan kurang dari tiga langkah.")
    awal = f"{b.fullmove_number}. " if b.turn else f"{b.fullmove_number}... "
    return sorted(awal + b.san(m) for m in langkah), None
