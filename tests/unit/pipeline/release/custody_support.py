"""TEST_ONLY RSA-PSS trust adapter. Never imported by production code."""
import base64
from pathlib import Path
import subprocess
import tempfile

from scripts.pipeline.release.evidence_archive import canonical, document, fields, read_zip, require, sha256
from scripts.pipeline.release.evidence_custody import (
    Authentication, CORE, ExpectedIdentity, TrustPolicy, VERIFIER_COMMIT,
    VERIFIER_PATH, VERIFIER_REPOSITORY, VERIFIER_SHA256, VerifierAuthorization,
    freeze_commit, manifest_bytes, prepare_payload, store_payload,
)

FIXTURE = Path(__file__).resolve().parents[3] / 'fixtures/hgc04'
POLICY_ID = 'HGC04-OFFLINE-TEST-V1'
ORIGINAL_SHA256 = {
    'melange-repo': 'eaa8c662e7f91d37ba4e9bde024309f3fea5116ed7eb6ef7f53c137c1f436d99',
    'melange-reproduction-reference': 'c0e9b871ff0a24f7b5dcfd947b056a47b89a49fdb04943d23f4718b5a31b0964',
    'melange-reproducibility': 'cc07c1ef2391bf6bd9097c2a74fe2b870fb535bcbe54cb3349db2c6a7ed2fdba',
}


def fixture_inputs():
    zips = {name: (FIXTURE / (name + '.zip')).read_bytes() for name in CORE}
    require({name: sha256(raw) for name, raw in zips.items()} == ORIGINAL_SHA256, 'historical fixture ZIP bytes changed')
    materials = read_zip((FIXTURE / 'materials.zip').read_bytes())
    origins = document((FIXTURE / 'origins.json').read_bytes())
    expected = ExpectedIdentity((FIXTURE / 'expected.json').read_bytes())
    return zips, materials, origins, expected


def prepared_fixture():
    zips, materials, origins, expected = fixture_inputs()
    return prepare_payload(zips, materials, origins, expected, POLICY_ID), expected


class TestSigner:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='hgc04-test-key-')
        self.root = Path(self.temporary.name)
        self.private = self.root / 'discarded-private.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
                        '-out', str(self.private)], check=True, capture_output=True, timeout=30)
        self.public = subprocess.run(['openssl', 'pkey', '-in', str(self.private), '-pubout'],
                                     check=True, capture_output=True, timeout=10).stdout

    def close(self):
        self.temporary.cleanup()

    def policy(self):
        return TrustPolicy(POLICY_ID, 'TEST_ONLY', self.public,
            VerifierAuthorization(VERIFIER_REPOSITORY, VERIFIER_COMMIT, VERIFIER_PATH, VERIFIER_SHA256))

    def sign(self, manifest):
        signature = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(self.private),
                '-sigopt', 'rsa_padding_mode:pss', '-sigopt', 'rsa_pss_saltlen:-1'],
            input=manifest, check=True, capture_output=True, timeout=10).stdout
        return canonical(dict(profile='TEST_ONLY_RSA_PSS_SHA256', trusted_key_sha256=sha256(self.public),
                              signature=base64.b64encode(signature).decode()))


class TestAuthenticator:
    def authenticate(self, manifest, bundle, policy, expected):
        value = document(bundle)
        fields(value, 'profile trusted_key_sha256 signature', 'TEST_ONLY bundle')
        require(value['profile'] == 'TEST_ONLY_RSA_PSS_SHA256' and policy.profile == 'TEST_ONLY'
                and value['trusted_key_sha256'] == sha256(policy.trusted_public_key), 'external test trust differs')
        signature = base64.b64decode(value['signature'], validate=True)
        with tempfile.TemporaryDirectory(prefix='hgc04-test-auth-') as temporary:
            root = Path(temporary)
            (root / 'trusted.pub').write_bytes(policy.trusted_public_key)
            (root / 'signature').write_bytes(signature)
            result = subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(root / 'trusted.pub'),
                '-signature', str(root / 'signature'), '-sigopt', 'rsa_padding_mode:pss', '-sigopt', 'rsa_pss_saltlen:-1'],
                input=manifest, capture_output=True, timeout=10)
        require(result.returncode == 0 and result.stdout.strip() == b'Verified OK', 'TEST_ONLY signature failed')
        return Authentication(policy.profile, sha256(manifest), sha256(expected.raw))


def frozen_fixture(store, prepared, expected, signer):
    stored = store_payload(store, prepared, expected)
    require(stored.object is not None, 'test payload creation failed')
    manifest = manifest_bytes(prepared, stored.object, expected)
    bundle = signer.sign(manifest)
    return freeze_commit(manifest, bundle, signer.policy(), expected, TestAuthenticator())
