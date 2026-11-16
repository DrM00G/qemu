"""Bounded complete newc/zstd initramfs validation; never extract paths.

Local experiment only. libzstd's stable streaming API checks entire frames,
including optional checksums; window <=64MiB, total decoded bytes <=128MiB.
"""
import ctypes as C
import hashlib
import zlib
from block_reader import Outcome, require


class Buffer(C.Structure):
    _fields_ = [('data', C.c_void_p), ('size', C.c_size_t), ('pos', C.c_size_t)]


def zstd_frame(data, limit):
    try:
        lib = C.CDLL('libzstd.so.1')
    except OSError as exc:
        raise Outcome('UNSUPPORTED', 'libzstd required') from exc
    for name, args, result in [
        ('ZSTD_createDStream', [], C.c_void_p),
        ('ZSTD_freeDStream', [C.c_void_p], C.c_size_t),
        ('ZSTD_DCtx_setParameter', [C.c_void_p, C.c_int, C.c_int], C.c_size_t),
        ('ZSTD_decompressStream', [C.c_void_p, C.POINTER(Buffer), C.POINTER(Buffer)], C.c_size_t),
        ('ZSTD_isError', [C.c_size_t], C.c_uint),
        ('ZSTD_versionString', [], C.c_char_p),
    ]:
        func = getattr(lib, name); func.argtypes = args; func.restype = result
    ctx = lib.ZSTD_createDStream()
    require(ctx, 'INVALID_IMAGE', 'zstd context allocation')
    src = C.create_string_buffer(bytes(data))
    inp = Buffer(C.cast(src, C.c_void_p), len(data), 0)
    out = bytearray()
    try:
        require(not lib.ZSTD_isError(lib.ZSTD_DCtx_setParameter(ctx, 100, 26)),
                'UNSUPPORTED', 'zstd window bound unavailable')
        while True:
            dest = C.create_string_buffer(min(65536, limit-len(out)+1))
            buf = Buffer(C.cast(dest, C.c_void_p), len(dest), 0)
            before = inp.pos
            remaining = lib.ZSTD_decompressStream(ctx, C.byref(buf), C.byref(inp))
            require(not lib.ZSTD_isError(remaining), 'INVALID_IMAGE', 'malformed zstd frame/checksum/window')
            out.extend(dest.raw[:buf.pos])
            require(len(out) <= limit, 'INVALID_IMAGE', 'initramfs expansion limit')
            if remaining == 0:
                return bytes(out), inp.pos, lib.ZSTD_versionString().decode()
            require(inp.pos != before or buf.pos, 'INVALID_IMAGE', 'truncated zstd frame')
    finally:
        lib.ZSTD_freeDStream(ctx)


def validate_initramfs(data, newc, limit):
    require(0 < len(data) <= limit, 'INVALID_IMAGE', 'initramfs stored size bound')
    segments = []
    archives = entries = decoded_bytes = 0
    digest = hashlib.sha256()

    def account(chunk):
        nonlocal decoded_bytes
        decoded_bytes += len(chunk)
        require(decoded_bytes <= limit, 'INVALID_IMAGE', 'initramfs expansion limit')
        digest.update(chunk)

    def cpio_sequence(chunk):
        nonlocal archives, entries
        pos = 0
        while pos < len(chunk):
            if chunk[pos] == 0:
                pos += 1
                continue
            require(pos % 4 == 0, 'INVALID_IMAGE', 'unaligned decoded newc archive')
            used, count = newc(chunk[pos:])
            pos += used; archives += 1; entries += count
            require(archives <= 128 and entries <= 262144, 'INVALID_IMAGE', 'archive/entry bound')

    pos = 0
    while pos < len(data):
        require(len(segments) < 256, 'INVALID_IMAGE', 'initramfs segment bound')
        start = pos
        if data[pos] == 0:
            while pos < len(data) and data[pos] == 0:
                pos += 1
            account(data[start:pos])
            continue
        version = None
        if data[pos:pos+4] == b'\x28\xb5\x2f\xfd':
            decoded, used, version = zstd_frame(data[pos:], limit-decoded_bytes)
            kind = 'zstd'
            before = archives
            cpio_sequence(decoded)
            require(archives > before, 'INVALID_IMAGE', 'compressed frame contains no archive')
        elif data[pos:pos+2] == b'\x1f\x8b':
            decoder = zlib.decompressobj(31)
            try:
                decoded = decoder.decompress(data[pos:], limit-decoded_bytes+1)
            except zlib.error as exc:
                raise Outcome('INVALID_IMAGE', 'gzip initramfs stream/CRC') from exc
            require(len(decoded) <= limit-decoded_bytes and not decoder.unconsumed_tail,
                    'INVALID_IMAGE', 'initramfs expansion limit')
            require(decoder.eof, 'INVALID_IMAGE', 'truncated gzip initramfs')
            used = len(data)-pos-len(decoder.unused_data); kind = 'gzip'
            before = archives
            cpio_sequence(decoded)
            require(archives > before, 'INVALID_IMAGE', 'compressed frame contains no archive')
        else:
            require(pos % 4 == 0, 'INVALID_IMAGE', 'unaligned uncompressed newc archive')
            used, count = newc(data[pos:])
            decoded = data[pos:pos+used]; kind = 'newc'
            archives += 1; entries += count
            require(archives <= 128 and entries <= 262144, 'INVALID_IMAGE', 'archive/entry bound')
        account(decoded)
        segments.append(dict(offset=start, stored_bytes=used, format=kind,
            stored_sha256=hashlib.sha256(data[start:start+used]).hexdigest(),
            decoded_bytes=len(decoded), decoded_sha256=hashlib.sha256(decoded).hexdigest(),
            decoder_version=version))
        pos += used
    require(archives > 0, 'INVALID_IMAGE', 'no newc archives')
    return dict(archives=archives, entries=entries, segments=segments,
        stored_sha256=hashlib.sha256(data).hexdigest(), decoded_sha256=digest.hexdigest(),
        decoded_bytes=decoded_bytes, window_limit_bytes=64*1024*1024,
        validation='complete frames and newc structure; not executable semantics')
