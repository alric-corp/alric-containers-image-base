"""Fail-closed controls for the multi-source package model.

Wolfi is the default. Alpine v3.24 is an explicit exception authorised only for
the frameworks the policy names. Every test here must FAIL CLOSED: an
unauthorised source, release, repository, keyring or key may never produce a
valid composition, and a package present in the lock may never be missing from
the SBOM. The positive cases only confirm the real catalog satisfies it.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.pipeline.artifacts import sbom_completeness
from scripts.pipeline.governance import source_trust

ROOT = Path(__file__).resolve().parents[4]
ALPINE_KEYS = ('melange/keys/alpine-devel@lists.alpinelinux.org-6165ee59.rsa.pub',
               'melange/keys/alpine-devel@lists.alpinelinux.org-616ae350.rsa.pub')
WOLFI_KEY = 'melange/keys/wolfi-signing.rsa.pub'
ALPINE_ORIGIN = 'https://alpinelinux.org/keys/'


class CompositionTrustTests(unittest.TestCase):
    """The repositories/keyring a framework resolves to must be authorised."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='source-trust-')
        self.root = Path(self.directory) / 'repo'
        (self.root / 'policies').mkdir(parents=True)
        for relative in ('distroless', 'frameworks', 'melange/keys'):
            shutil.copytree(ROOT / relative, self.root / relative)
        shutil.copytree(ROOT / 'policies/sources', self.root / 'policies/sources')

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def write(self, relative, text):
        (self.root / relative).write_text(text)

    def assertFailsClosed(self, needle=''):
        errors = source_trust.framework_errors(self.root)
        self.assertTrue(errors, 'expected the composition to be rejected')
        if needle:
            self.assertTrue(any(needle in error for error in errors), errors)
        with self.assertRaises(ValueError):
            source_trust.require_sources(self.root)

    def test_real_catalog_satisfies_the_contract(self):
        self.assertEqual(source_trust.framework_errors(self.root), [])

    def test_catalog_is_sixteen_wolfi_and_two_alpine(self):
        report = source_trust.inventory(self.root)
        counted = {}
        for entry in report.values():
            counted[entry['source']] = counted.get(entry['source'], 0) + 1
        self.assertEqual(counted, {'wolfi': 16, 'alpine-3.24': 2})
        self.assertEqual({name for name, entry in report.items()
                          if entry['source'] == 'alpine-3.24'}, {'dotnet8', 'dotnet8-dev'})

    def test_alpine_edge_is_rejected(self):
        self.write('distroless/sources/alpine-3.24.yaml',
                   'include: distroless/image-base.yaml\ncontents:\n  repositories:\n'
                   '    - https://dl-cdn.alpinelinux.org/alpine/edge/main\n  keyring:\n'
                   f'    - {ALPINE_KEYS[0]}\n')
        self.assertFailsClosed('do not match any declared source')

    def test_unauthorised_alpine_release_is_rejected(self):
        self.write('distroless/sources/alpine-3.24.yaml',
                   'include: distroless/image-base.yaml\ncontents:\n  repositories:\n'
                   '    - https://dl-cdn.alpinelinux.org/alpine/v3.23/main\n'
                   '    - https://dl-cdn.alpinelinux.org/alpine/v3.23/community\n  keyring:\n'
                   f'    - {ALPINE_KEYS[0]}\n    - {ALPINE_KEYS[1]}\n')
        self.assertFailsClosed('do not match any declared source')

    def test_arbitrary_repository_is_rejected(self):
        self.write('frameworks/go1-26.yaml',
                   'include: distroless/runtime.yaml\ncontents:\n  repositories:\n'
                   '    - https://packages.example.invalid/os\n  packages:\n    - go-1.26\n')
        self.assertFailsClosed('do not match any declared source')

    def test_arbitrary_keyring_is_rejected(self):
        self.write('frameworks/go1-26.yaml',
                   'include: distroless/runtime.yaml\ncontents:\n  keyring:\n'
                   '    - melange/keys/attacker.rsa.pub\n  packages:\n    - go-1.26\n')
        self.assertFailsClosed('do not match any declared source')

    def test_unknown_source_in_policy_is_rejected(self):
        policy = json.loads((self.root / source_trust.POLICY).read_text())
        policy['framework_sources']['dotnet8']['source'] = 'alpine-3.99'
        (self.root / source_trust.POLICY).write_text(json.dumps(policy))
        self.assertFailsClosed('unknown source')

    def test_unauthorised_framework_using_alpine_is_rejected(self):
        self.write('frameworks/nodejs22.yaml',
                   'include: distroless/runtime-alpine-3.24.yaml\ncontents:\n'
                   '  packages:\n    - nodejs-22\n')
        self.assertFailsClosed("authorises 'wolfi'")

    def test_wolfi_repository_with_alpine_key_is_rejected(self):
        self.write('distroless/sources/wolfi.yaml',
                   'include: distroless/image-base.yaml\ncontents:\n  repositories:\n'
                   f'    - https://packages.wolfi.dev/os\n  keyring:\n    - {ALPINE_KEYS[0]}\n')
        self.assertFailsClosed('do not match any declared source')

    def test_alpine_repository_with_wolfi_key_is_rejected(self):
        self.write('distroless/sources/alpine-3.24.yaml',
                   'include: distroless/image-base.yaml\ncontents:\n  repositories:\n'
                   '    - https://dl-cdn.alpinelinux.org/alpine/v3.24/main\n'
                   '    - https://dl-cdn.alpinelinux.org/alpine/v3.24/community\n  keyring:\n'
                   f'    - {WOLFI_KEY}\n')
        self.assertFailsClosed('do not match any declared source')

    def test_framework_without_any_source_is_rejected(self):
        self.write('frameworks/go1-26.yaml', 'contents:\n  packages:\n    - go-1.26\n')
        self.assertFailsClosed('no package source resolved')

    def test_tampered_pinned_key_is_rejected(self):
        key = self.root / ALPINE_KEYS[0]
        key.write_bytes(key.read_bytes().replace(b'MII', b'MIj', 1))
        self.assertFailsClosed('SHA-256 mismatch')

    def test_include_escaping_the_repository_is_rejected(self):
        self.write('frameworks/go1-26.yaml', 'include: ../../../etc/passwd\n')
        self.assertFailsClosed('escapes the repository')

    def test_include_as_a_list_is_rejected(self):
        # apko itself refuses a list; governance must not accept what apko cannot build.
        self.write('frameworks/go1-26.yaml',
                   'include:\n  - distroless/sources/wolfi.yaml\n  - distroless/runtime.yaml\n')
        self.assertFailsClosed('single string')

    def test_missing_source_policy_is_rejected(self):
        (self.root / source_trust.POLICY).unlink()
        self.assertFailsClosed('invalid or missing source policy')


