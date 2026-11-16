"""Bounded syntactic validation and explicit lab integrity checks; no authenticity claim."""
import hashlib
import struct
import re
import zlib
from block_reader import require, Outcome
from preboot import MAX_FILE


def sha(data):
    return hashlib.sha256(data).hexdigest()


def gunzip(data):
    try:
        d = zlib.decompressobj(31)
        out = d.decompress(data, MAX_FILE+1)
        require(len(out) <= MAX_FILE and not d.unconsumed_tail, 'INVALID_IMAGE', 'gzip expansion limit')
        require(d.eof and not d.unused_data, 'INVALID_IMAGE', 'truncated/trailing gzip data')
        return out
    except zlib.error as exc:
        raise Outcome('INVALID_IMAGE', 'gzip checksum/stream failure') from exc


def newc(data):
    """Consume one complete newc archive, including trailer; never extract it."""
    pos, entries = 0, 0
    while True:
        require(pos+110 <= len(data), 'INVALID_IMAGE', 'truncated newc header')
        header = data[pos:pos+110]
        require(header[:6] in (b'070701', b'070702'), 'INVALID_IMAGE', 'newc magic')
        require(re.fullmatch(b'[0-9a-fA-F]{104}', header[6:]) is not None,
                'INVALID_IMAGE', 'newc non-hex field')
        try:
            fields = [int(header[i:i+8], 16) for i in range(6, 110, 8)]
        except ValueError as exc:
            raise Outcome('INVALID_IMAGE', 'newc numeric field') from exc
        size, namesize, checksum = fields[6], fields[11], fields[12]
        require(0 < namesize <= 4096, 'INVALID_IMAGE', 'newc name length')
        start = pos+110
        end = start+namesize
        require(end <= len(data) and data[end-1] == 0 and b'\0' not in data[start:end-1],
                'INVALID_IMAGE', 'newc name terminator/bounds')
        name = data[start:end-1]
        payload = (end+3) & ~3
        stop = payload+size
        require(stop <= len(data), 'INVALID_IMAGE', 'truncated newc payload')
        require(not any(data[end:payload]), 'INVALID_IMAGE', 'nonzero newc name padding')
        if header[:6] == b'070702':
            require(sum(data[payload:stop]) & 0xffffffff == checksum, 'INVALID_IMAGE', 'newc CRC sum')
        else:
            require(checksum == 0, 'INVALID_IMAGE', 'nonzero newc checksum')
        pos = (stop+3) & ~3
        require(pos <= len(data), 'INVALID_IMAGE', 'newc alignment truncated')
        require(not any(data[stop:pos]), 'INVALID_IMAGE', 'nonzero newc payload padding')
        entries += 1
        require(entries <= 262144, 'INVALID_IMAGE', 'newc entry bound')
        if name == b'TRAILER!!!':
            require(size == 0, 'INVALID_IMAGE', 'nonempty newc trailer')
            return pos, entries


def initramfs(data):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'cm5-phase10f1'))
    from initramfs_format import validate_initramfs
    return validate_initramfs(data, newc, MAX_FILE)


