import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline.governance import pin_inventory as inventory


class VersionedImagePinsTests(unittest.TestCase):
    def test_tagged_digest_keeps_registry_name_and_is_checked_without_losing_tag(self):
        reference = 'localhost:5000/skopeo/stable:v1.22.2-immutable@sha256:' + 'a' * 64
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'Makefile'
            path.write_text(reference)
            with patch.object(inventory, 'ROOT', root):
                entries = inventory.pins([path])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['name'], 'localhost:5000/skopeo/stable')
        self.assertEqual(entries[0]['tag'], 'v1.22.2-immutable')

        def run(argv, **kwargs):
            self.assertEqual(argv[-1], reference)
            return subprocess.CompletedProcess(argv, 0, '{}', '')

        self.assertTrue(inventory.availability(entries, run)[0]['available'])

    def test_actual_skopeo_pins_are_both_visible_and_managed(self):
        paths = inventory.scanned_files()
        entries = inventory.coverage(
            inventory.pins(paths), inventory.renovate_matches(
                json.loads((inventory.ROOT / 'renovate.json').read_text()), paths), set())
        skopeo = [entry for entry in entries if entry['name'] == 'quay.io/skopeo/stable']
        self.assertEqual(len(skopeo), 2)
        self.assertTrue(all(entry['tag'].endswith('-immutable') for entry in skopeo))
        self.assertTrue(all(entry['managers'] == ['renovate'] for entry in skopeo))
        self.assertEqual(inventory.consistency(skopeo), [])
