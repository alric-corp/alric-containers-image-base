"""Bounded hostile-input handling for the outer envelope and original ZIPs."""
import io
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from scripts.pipeline.release.evidence_archive import (
    LIMITS, ExpansionBudget, InvalidEvidence, check_inventory, document,
    extract_new, inventory, make_zip, read_zip, safe_path,
)


def archive(entries, compression=zipfile.ZIP_DEFLATED):
    output = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(output, 'w', compression=compression) as stream:
            for name, raw, mode, extra in entries:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.compress_type = compression
                info.external_attr = mode << 16
                info.extra = extra
                stream.writestr(info, raw)
    return output.getvalue()


def regular(name, raw=b'original bytes\x00\xff'):
    return name, raw, stat.S_IFREG | 0o644, b''


class ArchiveTests(unittest.TestCase):
    def test_original_member_bytes_survive_both_supported_methods(self):
        expected = {'a/receipt.json': b'{ "b": 2, "a": 1 }\n', 'a/output.apk': bytes(range(256))}
        for method in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            with self.subTest(method=method):
                self.assertEqual(read_zip(archive([regular(k, v) for k, v in expected.items()], method)), expected)
        self.assertEqual(read_zip(make_zip(expected), custody=True), expected)

    def test_json_duplicate_keys_and_non_finite_values_are_rejected(self):
        for raw in (b'{"schema_version":1,"schema_version":1}', b'{"a":{"x":1,"x":2}}',
                    b'{"n":NaN}', b'{"n":Infinity}', b'[]', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(InvalidEvidence):
                document(raw)

    def test_json_byte_limit(self):
        with patch.dict(LIMITS, json_bytes=4), self.assertRaises(InvalidEvidence):
            document(b'{"a":1}')

    def test_absolute_traversal_and_ambiguous_paths_are_rejected(self):
        for path in ('/absolute', '../x', 'a/../../b', 'a/./b', 'a//b', 'a/',
                     'C:/drive', 'a\\b', './x', ''):
            with self.subTest(path=path), self.assertRaises(InvalidEvidence):
                read_zip(archive([regular(path)]))
        with self.assertRaises(InvalidEvidence):
            read_zip(archive([regular('a_b')]).replace(b'a_b', b'a\x00b'))

    def test_duplicate_casefold_and_file_directory_collisions(self):
        for names in (('x', 'x'), ('A', 'a'), ('parent', 'parent/child'), ('parent/child', 'parent')):
            with self.subTest(names=names), self.assertRaises(InvalidEvidence):
                read_zip(archive([regular(n) for n in names]))

    def test_symlinks_directories_and_special_types_are_rejected(self):
        for mode, name in ((stat.S_IFLNK, 'link'), (stat.S_IFDIR, 'directory/'),
                           (stat.S_IFIFO, 'fifo'), (stat.S_IFSOCK, 'socket'), (stat.S_IFCHR, 'device')):
            with self.subTest(mode=mode), self.assertRaises(InvalidEvidence):
                read_zip(archive([(name, b'target', mode | 0o777, b'')]))

    def test_link_extensions_comments_and_unsupported_compression_rejected(self):
        # ZIP has no portable hardlink type; v1 rejects all extra fields,
        # including Unix extensions that could carry link semantics.
        extra = struct.pack('<HH', 0x000d, 2) + b'xx'
        with self.assertRaises(InvalidEvidence):
            read_zip(archive([('link', b'target', stat.S_IFREG | 0o644, extra)]))
        raw = archive([regular('x')])
        with self.assertRaises(InvalidEvidence):
            read_zip(raw[:-2] + b'\x01\x00' + b'x')
        with self.assertRaises(InvalidEvidence):
            read_zip(archive([regular('x')], zipfile.ZIP_BZIP2))

    def test_private_key_and_cache_paths_or_material_are_rejected(self):
        for name, raw in (('cache/output', b'x'), ('.aws/config', b'x'), ('key.rsa', b'x'),
                          ('key.pem', b'-----BEGIN PRIVATE KEY-----\nnot a key\n')):
            with self.subTest(name=name), self.assertRaises(InvalidEvidence):
                read_zip(archive([regular(name, raw)]))

    def test_custody_envelope_metadata_and_order_are_enforced(self):
        with self.assertRaises(InvalidEvidence):
            read_zip(archive([regular('b'), regular('a')], zipfile.ZIP_STORED), custody=True)
        with self.assertRaises(InvalidEvidence):
            read_zip(archive([regular('a')]), custody=True)
        self.assertEqual(make_zip({'b': b'2', 'a': b'1'}), make_zip({'a': b'1', 'b': b'2'}))

    def test_archive_member_path_and_file_limits(self):
        raw = archive([regular('a', b'1234'), regular('b', b'5678')])
        for limit in ({'archive_bytes': len(raw) - 1}, {'members': 1}, {'file_bytes': 3}, {'expanded_bytes': 7}):
            with self.subTest(limit=limit), patch.dict(LIMITS, limit), self.assertRaises(InvalidEvidence):
                read_zip(raw)
        for path in ('/'.join(['x'] * 17), 'x' * 513):
            with self.subTest(path=path), self.assertRaises(InvalidEvidence):
                safe_path(path)

    def test_declared_size_cannot_hide_larger_actual_deflate_stream(self):
        raw = bytearray(archive([regular('x', b'A' * 4096)]))
        central = raw.index(b'PK\x01\x02')
        struct.pack_into('<I', raw, 22, 1)  # Local uncompressed size.
        struct.pack_into('<I', raw, central + 24, 1)
        with self.assertRaisesRegex(InvalidEvidence, 'actual file size'):
            read_zip(bytes(raw))

    def test_truncated_stream_and_crc_corruption_are_rejected(self):
        raw = bytearray(archive([regular('x')], zipfile.ZIP_STORED))
        raw[31] ^= 1
        with self.assertRaisesRegex(InvalidEvidence, 'CRC'):
            read_zip(bytes(raw))
        with self.assertRaises(InvalidEvidence):
            read_zip(bytes(raw[:-10]))

    def test_central_count_cannot_hide_entries_from_parser_budget(self):
        raw = bytearray(archive([regular('a'), regular('b')]))
        struct.pack_into('<2H', raw, len(raw) - 22 + 8, 1, 1)
        with self.assertRaisesRegex(InvalidEvidence, 'declared/actual member count'):
            read_zip(bytes(raw))

    def test_shared_expansion_budget_applies_to_internal_archives(self):
        inner = archive([regular('x', b'A' * 20)])
        outer = make_zip({'originals/a.zip': inner})
        budget = ExpansionBudget()
        with patch.dict(LIMITS, expanded_bytes=len(inner) + 19):
            recovered = read_zip(outer, budget=budget, custody=True)
            with self.assertRaisesRegex(InvalidEvidence, 'aggregate expansion'):
                read_zip(recovered['originals/a.zip'], budget=budget)
        budget = ExpansionBudget()
        with patch.dict(LIMITS, members=1):
            recovered = read_zip(outer, budget=budget, custody=True)
            with self.assertRaisesRegex(InvalidEvidence, 'member count'):
                read_zip(recovered['originals/a.zip'], budget=budget)

    def test_packer_rejects_oversized_input_before_zip_allocation(self):
        with patch.dict(LIMITS, archive_bytes=10), patch('zipfile.ZipFile', side_effect=AssertionError('allocated')):
            with self.assertRaises(InvalidEvidence):
                make_zip({'x': b'01234567890'})

    def test_inventory_exact_set_order_types_sizes_and_hashes(self):
        files = {'a': b'original', 'b': b'\x00\xff'}
        records = inventory(files)
        check_inventory(records, files)
        cases = [records[:-1], records + records[:1], list(reversed(records)),
                 [dict(records[0], size=True), records[1]], [dict(records[0], size=99), records[1]],
                 [dict(records[0], sha256='0' * 64), records[1]], [dict(records[0], type='symlink'), records[1]]]
        for records in cases:
            with self.subTest(records=records), self.assertRaises(InvalidEvidence):
                check_inventory(records, files)

    def test_extraction_requires_new_leaf_and_rejects_symlink_ancestors(self):
        with tempfile.TemporaryDirectory(prefix='hgc04-extract-') as temporary:
            root = Path(temporary).resolve()
            target = root / 'new'
            extract_new({'a/b': b'original'}, target)
            self.assertEqual((target / 'a/b').read_bytes(), b'original')
            with self.assertRaises(InvalidEvidence):
                extract_new({'a/b': b'replacement'}, target)
            self.assertEqual((target / 'a/b').read_bytes(), b'original')
            (root / 'link').symlink_to(target, target_is_directory=True)
            with self.assertRaises(InvalidEvidence):
                extract_new({'x': b'x'}, root / 'link/child')
            with self.assertRaises(InvalidEvidence):
                extract_new({}, Path('relative'))


if __name__ == '__main__':
    unittest.main()
