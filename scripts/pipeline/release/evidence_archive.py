"""HGC-04 v1 bounded JSON/ZIP handling; never extractall or follow links."""
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import struct
import zipfile
import zlib

SCHEMA_VERSION = 1
LIMITS = dict(archive_bytes=64 * 1024 * 1024, file_bytes=32 * 1024 * 1024,
              expanded_bytes=128 * 1024 * 1024, members=4096, depth=16,
              path_bytes=512, json_bytes=4 * 1024 * 1024)


class InvalidEvidence(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise InvalidEvidence(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def json_value(raw):
    require(type(raw) is bytes and len(raw) <= LIMITS['json_bytes'], 'JSON size/type limit')

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result

    def constant(_):
        raise InvalidEvidence('non-finite JSON value')

    try:
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise InvalidEvidence('invalid JSON: ' + str(error)) from error
    return result


def document(raw):
    result = json_value(raw)
    require(type(result) is dict, 'JSON object required')
    return result


def fields(value, names, label):
    require(type(value) is dict and set(value) == set(names.split()), label + ': fields differ')


def positive(value, label):
    require(type(value) is int and value > 0, label + ': positive integer required')


def digest(value, label='digest', length=64):
    require(type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value), label + ': invalid digest')


def safe_path(value):
    require(type(value) is str and 0 < len(value.encode('utf-8')) <= LIMITS['path_bytes'], 'path size/type limit')
    parts = value.split('/')
    require(len(parts) <= LIMITS['depth'] and all(p not in ('', '.', '..') for p in parts)
            and re.fullmatch(r'[A-Za-z0-9_./+-]+', value) is not None
            and not value.startswith('/'), 'unsafe path')
    return value


def reject_secrets(path, raw):
    parts = path.lower().split('/')
    require(not set(parts) & {'.aws', '.ssh', '.git', '.cache', 'cache', 'credentials'}
            and not any(part.endswith('.rsa') or part in ('id_rsa', 'id_ed25519') for part in parts),
            'private key/cache/credential path')
    require(not any(marker in raw for marker in (b'-----BEGIN PRIVATE KEY', b'-----BEGIN RSA PRIVATE KEY',
                b'-----BEGIN EC PRIVATE KEY', b'-----BEGIN OPENSSH PRIVATE KEY', b'-----BEGIN ENCRYPTED PRIVATE KEY')),
            'private key material')


class ExpansionBudget:
    def __init__(self):
        self.members = 0
        self.bytes = 0

    def member(self):
        self.members += 1
        require(self.members <= LIMITS['members'], 'member count limit')

    def consume(self, count):
        self.bytes += count
        require(self.bytes <= LIMITS['expanded_bytes'], 'aggregate expansion limit')


def read_zip(raw, *, budget=None, custody=False):
    require(type(raw) is bytes and len(raw) <= LIMITS['archive_bytes'], 'archive size/type limit')
    budget = budget or ExpansionBudget()
    result, folded, ranges = {}, set(), []
    # Bound the central-directory parser itself, before ZipFile allocates entries.
    require(len(raw) >= 22 and raw[-22:-18] == b'PK\x05\x06', 'ZIP end record/comments unsupported')
    end = struct.unpack('<4s4H2IH', raw[-22:])
    require(end[1] == end[2] == end[7] == 0 and end[3] == end[4]
            and end[4] <= LIMITS['members'] and end[5] + end[6] == len(raw) - 22,
            'ZIP directory count/size/multidisk limit')
    position, count = end[6], 0
    while position < len(raw) - 22:
        require(raw[position:position + 4] == b'PK\x01\x02' and position + 46 <= len(raw) - 22,
                'invalid ZIP central directory')
        name_size, extra_size, comment_size = struct.unpack('<3H', raw[position + 28:position + 34])
        position += 46 + name_size + extra_size + comment_size
        count += 1
        require(count <= LIMITS['members'] and position <= len(raw) - 22, 'actual ZIP directory count/size limit')
    require(count == end[4], 'ZIP declared/actual member count differs')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            require(not archive.comment, 'ZIP comments unsupported')
            infos = archive.infolist()
            require(len(infos) <= LIMITS['members'], 'member count limit')
            if custody:
                require([i.filename for i in infos] == sorted(i.filename for i in infos), 'custody member order')
            for info in infos:
                budget.member()
                name = safe_path(info.filename)
                require(name.casefold() not in folded, 'duplicate/colliding ZIP path')
                folded.add(name.casefold())
                require(not any(name.startswith(other + '/') or other.startswith(name + '/') for other in result),
                        'file/directory path collision')
                mode = info.external_attr >> 16
                require(not info.is_dir() and stat.S_IFMT(mode) in (0, stat.S_IFREG)
                        and not info.external_attr & 0x10, 'ZIP member is not a regular file')
                require(not info.extra and not info.comment and not info.flag_bits & 1,
                        'ZIP links/extensions/encryption unsupported')
                require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), 'unsupported ZIP compression')
                require(0 <= info.file_size <= LIMITS['file_bytes'], 'declared file size limit')
                if custody:
                    require(info.compress_type == zipfile.ZIP_STORED and info.date_time == (1980, 1, 1, 0, 0, 0)
                            and mode == stat.S_IFREG | 0o644 and info.create_system == 3,
                            'custody ZIP metadata differs')
                header = info.header_offset
                require(0 <= header and header + 30 <= archive.start_dir, 'ZIP local header bounds')
                local = struct.unpack('<4s5H3I2H', raw[header:header + 30])
                require(local[0] == b'PK\x03\x04' and local[2] == info.flag_bits and local[3] == info.compress_type
                        and local[10] == 0, 'ZIP local header/extensions differ')
                start = header + 30 + local[9]
                stop = start + info.compress_size
                require(start <= stop <= archive.start_dir and info.compress_size <= LIMITS['archive_bytes'], 'ZIP compressed bounds')
                require(raw[header + 30:start].decode('utf-8' if info.flag_bits & 0x800 else 'cp437') == name,
                        'ZIP local/central paths differ')
                member_end = stop
                if info.flag_bits & 8:
                    descriptor_start = stop + (4 if raw[stop:stop + 4] == b'PK\x07\x08' else 0)
                    member_end = descriptor_start + 12
                    require(member_end <= archive.start_dir
                            and struct.unpack('<3I', raw[descriptor_start:member_end]) ==
                                (info.CRC, info.compress_size, info.file_size), 'ZIP data descriptor differs')
                else:
                    require(local[6:9] == (info.CRC, info.compress_size, info.file_size), 'ZIP local size/CRC differs')
                require(not any(header < b and a < member_end for a, b in ranges), 'overlapping ZIP members')
                ranges.append((header, member_end))
                chunks, actual = [], 0
                inflater = zlib.decompressobj(-15) if info.compress_type == zipfile.ZIP_DEFLATED else None
                for position in range(start, stop, 64 * 1024):
                    pending = raw[position:min(position + 64 * 1024, stop)]
                    while pending:
                        if inflater:
                            chunk = inflater.decompress(pending, min(64 * 1024, LIMITS['file_bytes'] - actual + 1))
                            pending = inflater.unconsumed_tail
                        else:
                            chunk, pending = pending, b''
                        actual += len(chunk)
                        budget.consume(len(chunk))
                        require(actual <= LIMITS['file_bytes'] and actual <= info.file_size, 'actual file size limit')
                        chunks.append(chunk)
                if inflater:
                    require(inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail, 'invalid deflate stream length')
                require(actual == info.file_size, 'ZIP member size differs')
                data = b''.join(chunks)
                require(zlib.crc32(data) & 0xffffffff == info.CRC, 'ZIP CRC differs')
                reject_secrets(name, data)
                result[name] = data
            cursor = 0
            for start, stop in sorted(ranges):
                require(start == cursor, 'unlisted ZIP data/prefix')
                cursor = stop
            require(cursor == archive.start_dir, 'unlisted ZIP data/suffix')
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, EOFError, OSError, zlib.error, UnicodeError, struct.error) as error:
        raise InvalidEvidence('invalid ZIP: ' + str(error)) from error
    return result


