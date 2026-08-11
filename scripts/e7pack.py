"""Epic Seven `data.pack` access: container format, decryption, table parsing.

Two encryption layers sit between `data.pack` and a readable game table:

1. The pack itself is XOR-encrypted with a 128-byte key. That layer, plus the
   record scanner that locates files inside the pack, is handled by
   CeciliaBot's EpicSevenAssetRipper (`app/` package), which this module drives
   headlessly -- we do not reimplement it.

2. Each extracted `.db` payload is a *second* PLPcK container, XOR-encrypted
   with a 256-byte key applied at a per-file rotation. The ripper does not
   decode this layer.

`DB_KEY` below was recovered from the live pack, not from any published source:
`db/level_enter_drops.db` decrypts to ~61% NUL bytes, so the per-residue modal
ciphertext byte over its 19713 key-length blocks *is* the key. Every other
table then decrypts with the same key at some rotation in 0..255, which
`find_rotation` recovers from the known 5-byte `PLPcK` magic and confirms
against the container's trailing footer. `decrypt_db` refuses to return data it
could not confirm, so a key or format change surfaces as an error rather than
as garbage.

Decrypted container layout (little-endian):

    header      'PLPcK' | u8 version | u32 header_size | ...    (header_size bytes)
    index       u32 index_size, then a hash table of node offsets
    nodes       back-to-back records until the footer
    footer      header_size bytes, starting with 'PLPcK'

    node        u32 total | u8 tag(=2) | u8 key_len | u32 val_len | u8 pad
                | u32 ptr | key | value          (total == 15 + key_len + val_len)

Nodes form a flat key/value store. A table is reconstructed from four kinds of
key: `\\x09cols` and `\\x09rows` hold the column and row counts, `\\x09<i>` holds
column *i*'s name, `\\x09\\x09<i>` holds row *i*'s id, and the node keyed by that
id holds the row -- its column values joined by NUL.
"""
from __future__ import annotations

import os
import subprocess
import sys

MAGIC = b'PLPcK'
KEY_LEN = 256
NODE_HDR = 15

# 256-byte key for the inner .db layer; see module docstring for its provenance.
DB_KEY = bytes.fromhex(
    '55cfa24f6352d005933b50042be0ba4c708de8ebb52059b2059c9bfe90d8923d'
    'f74b43911bbc00bb6bfa91ae4ed4644f585162ec1bd5ef24addbaf838242aef5'
    '1e97804b134ffd8ce5bb4f6e3e6451147cdf56c318e5e964c999c0d95cc86082'
    '2e6b418be465d79a036dbf67ab3da72ab1023a4561f444e5ce858d23ea10feb4'
    '899151ad7e43ff3e2419a97b4dd3af4ef5c829e5af4ace9436f6b6b6382e9dfd'
    '26642099011a4899089c9d4b9f80bbb00a4cc73255ce1f78646e91c9c12313f5'
    'd840dc51457010d37d19615bb69888b42b19e749f993c00337e9332f89b320c1'
    '73a5653848788798a771739e72dbc84c7946597149bddae4e3bd1a17856c85a5')
_DB_KEY2 = DB_KEY + DB_KEY

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RIPPER = os.path.join(REPO_ROOT, 'tools', 'EpicSevenAssetRipper')
RIPPER_REPO = 'https://github.com/CeciliaBot/EpicSevenAssetRipper'
DEFAULT_PACK = r'C:\ProgramData\Smilegate\Games\EpicSeven\data.pack'


# --------------------------------------------------------------------------
# inner .db layer
# --------------------------------------------------------------------------

def find_rotation(raw: bytes) -> int | None:
    """Return the key rotation that decrypts `raw`, or None if none validates.

    Candidates come from the 5-byte magic; each is confirmed by decrypting the
    header size and checking that a second magic sits at the footer offset.
    """
    for rot in range(KEY_LEN):
        if bytes(raw[i] ^ _DB_KEY2[rot + i] for i in range(5)) != MAGIC:
            continue
        head = bytes(raw[i] ^ _DB_KEY2[rot + i] for i in range(10))
        hdr_size = int.from_bytes(head[6:10], 'little')
        foot = len(raw) - hdr_size
        if not (NODE_HDR < hdr_size < len(raw)):
            continue
        if bytes(raw[foot + i] ^ _DB_KEY2[(rot + foot + i) % KEY_LEN] for i in range(5)) == MAGIC:
            return rot
    return None