def key(path, url=None):
    return {'name': path, 'url': url or path, 'content': (ROOT / path).read_text()}


def lock(keys):
    return {'contents': {'keyring': list(keys), 'packages': []}}


class EffectiveKeyringTests(unittest.TestCase):
    """Apko unions network-discovered keys; only pinned ones may survive."""

    def alpine(self):
        """What a real build produces: 2 declared + 2 discovered, same bytes."""
        return lock([key(ALPINE_KEYS[0], ALPINE_ORIGIN + 'a.rsa.pub'),
                     key(ALPINE_KEYS[1], ALPINE_ORIGIN + 'b.rsa.pub'),
                     key(ALPINE_KEYS[0]), key(ALPINE_KEYS[1])])

    def assertFailsClosed(self, document, framework='dotnet8', needle=''):
        problems = source_trust.keyring_errors(document, framework, ROOT)
        self.assertTrue(problems, 'expected the effective keyring to be rejected')
        if needle:
            self.assertTrue(any(needle in p for p in problems), problems)
        with self.assertRaises(ValueError):
            source_trust.require_keyring(document, framework, ROOT)

    def test_real_effective_keyring_is_accepted(self):
        self.assertEqual(source_trust.keyring_errors(self.alpine(), 'dotnet8', ROOT), [])

    def test_new_unpinned_key_is_rejected(self):
        document = self.alpine()
        document['contents']['keyring'].append(
            {'name': 'alpine-devel@lists.alpinelinux.org-NEW.rsa.pub',
             'url': ALPINE_ORIGIN + 'new.rsa.pub',
             'content': '-----BEGIN PUBLIC KEY-----\nQUJD\n-----END PUBLIC KEY-----\n'})
        self.assertFailsClosed(document, needle='is not pinned')

    def test_altered_key_hash_is_rejected(self):
        document = self.alpine()
        document['contents']['keyring'][0]['content'] += 'tampered\n'
        self.assertFailsClosed(document, needle='is not pinned')

    def test_removed_pinned_key_is_rejected(self):
        self.assertFailsClosed(lock([key(ALPINE_KEYS[0])]),
                               needle='absent from the effective keyring')

    def test_key_discovered_from_another_origin_is_rejected(self):
        document = self.alpine()
        document['contents']['keyring'][0]['url'] = 'https://mirror.example.invalid/keys/a.rsa.pub'
        self.assertFailsClosed(document, needle='origin not allowed')

    def test_empty_keyring_is_rejected(self):
        self.assertFailsClosed(lock([]), needle='empty')

    def test_wolfi_key_in_an_alpine_build_is_rejected(self):
        self.assertFailsClosed(lock([key(WOLFI_KEY)]), needle='is not pinned')

    def test_alpine_key_in_a_wolfi_build_is_rejected(self):
        self.assertFailsClosed(lock([key(ALPINE_KEYS[0])]), framework='go1-26',
                               needle='is not pinned')

    def test_keyring_entry_without_content_is_rejected(self):
        document = self.alpine()
        document['contents']['keyring'][0]['content'] = ''
        self.assertFailsClosed(document, needle='has no content')


