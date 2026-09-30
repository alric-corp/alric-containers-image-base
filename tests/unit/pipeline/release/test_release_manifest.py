"""Bind actual publication evidence to the release manifest, including retries."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.pipeline.release import release_manifest as release
from tests.unit.pipeline.consumer_apps import test_inventory as publication_fixture


class ManifestTests(unittest.TestCase):
    def setUp(self):
        fixture = publication_fixture.InventoryTests()
        fixture.setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = fixture.run['id']
        self.revision = fixture.run['head_sha']
        self.frameworks = list(fixture.files)
        for name, files in fixture.files.items():
            files = dict(files)
            expected = json.loads(files['image.oci/validated-index.json'])
            sboms, published = [], []
            for path, subject in [('sbom-index', expected['digest']),
                                  ('sbom-x86_64', expected['platforms']['linux/amd64']),
                                  ('sbom-aarch64', expected['platforms']['linux/arm64'])]:
                raw = json.dumps({'spdxVersion': 'SPDX-2.3', 'documentDescribes': ['SPDXRef-root'],
                    'packages': [{'SPDXID': 'SPDXRef-root', 'checksums': [
                        {'algorithm': 'SHA256', 'checksumValue': subject[7:]}]}]}).encode()
                record = {'path': f'sbom/{path}.spdx.json', 'subject': subject,
                          'sha256': hashlib.sha256(raw).hexdigest()}
                files['image.oci/'+record['path']] = raw
                sboms.append(record)
                published.append(dict(record, image_ref=f'{release.registry("DEV")}/image-base-{name}@{subject}', attested=True))
            expected['sboms'] = sboms
            files['image.oci/validated-index.json'] = json.dumps(expected).encode()
            files['sbom-publication.json'] = json.dumps(published).encode()
            proof = json.loads(files['publication-evidence.json'])
            proof['image_ref'] = f'{release.registry("DEV")}/image-base-{name}@{expected["digest"]}'
            files['publication-evidence.json'] = json.dumps(proof).encode()
            files['candidate-identity.json'] = json.dumps({'run_id':self.run, 'attempt':1,
                'source_sha':self.revision, 'digest':expected['digest'],
                'tag':f'300926-0000-r{self.run}-a1'}).encode()
            root = self.root/f'publication-{name}-1'
            for path, raw in files.items():
                output=root/path; output.parent.mkdir(parents=True,exist_ok=True); output.write_bytes(raw)

    def create(self):
        return release.from_publications(self.root, self.frameworks, self.run, 1, self.revision)

    def modify(self, path, fn):
        path = self.root/'publication-go1-26-1'/path
        value=json.loads(path.read_text()); fn(value); path.write_text(json.dumps(value))

    def test_full_catalog_serializes_into_nine_complete_consumer_units(self):
        m=self.create()
        self.assertEqual(len(m['images']),16)
        self.assertEqual(len(m['units']),9)
        self.assertEqual(release.validate(json.loads(release.canonical(m))),m)
        self.assertEqual(m['source_registry'],release.registry('DEV'))

    def test_changed_index_blocks_manifest(self):
        self.modify('image.oci/validated-index.json', lambda v: v.update(digest='sha256:'+'f'*64))
        with self.assertRaises(ValueError): self.create()

    def test_other_attempt_identity_is_rejected(self):
        self.modify('candidate-identity.json', lambda v: v.update(attempt=2))
        with self.assertRaises(ValueError): self.create()

    def test_gate_for_different_dev_digest_cannot_authorize_runtime(self):
        self.modify('runtime-gate-result.json', lambda v: v.update(dev_index_digest='sha256:'+'f'*64))
        with self.assertRaises(ValueError): self.create()

    def test_changed_original_sbom_cannot_become_release_evidence(self):
        self.modify('image.oci/sbom/sbom-index.spdx.json', lambda v: v.update(spdxVersion='tampered'))
        with self.assertRaises(ValueError): self.create()

    def test_missing_publication_attempt_is_not_substituted(self):
        with self.assertRaises(FileNotFoundError):
            release.from_publications(self.root,self.frameworks,self.run,2,self.revision)

    def test_an_unattested_sbom_blocks_manifest(self):
        self.modify('sbom-publication.json', lambda v: v[0].update(attested=False))
        with self.assertRaises(ValueError): self.create()


if __name__ == '__main__':
    unittest.main()