def decrypt_db(raw: bytes) -> bytes:
    """Decrypt an extracted `.db` payload. Raises if the layer cannot be confirmed."""
    if raw[:5] == MAGIC:
        return raw  # already plain
    rot = find_rotation(raw)
    if rot is None:
        raise ValueError('no key rotation produces a valid PLPcK container')
    ks = (_DB_KEY2[rot:rot + KEY_LEN] * (len(raw) // KEY_LEN + 2))[:len(raw)]
    return bytes(a ^ b for a, b in zip(raw, ks))


# --------------------------------------------------------------------------
# container / table parsing
# --------------------------------------------------------------------------

def _walk_nodes(data: bytes, start: int):
    out = []
    pos = start
    n = len(data)
    while pos + NODE_HDR <= n:
        total = int.from_bytes(data[pos:pos + 4], 'little')
        tag = data[pos + 4]
        klen = data[pos + 5]
        vlen = int.from_bytes(data[pos + 6:pos + 10], 'little')
        if tag != 2 or total != NODE_HDR + klen + vlen or pos + total > n:
            break
        out.append((data[pos + NODE_HDR:pos + NODE_HDR + klen],
                    data[pos + NODE_HDR + klen:pos + total]))
        pos += total
    return out, pos


def parse_table(data: bytes):
    """Parse a decrypted container into (columns, rows). Raises on any mismatch."""
    if data[:5] != MAGIC:
        raise ValueError('not a PLPcK container')
    hdr_size = int.from_bytes(data[6:10], 'little')
    index_size = int.from_bytes(data[hdr_size:hdr_size + 4], 'little')
    start = hdr_size + index_size
    footer = len(data) - hdr_size

    nodes, end = _walk_nodes(data, start)
    if end != footer or data[footer:footer + 5] != MAGIC:
        raise ValueError(f'node chain ended at {end}, expected footer at {footer}')

    d = dict(nodes)
    n_cols = int.from_bytes(d[b'\x09cols'], 'little')
    n_rows = int.from_bytes(d[b'\x09rows'], 'little')
    cols = [d[b'\x09' + str(i).encode()].decode('utf-8') for i in range(n_cols)]

    rows = []
    for i in range(n_rows):
        rid = d[b'\x09\x09' + str(i).encode()]
        vals = d[rid].split(b'\x00')
        if len(vals) == n_cols + 1 and vals[-1] == b'':
            vals = vals[:-1]
        if len(vals) != n_cols:
            raise ValueError(f'row {i} ({rid!r}) has {len(vals)} values, expected {n_cols}')
        rows.append([v.decode('utf-8', 'replace') for v in vals])
    return cols, rows


# --------------------------------------------------------------------------
# ripper (outer pack layer)
# --------------------------------------------------------------------------

def ensure_ripper(path: str = None) -> str:
    """Return the ripper checkout path, cloning it on first use."""
    path = path or os.environ.get('E7_RIPPER') or DEFAULT_RIPPER
    if not os.path.isdir(os.path.join(path, 'app')):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        subprocess.run(['git', 'clone', '--depth', '1', RIPPER_REPO, path], check=True)
    return path


def ripper_commit(path: str) -> str | None:
    try:
        out = subprocess.run(['git', '-C', path, 'log', '-1', '--format=%H %cs'],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return None


class PackReader:
    """Reads files out of `data.pack` via the ripper's scanner."""

    def __init__(self, pack_path: str = None, ripper_path: str = None):
        self.pack_path = pack_path or os.environ.get('E7_PACK') or DEFAULT_PACK
        if not os.path.exists(self.pack_path):
            raise FileNotFoundError(
                f'data.pack not found at {self.pack_path}. Install Epic Seven via the '
                'STOVE launcher and run it once, or set E7_PACK.')
        self.ripper_path = ensure_ripper(ripper_path)
        if self.ripper_path not in sys.path:
            sys.path.insert(0, self.ripper_path)
        # the ripper resolves settings.ini relative to cwd
        self._prev_cwd = os.getcwd()
        os.chdir(self.ripper_path)
        from app.pack import DataPack
        from app.util.pack_read import PackFileScanner
        self._pack = DataPack(self.pack_path)
        if self._pack._type != 'pack':
            raise ValueError(f'{self.pack_path} is not an Epic Seven data.pack')
        self._scanner = PackFileScanner(self._pack)

    def scan(self):
        """Yield every record as {name, size, offset, extra}."""
        while True:
            m = self._scanner.next()
            if m is None:
                return
            yield {'name': m.name, 'size': m.size, 'offset': m.offset_data,
                   'extra': list(m.mtime) if isinstance(m.mtime, list) else None}

    def read(self, record) -> bytes:
        return bytes(self._scanner.get_file_content(
            {'offset': record['offset'], 'size': record['size'], 'full_path': record['name']}))

    def close(self):
        try:
            self._scanner.close()
            self._pack.destroy()
        finally:
            os.chdir(self._prev_cwd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