class SbomCompletenessTests(unittest.TestCase):
    """Every locked package must be represented in the SPDX of its architecture."""

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='sbom-completeness-')
        self.layout = Path(self.directory) / 'image.oci'
        (self.layout / 'sbom').mkdir(parents=True)
        packages = [
            {'name': 'musl', 'version': '1.2.6-r2', 'architecture': arch,
             'url': f'https://dl-cdn.alpinelinux.org/alpine/v3.24/main/{arch}/musl-1.2.6-r2.apk'}
            for arch in ('x86_64', 'aarch64')]
        (self.layout / 'apko.lock.json').write_text(json.dumps(
            {'contents': {'keyring': [], 'packages': packages}}))
        for filename in sbom_completeness.ARCHS.values():
            (self.layout / 'sbom' / filename).write_text(json.dumps(
                {'packages': [], 'relationships': []}))

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_apko_output_alone_is_incomplete(self):
        problems = sbom_completeness.errors(self.layout)
        self.assertTrue(any('not represented in the SBOM' in p for p in problems), problems)

    def test_completion_represents_every_locked_package(self):
        sbom_completeness.complete(self.layout, 'dotnet8', ROOT)
        self.assertEqual(sbom_completeness.errors(self.layout), [])
        document = json.loads((self.layout / 'sbom' / 'sbom-x86_64.spdx.json').read_text())
        entry = next(p for p in document['packages'] if p['name'] == 'musl')
        purl = next(r['referenceLocator'] for r in entry['externalRefs']
                    if r['referenceType'] == 'purl')
        self.assertEqual(purl, 'pkg:apk/alpine/musl@1.2.6-r2?arch=x86_64')
        self.assertTrue(entry['downloadLocation'].startswith('https://dl-cdn.alpinelinux.org/'))
        self.assertEqual(entry['supplier'], 'Organization: alpine')

    def test_package_missing_from_the_sbom_is_detected(self):
        sbom_completeness.complete(self.layout, 'dotnet8', ROOT)
        path = self.layout / 'sbom' / 'sbom-x86_64.spdx.json'
        document = json.loads(path.read_text())
        document['packages'] = [p for p in document['packages'] if p['name'] != 'musl']
        path.write_text(json.dumps(document))
        self.assertTrue(any('musl@1.2.6-r2' in p for p in sbom_completeness.errors(self.layout)))

    def test_wolfi_framework_keeps_its_own_namespace(self):
        sbom_completeness.complete(self.layout, 'go1-26', ROOT)
        document = json.loads((self.layout / 'sbom' / 'sbom-x86_64.spdx.json').read_text())
        purl = next(r['referenceLocator'] for p in document['packages']
                    for r in p.get('externalRefs', []) if r['referenceType'] == 'purl')
        self.assertTrue(purl.startswith('pkg:apk/wolfi/'), purl)


if __name__ == '__main__':
    unittest.main()