def make_zip(files):
    require(type(files) is dict and files, 'nonempty file map required')
    require(len(files) <= LIMITS['members'], 'member count limit')
    require(all(type(raw) is bytes and len(raw) <= LIMITS['file_bytes'] for raw in files.values()),
            'file size/type limit')
    # ZIP_STORED has no compression: reject oversized input before allocating it.
    require(sum(len(raw) + 2 * len(safe_path(name).encode()) + 76 for name, raw in files.items()) + 22
            <= LIMITS['archive_bytes'], 'archive size limit')
    output = io.BytesIO()
    folded = set()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name in sorted(files):
            safe_path(name)
            require(name.casefold() not in folded, 'colliding path')
            folded.add(name.casefold())
            raw = files[name]
            require(type(raw) is bytes, 'bytes required')
            reject_secrets(name, raw)
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, raw)
    raw = output.getvalue()
    read_zip(raw, custody=True)
    return raw


def inventory(files):
    return [dict(path=path, type='file', size=len(raw), sha256=sha256(raw)) for path, raw in sorted(files.items())]


def check_inventory(records, files):
    require(type(records) is list, 'inventory list required')
    for record in records:
        fields(record, 'path type size sha256', 'inventory')
        safe_path(record['path'])
        require(record['type'] == 'file' and type(record['size']) is int and record['size'] >= 0,
                'invalid inventory type/size')
        digest(record['sha256'])
    require(records == inventory(files), 'inventory bytes/set/order differ')


def extract_new(files, destination):
    """Reserve a previously absent leaf in a caller-owned private parent."""
    destination = Path(destination)
    require(destination.is_absolute(), 'absolute extraction destination required')
    for parent in (destination, *destination.parents):
        require(not parent.is_symlink(), 'symlink destination/ancestor')
    require(destination.parent.is_dir(), 'extraction parent missing')
    try:
        destination.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError as error:
        raise InvalidEvidence('extraction destination already exists') from error
    for name, raw in sorted(files.items()):
        path = destination / safe_path(name)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open('xb') as stream:
            stream.write(raw)
    return destination
