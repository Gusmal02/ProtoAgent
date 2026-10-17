"""Lossless bounded storage envelope; old JSON checkpoints remain readable.

Compression is not authentication. Session verifies the stored SHA before this
decoder; snapshots are host storage, never an arbitrary plugin upload API.
"""
import zlib

MAGIC=b'PAZ1\x00'
MAX_BYTES=16*1024*1024

def pack(raw):
    if len(raw)>MAX_BYTES: raise ValueError('checkpoint size budget exceeded')
    compressed=MAGIC+zlib.compress(raw,level=1)
    return compressed if len(compressed)<len(raw) else raw

def unpack(stored):
    if len(stored)>MAX_BYTES: raise ValueError('checkpoint size budget exceeded')
    if not stored.startswith(MAGIC): return stored
    decoder=zlib.decompressobj()
    raw=decoder.decompress(stored[len(MAGIC):],MAX_BYTES+1)
    if len(raw)>MAX_BYTES or decoder.unconsumed_tail or not decoder.eof or decoder.unused_data:
        raise ValueError('invalid or oversized checkpoint envelope')
    return raw