def dtb(data):
    require(len(data) >= 40, 'INVALID_IMAGE', 'short DTB')
    magic, total, tree, strings, reserve, ver, compat, cpu, ns, nt = struct.unpack_from('>10I', data)
    require(magic == 0xd00dfeed and total == len(data), 'INVALID_IMAGE', 'DTB magic/total length')
    require(ver == 17 and compat <= 17, 'UNSUPPORTED', 'DTB version')
    require(tree % 4 == 0 and reserve % 8 == 0 and tree >= 40 and strings >= 40 and reserve >= 40 and
            tree+nt <= total and strings+ns <= total, 'INVALID_IMAGE', 'DTB block bounds')
    r = reserve
    while True:
        require(r+16 <= total, 'INVALID_IMAGE', 'DTB reserve terminator')
        address, length = struct.unpack_from('>QQ', data, r)
        r += 16
        if address == length == 0:
            break
    spans = sorted([(0, 40), (reserve, r), (tree, tree+nt), (strings, strings+ns)])
    require(all(a[1] <= b[0] for a,b in zip(spans, spans[1:])), 'INVALID_IMAGE', 'DTB overlapping blocks')
    pos, depth, roots, ended = tree, 0, 0, False
    while pos < tree+nt:
        require(pos+4 <= tree+nt, 'INVALID_IMAGE', 'DTB token bounds')
        token = struct.unpack_from('>I', data, pos)[0]
        pos += 4
        if token == 1:
            end = data.find(b'\0', pos, tree+nt)
            require(end >= pos, 'INVALID_IMAGE', 'DTB node name')
            if depth == 0:
                roots += 1
                require(end == pos and roots == 1, 'INVALID_IMAGE', 'DTB root node')
            depth += 1
            require(depth <= 256, 'INVALID_IMAGE', 'DTB depth')
            pos = (end+4) & ~3
        elif token == 2:
            require(depth > 0, 'INVALID_IMAGE', 'DTB unbalanced end node')
            depth -= 1
        elif token == 3:
            require(depth > 0 and pos+8 <= tree+nt, 'INVALID_IMAGE', 'DTB property header')
            size, name = struct.unpack_from('>II', data, pos)
            pos += 8
            require(name < ns and data.find(b'\0', strings+name, strings+ns) >= 0 and pos+size <= tree+nt,
                    'INVALID_IMAGE', 'DTB property bounds/name')
            pos = (pos+size+3) & ~3
        elif token == 4:
            pass
        elif token == 9:
            require(depth == 0 and roots == 1 and pos == tree+nt, 'INVALID_IMAGE', 'DTB END placement')
            ended = True
        else:
            raise Outcome('INVALID_IMAGE', 'DTB unknown token')
    require(ended, 'INVALID_IMAGE', 'DTB missing END')
    return dict(validation='DTB block/token structure; bindings and overlay operations not validated')


def validate(kind, data):
    if kind == 'kernel':
        decoded = gunzip(data) if data.startswith(b'\x1f\x8b') else data
        require(len(decoded) >= 64 and decoded[56:60] == b'ARM\x64', 'INVALID_IMAGE', 'ARM64 Image magic')
        size = struct.unpack_from('<Q', decoded, 16)[0]
        # image_size is the memory footprint, including zero-filled space;
        # it is not the number of bytes stored in the Image file.
        require(size != 0, 'UNSUPPORTED', 'legacy zero ARM64 image_size')
        require(64 <= size <= MAX_FILE and len(decoded) <= MAX_FILE, 'INVALID_IMAGE', 'ARM64 memory/file bound')
        offset, flags = struct.unpack_from('<Q', decoded, 8)[0], struct.unpack_from('<Q', decoded, 24)[0]
        require(offset <= MAX_FILE and not flags & 1, 'UNSUPPORTED', 'ARM64 offset/big-endian image')
        return dict(memory_image_bytes=size, text_offset=offset, decoded_sha256=sha(decoded), decoded_bytes=len(decoded),
                    validation='gzip stream/CRC when compressed, ARM64 header/memory bounds; instruction semantics unknown')
    if kind == 'initramfs':
        return initramfs(data)
    if kind == 'dtb':
        return dtb(data)
    require(0 < len(data) <= 65536 and b'\0' not in data, 'INVALID_IMAGE', 'cmdline bounds/NUL')
    try:
        text = data.decode('ascii')
    except UnicodeError as exc:
        raise Outcome('INVALID_IMAGE', 'non-ASCII cmdline') from exc
    require('\n' not in text.rstrip('\r\n') and '\r' not in text.rstrip('\r\n'), 'INVALID_IMAGE', 'multiline cmdline')
    return dict(validation='single ASCII command line')
