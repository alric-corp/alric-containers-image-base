"""Consumo auditado (examples/audited-consumer) contra CLIs simulados, sem rede.

aws, docker, cosign, gh e curl são stubs locais que leem um "mundo" JSON por
cenário: tags e seus digests ao longo do tempo, assinaturas, SBOM attestations
e provenance. O nível full-policy executa o ``verify_promotion`` real,
copiado para um checkout git temporário fixado por commit; o simplified
executa o ``scripts/verify-image.sh`` real fixado por sha256. A identidade
usada aqui é sintética: nada depende de conta, repository ou IDs do LAB.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / 'examples/audited-consumer'
GATE = EXAMPLE / 'audited_consumer.py'
CONSUME = EXAMPLE / 'consume.sh'
VERIFY_IMAGE = ROOT / 'scripts/verify-image.sh'
REGISTRY = '000000000000.dkr.ecr.sa-east-1.amazonaws.com'
SOURCE = 'example-org/example-image-base'
IDS = {'repository_id': '4242', 'owner_id': '4343'}
ISSUER = 'https://token.actions.githubusercontent.com'
WORKFLOW = '.github/workflows/build-base-images.yml'
IDENTITY = f'https://github.com/{SOURCE}/{WORKFLOW}@refs/heads/develop'
SOURCE_SHA = '1' * 40
FACTORY_FILES = ('scripts/__init__.py', 'scripts/pipeline/__init__.py', 'scripts/pipeline/release/__init__.py',
                 'scripts/pipeline/release/verify_promotion.py', 'scripts/pipeline/artifacts/__init__.py',
                 'scripts/pipeline/artifacts/image_reference.py')
# PATH fechado: somente stubs e estes utilitários. Nenhum aws/docker/cosign/gh/curl
# real é alcançável, inclusive quando um cenário remove um stub de propósito.
SYSTEM_TOOLS = ('git', 'bash', 'mkdir', 'mktemp', 'chmod', 'ls', 'cat', 'rm', 'head', 'seq', 'sleep', 'dirname',
                'env', 'basename')
STUBBED = ('aws', 'docker', 'cosign', 'gh', 'curl')


def digest(label):
    return 'sha256:' + hashlib.sha256(label.encode()).hexdigest()


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


RUNTIME, BUILD, RUNTIME_MOVED, UNSIGNED = (digest(x) for x in ('runtime-r1', 'build-r1', 'runtime-r2', 'unsigned'))

# Stub único: o nome do executável decide o comportamento. Formatos de saída
# do cosign/gh aqui são simulados; o gate só depende dos campos que os
# verificadores da Factory já usam (lista verificada, certificate IDs,
# statement.subject e invocationId).
STUB = r'''#!{python}
import json, os, sys, time
from pathlib import Path
GITHUB = 'https://token.actions.githubusercontent.com'
world = json.loads(Path(os.environ['AUDITED_STUB_WORLD']).read_text())
tool, args = Path(sys.argv[0]).name, sys.argv[1:]
with open(os.environ['AUDITED_STUB_LOG'], 'a') as log:
    log.write(json.dumps([tool] + args) + '\n')
time.sleep(world.get('delays', {}).get(tool, 0))
if tool in world.get('exit', {}):
    sys.exit(world['exit'][tool])

def option(name):
    return args[args.index(name) + 1] if name in args else None

def image(reference):
    reference = reference[len('oci://'):] if reference.startswith('oci://') else reference
    path, _, value = reference.partition('@')
    item = world['images'].get(value)
    if item is None or path != world['registry'] + '/' + item['repository']:
        return None, value
    return item, value

if tool == 'aws':
    if args[:2] == ['ecr', 'get-login-password']:
        print('stub-password'); sys.exit(0)
    repository, tag = option('--repository-name'), option('--image-ids').split('=', 1)[1]
    values = world['tags'].get(repository, {}).get(tag)
    if not values:
        print('An error occurred (ImageNotFoundException)', file=sys.stderr); sys.exit(254)
    counter = Path(os.environ['AUDITED_STUB_STATE']) / (repository + '.' + tag)
    calls = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(calls + 1))
    print(values[min(calls, len(values) - 1)]); sys.exit(0)

if tool == 'docker':
    if args[:1] == ['login']:
        sys.stdin.read(); sys.exit(0)
    if args[:3] == ['buildx', 'imagetools', 'inspect']:
        item, _ = image(args[-1])
        if item is None:
            print('ERROR: manifest unknown', file=sys.stderr); sys.exit(1)
        print(json.dumps({'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.index.v1+json', 'manifests': [
            {'mediaType': 'application/vnd.oci.image.manifest.v1+json', 'digest': value, 'size': 1,
             'platform': {'os': name.split('/')[0], 'architecture': name.split('/')[1]}}
            for name, value in item['platforms'].items()]}))
        sys.exit(0)
    if args[:2] == ['buildx', 'build']:
        code = world.get('build_exit', 0)
        if code == 0 and option('--iidfile'):
            Path(option('--iidfile')).write_text('sha256:' + 'f' * 64)
        sys.exit(code)
    if args[:1] == ['run']:
        print('stub-container'); sys.exit(0)
    if args[:1] == ['port']:
        print('127.0.0.1:18080'); sys.exit(0)
    sys.exit(0)

if tool == 'cosign':
    item, value = image(args[-1])
    signature = (item or {}).get('signature')
    accepted = (signature is not None and signature['identity'] == option('--certificate-identity')
                and signature['issuer'] == option('--certificate-oidc-issuer'))
    if args[0] == 'verify':
        if not accepted:
            print('Error: no matching signatures', file=sys.stderr); sys.exit(10)
        print('[]' if signature.get('empty') else json.dumps([{'critical': {'image': {'docker-manifest-digest': value}}}]))
        sys.exit(0)
    if not accepted or not item.get('sbom'):
        print('Error: no matching attestations', file=sys.stderr); sys.exit(10)
    print(json.dumps({'payloadType': 'application/vnd.in-toto+json', 'payload': '', 'signatures': []})); sys.exit(0)

if tool == 'gh':
    item, value = image(args[2])
    proof = (item or {}).get('provenance')
    repository = option('--repo')
    accepted = (proof is not None and proof['repository'] == repository
                and option('--signer-workflow') == repository + '/' + proof['workflow']
                and option('--source-ref') == proof['ref'] and proof.get('issuer', GITHUB) == GITHUB
                and option('--source-digest') in (None, proof['source_sha']))
    if not accepted:
        print('Error: no attestations matched the policy', file=sys.stderr); sys.exit(1)
    subject = proof.get('subject', value)
    print(json.dumps([{'verificationResult': {
        'signature': {'certificate': {
            'sourceRepositoryIdentifier': proof['repository_id'], 'sourceRepositoryOwnerIdentifier': proof['owner_id'],
            'sourceRepositoryURI': 'https://github.com/' + repository, 'sourceRepositoryRef': proof['ref'],
            'sourceRepositoryDigest': proof['source_sha']}},
        'statement': {'_type': 'https://in-toto.io/Statement/v1', 'predicateType': 'https://slsa.dev/provenance/v1',
                      'subject': [{'name': args[2][6:].split('@')[0], 'digest': {'sha256': subject[7:]}}],
                      'predicate': {'runDetails': {'metadata': {'invocationId': proof['invocation']}}}}}}]))
    sys.exit(0)

if tool == 'curl':
    if args[-1].endswith('/health'):
        print('{"status": "ok"}')
    elif args[-1].endswith('/info'):
        print(json.dumps({'status': 'ok', 'security': {'uid': world.get('smoke_uid', 10000), 'gid': 10000}}))
    else:
        sys.exit(22)
    sys.exit(0)
sys.exit(97)
'''


def provenance(subject, run=101, **changes):
    value = dict(repository=SOURCE, workflow=WORKFLOW, ref='refs/heads/develop', source_sha=SOURCE_SHA,
                 invocation=f'https://github.com/{SOURCE}/actions/runs/{run}/attempts/1', subject=subject, **IDS)
    value.update(changes)
    return value


def image(repository, label, subject, run=101):
    return dict(repository=repository, platforms={'linux/amd64': digest(label + '-amd64'),
                                                  'linux/arm64': digest(label + '-arm64')},
                signature=dict(identity=IDENTITY, issuer=ISSUER), sbom=True, provenance=provenance(subject, run))


def world():
    return dict(registry=REGISTRY,
                tags={'image-base-go1-26': {'stable': [RUNTIME]}, 'image-base-go1-26-dev': {'stable': [BUILD]}},
                images={RUNTIME: image('image-base-go1-26', 'runtime-r1', RUNTIME),
                        BUILD: image('image-base-go1-26-dev', 'build-r1', BUILD),
                        RUNTIME_MOVED: image('image-base-go1-26', 'runtime-r2', RUNTIME_MOVED, run=202)})


RELEASE = dict(schema_version=1, source_repository=SOURCE, source_sha=SOURCE_SHA, run_id=101, run_attempt=1,
               images={'go1-26': RUNTIME, 'go1-26-dev': BUILD})


def load_gate():
    spec = importlib.util.spec_from_file_location('audited_consumer_under_test', GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipIf(os.name != 'posix', 'o gate de consumo exige POSIX')
class AuditedConsumerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = tempfile.TemporaryDirectory(prefix='audited-consumer-')
        cls.addClassCleanup(cls.storage.cleanup)
        root = Path(cls.storage.name)
        cls.bin = root / 'bin'
        cls.bin.mkdir()
        for tool in STUBBED:
            path = cls.bin / tool
            path.write_text(STUB.replace('{python}', sys.executable))
            path.chmod(0o755)
        cls.tools = root / 'tools'
        cls.tools.mkdir()
        for tool in SYSTEM_TOOLS:
            found = shutil.which(tool)
            if found is None:
                raise unittest.SkipTest(f'utilitário ausente: {tool}')
            os.symlink(found, cls.tools / tool)
        python3 = cls.tools / 'python3'  # consume.sh chama python3: este interpretador, com o mesmo venv
        python3.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        python3.chmod(0o755)
        # Checkout revisado da Factory: o verify_promotion real, identidade sintética.
        cls.factory = root / 'factory'
        for relative in FACTORY_FILES:
            target = cls.factory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        identities = cls.factory / 'policies/release/signing-identities.json'
        identities.parent.mkdir(parents=True)
        identities.write_text(json.dumps({SOURCE: dict(IDS, previous_names=[])}))
        git = ['git', '-C', str(cls.factory), '-c', 'user.name=test', '-c', 'user.email=test@example.invalid',
               '-c', 'commit.gpgsign=false']
        subprocess.run(git[:3] + ['init', '-q'], check=True)
        subprocess.run(git + ['add', '-A'], check=True)
        subprocess.run(git + ['commit', '-q', '-m', 'factory snapshot'], check=True)
        cls.commit = subprocess.run(['git', '-C', str(cls.factory), 'rev-parse', 'HEAD'], check=True,
                                    capture_output=True, text=True).stdout.strip()

    def setUp(self):
        self.case = Path(tempfile.mkdtemp(dir=self.storage.name))
        (self.case / 'state').mkdir()
        self.log = self.case / 'calls.log'
        self.world = world()

    def policy(self, **changes):
        value = dict(schema_version=1, verification_level='full-policy', registry=REGISTRY,
                     repository_prefix='image-base-', source_repository=SOURCE, signer_workflow=WORKFLOW,
                     signer_ref='refs/heads/develop', oidc_issuer=ISSUER,
                     bases={'runtime': {'framework': 'go1-26', 'build_arg': 'RUNTIME_IMAGE'},
                            'build': {'framework': 'go1-26-dev', 'build_arg': 'BUILD_IMAGE'}},
                     require_sbom_attestation=True, verifier_timeout_seconds=30,
                     factory_checkout_commit=self.commit, verifier_script_sha256=file_sha256(VERIFY_IMAGE))
        value.update(changes)
        return value

    def write(self, name, value):
        path = self.case / name
        path.write_text(json.dumps(value))
        return path

    def env(self, path=None):
        (self.case / 'world.json').write_text(json.dumps(self.world))
        return dict(os.environ, PATH=(path or str(self.bin)) + os.pathsep + str(self.tools),
                    AUDITED_STUB_WORLD=str(self.case / 'world.json'), AUDITED_STUB_LOG=str(self.log),
                    AUDITED_STUB_STATE=str(self.case / 'state'), TMPDIR=str(self.case))

    def gate(self, *args, path=None):
        return subprocess.run([sys.executable, '-B', str(GATE), *map(str, args)], capture_output=True,
                              text=True, env=self.env(path), timeout=120)

    def verify(self, *args, policy=None, release=None, out='out', verifier=VERIFY_IMAGE, factory=None, path=None):
        options = ['verify', '--policy', self.write('policy.json', policy or self.policy()), '--out', self.case / out,
                   '--verifier-script', verifier, '--factory-checkout', factory or self.factory]
        if release is not None:
            options += ['--release-record', self.write('release.json', release)]
        result = self.gate(*options, *args, path=path)
        record_path = self.case / out / 'verification-record.json'
        record = json.loads(record_path.read_text()) if record_path.exists() else None
        return result, record, self.case / out / 'verified-bases.lock.json'

    def calls(self, tool=None):
        if not self.log.exists():
            return []
        entries = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [entry for entry in entries if tool is None or entry[0] == tool]

    def assertBlocked(self, outcome, code, exit_code=1):
        result, record, lock = outcome
        self.assertEqual(result.returncode, exit_code, result.stdout + result.stderr)
        self.assertFalse(lock.exists(), 'lock must not exist after a refusal')
        self.assertEqual(record['status'], 'BLOCKED')
        self.assertEqual([d['code'] for d in record['diagnostics']], [code], record['diagnostics'])
        self.assertIn(f'BLOCKED {code}', result.stderr)
        return record


class PositiveConsumptionTests(AuditedConsumerTestCase):
    def test_full_policy_resolves_each_tag_once_and_locks_the_verified_indexes(self):
        result, record, lock = self.verify('--runtime', 'stable', '--build', 'stable')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(record['status'], 'TRUSTED')
        lock = json.loads(lock.read_text())
        self.assertEqual(lock['build_args'], {'RUNTIME_IMAGE': f'{REGISTRY}/image-base-go1-26@{RUNTIME}',
                                              'BUILD_IMAGE': f'{REGISTRY}/image-base-go1-26-dev@{BUILD}'})
        self.assertEqual(lock['record_sha256'], file_sha256(self.case / 'out/verification-record.json'))
        runtime = record['bases']['runtime']
        self.assertEqual(runtime['checks'], dict(signature='PASS', provenance='PASS', platforms='PASS',
                                                 repository_ids='PASS', release_binding='NOT_REQUESTED',
                                                 sbom_attestation='PASS'))
        self.assertEqual(runtime['platforms'], self.world['images'][RUNTIME]['platforms'])
        self.assertEqual(runtime['input'], dict(kind='tag', value='stable'))
        self.assertEqual(record['pair'], dict(compatible=True, same_release='PASS'))
        describe = [c for c in self.calls('aws') if c[1:3] == ['ecr', 'describe-images']]
        self.assertEqual(len(describe), 2)  # one per base, never again after verification
        for call in self.calls('cosign') + self.calls('gh'):
            self.assertTrue(any(RUNTIME in a or BUILD in a for a in call), call)  # never a tag
        self.assertIn('NOT_AN_ADMISSION_CONTROLLER', record['limitations'])

    def test_release_record_binds_commit_run_and_attempt(self):
        result, record, lock = self.verify(release=RELEASE)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(record['bases']['build']['checks']['release_binding'], 'PASS')
        self.assertEqual(record['release_record']['run_id'], 101)
        # verify_promotion (runtime e -dev) exige o commit aprovado no gh; o SBOM via verify-image.sh não usa a flag.
        bound = [c for c in self.calls('gh') if '--source-digest' in c]
        self.assertEqual([c[c.index('--source-digest') + 1] for c in bound], [SOURCE_SHA, SOURCE_SHA])
        # Digests da release aprovada dispensam qualquer consulta de tag.
        self.assertEqual([c for c in self.calls('aws') if 'describe-images' in c], [])

    def test_simplified_level_is_explicitly_weaker_than_the_full_policy(self):
        result, record, lock = self.verify('--runtime', RUNTIME, '--build', BUILD,
                                           policy=self.policy(verification_level='simplified',
                                                              factory_checkout_commit=None))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        checks = record['bases']['runtime']['checks']
        self.assertEqual({k: checks[k] for k in ('platforms', 'repository_ids', 'release_binding')},
                         dict(platforms='NOT_CHECKED', repository_ids='NOT_CHECKED', release_binding='NOT_CHECKED'))
        self.assertEqual(record['pair']['same_release'], 'NOT_CHECKED')
        self.assertIsNone(json.loads(lock.read_text())['bases']['runtime']['platforms'])
        self.assertEqual(self.calls('docker')[0][0:2], ['docker', 'login'])  # verify-image.sh path, no Factory import
        args = self.gate('build-args', '--lock', lock, '--require-level', 'full-policy')
        self.assertEqual(args.returncode, 1)
        self.assertIn('LEVEL_INSUFFICIENT', args.stderr)


class NegativeConsumptionTests(AuditedConsumerTestCase):
    def test_divergent_digest_is_refused(self):
        # Tag resolve para outro índice que não o da release aprovada: nenhum verificador roda.
        self.world['tags']['image-base-go1-26']['stable'] = [RUNTIME_MOVED]
        self.assertBlocked(self.verify('--runtime', 'stable', release=RELEASE), 'DIGEST_MISMATCH')
        self.assertEqual(self.calls('cosign'), [])
        # Digest sem assinatura/índice no registry.
        self.assertBlocked(self.verify('--runtime', UNSIGNED, '--build', BUILD, out='o2'), 'INDEX_UNAVAILABLE')
        # Verificador reporta statement de outro subject com exit 0.
        self.world['images'][RUNTIME]['provenance']['subject'] = RUNTIME_MOVED
        self.assertBlocked(self.verify('--runtime', RUNTIME, '--build', BUILD, out='o3'),
                           'PROVENANCE_SUBJECT_MISMATCH')

    def test_verifier_confirming_another_digest_is_refused(self):
        fake = self.case / 'verify-image.sh'
        fake.write_text('#!/bin/bash\necho "PASS: assinatura"\necho "PASS: attestation SBOM"\n'
                        f'echo "PASS: provenance"\necho "RESULTADO: PASS -- {REGISTRY}/image-base-go1-26@{UNSIGNED}"\n')
        outcome = self.verify('--runtime', RUNTIME, verifier=fake, policy=self.policy(
            verification_level='simplified', factory_checkout_commit=None, verifier_script_sha256=file_sha256(fake),
            bases={'runtime': {'framework': 'go1-26', 'build_arg': 'RUNTIME_IMAGE'}}))
        self.assertBlocked(outcome, 'DIGEST_MISMATCH')

    def test_wrong_issuer_is_refused_by_both_levels_and_cannot_be_declared(self):
        self.world['images'][RUNTIME]['signature']['issuer'] = 'https://accounts.google.com'
        self.assertBlocked(self.verify('--runtime', RUNTIME, '--build', BUILD), 'SIGNATURE_REJECTED')
        self.assertBlocked(self.verify('--runtime', RUNTIME, '--build', BUILD, out='o2', policy=self.policy(
            verification_level='simplified', factory_checkout_commit=None)), 'SIGNATURE_REJECTED')
        outcome = self.verify('--runtime', RUNTIME, out='o3', policy=self.policy(
            oidc_issuer='https://token.actions.githubusercontent.com/example-enterprise'))
        self.assertBlocked(outcome, 'POLICY_NOT_ENFORCEABLE', exit_code=2)

    def test_wrong_workflow_identity_is_refused(self):
        for case, identity in (('fork', f'https://github.com/attacker/fork/{WORKFLOW}@refs/heads/develop'),
                               ('workflow', f'https://github.com/{SOURCE}/.github/workflows/other.yml@refs/heads/develop'),
                               ('branch', f'https://github.com/{SOURCE}/{WORKFLOW}@refs/heads/main')):
            with self.subTest(case=case):
                self.world['images'][RUNTIME]['signature']['identity'] = identity
                self.assertBlocked(self.verify('--runtime', RUNTIME, '--build', BUILD, out=case),
                                   'SIGNATURE_REJECTED')
        self.assertBlocked(self.verify('--runtime', RUNTIME, out='declared', policy=self.policy(
            signer_workflow='.github/workflows/other.yml')), 'POLICY_NOT_ENFORCEABLE', exit_code=2)

    def test_incompatible_provenance_is_refused(self):
        self.world['images'][RUNTIME]['provenance']['repository_id'] = '999'
        self.assertBlocked(self.verify('--runtime', RUNTIME, '--build', BUILD), 'PROVENANCE_REJECTED')
        self.world = world()
        self.world['images'][RUNTIME]['provenance']['source_sha'] = '2' * 40
        self.assertBlocked(self.verify(release=RELEASE, out='commit'), 'PROVENANCE_REJECTED')
        self.world = world()
        other_run = dict(RELEASE, run_id=999)
        self.assertBlocked(self.verify(release=other_run, out='run'), 'PROVENANCE_RELEASE_MISMATCH')

    def test_insufficient_evidence_is_refused(self):
        self.world['images'][RUNTIME]['signature']['empty'] = True
        self.assertBlocked(self.verify('--runtime', RUNTIME, '--build', BUILD), 'INSUFFICIENT_EVIDENCE')
        self.world = world()
        self.world['images'][RUNTIME]['sbom'] = False
        self.assertBlocked(self.verify('--runtime', RUNTIME, '--build', BUILD, out='sbom'),
                           'SBOM_ATTESTATION_REJECTED')
        self.world = world()
        del self.world['images'][RUNTIME]['platforms']['linux/arm64']
        self.assertBlocked(self.verify('--runtime', RUNTIME, '--build', BUILD, out='platforms'),
                           'PLATFORM_SET_INVALID')
        silent = self.case / 'silent.sh'
        silent.write_text(f'#!/bin/bash\necho "RESULTADO: PASS -- {REGISTRY}/image-base-go1-26@{RUNTIME}"\n')
        self.assertBlocked(self.verify('--runtime', RUNTIME, verifier=silent, out='silent', policy=self.policy(
            verification_level='simplified', factory_checkout_commit=None, verifier_script_sha256=file_sha256(silent),
            bases={'runtime': {'framework': 'go1-26', 'build_arg': 'RUNTIME_IMAGE'}})), 'INSUFFICIENT_EVIDENCE')

    def test_verifier_failure_or_timeout_is_refused(self):
        self.world['delays'] = {'cosign': 30}
        started = time.monotonic()
        self.assertBlocked(self.verify('--runtime', RUNTIME, '--build', BUILD,
                                       policy=self.policy(verifier_timeout_seconds=2)), 'VERIFIER_TIMEOUT')
        self.assertLess(time.monotonic() - started, 20)
        self.world = world()
        bare = self.case / 'bare'
        bare.mkdir()
        for tool in ('aws', 'docker', 'gh'):
            os.symlink(self.bin / tool, bare / tool)
        self.assertBlocked(self.verify('--runtime', RUNTIME, '--build', BUILD, out='missing', path=str(bare)),
                           'VERIFIER_UNAVAILABLE')
        self.assertBlocked(self.verify('--runtime', RUNTIME, out='script', policy=self.policy(
            verifier_script_sha256='0' * 64)), 'VERIFIER_SCRIPT_UNTRUSTED')
        self.assertBlocked(self.verify('--runtime', RUNTIME, out='commit', policy=self.policy(
            factory_checkout_commit='2' * 40)), 'FACTORY_CHECKOUT_UNTRUSTED')
        dirty = Path(tempfile.mkdtemp(dir=self.case)) / 'factory'
        shutil.copytree(self.factory, dirty)
        (dirty / 'scripts/pipeline/release/verify_promotion.py').write_text('def verify_promotion(*a, **k):\n    pass\n')
        self.assertBlocked(self.verify('--runtime', RUNTIME, out='dirty', factory=dirty),
                           'FACTORY_CHECKOUT_UNTRUSTED')

    def test_incompatible_runtime_dev_pair_is_refused(self):
        java = {'runtime': {'framework': 'go1-26', 'build_arg': 'RUNTIME_IMAGE'},
                'build': {'framework': 'java21-dev', 'build_arg': 'BUILD_IMAGE'}}
        self.assertBlocked(self.verify('--runtime', RUNTIME, policy=self.policy(bases=java)),
                           'PAIR_INCOMPATIBLE', exit_code=2)
        dev_final = {'runtime': {'framework': 'go1-26-dev', 'build_arg': 'RUNTIME_IMAGE'}}
        self.assertBlocked(self.verify('--runtime', BUILD, out='dev', policy=self.policy(bases=dev_final)),
                           'PAIR_INCOMPATIBLE', exit_code=2)
        self.world['images'][BUILD]['provenance']['invocation'] = \
            f'https://github.com/{SOURCE}/actions/runs/303/attempts/1'
        self.assertBlocked(self.verify('--runtime', RUNTIME, '--build', BUILD, out='runs'), 'PAIR_RELEASE_MISMATCH')

    def test_placeholders_and_unknown_fields_are_refused_before_any_command(self):
        example = json.loads((EXAMPLE / 'policy.example.json').read_text())
        self.assertBlocked(self.verify('--runtime', RUNTIME, policy=example), 'POLICY_PLACEHOLDER', exit_code=2)
        self.assertBlocked(self.verify('--runtime', RUNTIME, out='extra', policy=dict(self.policy(), extra=True)),
                           'POLICY_INVALID', exit_code=2)
        self.assertBlocked(self.verify('--runtime', 'registry.example/x:stable', out='ref'), 'REFERENCE_INVALID',
                           exit_code=2)
        self.assertEqual(self.calls(), [])


class LockAndDockerfileTests(AuditedConsumerTestCase):
    def trusted_lock(self):
        result, _, lock = self.verify('--runtime', RUNTIME, '--build', BUILD)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return lock

    def test_tampered_lock_or_record_is_refused(self):
        lock = self.trusted_lock()
        original = lock.read_text()
        lock.write_text(original.replace(RUNTIME, RUNTIME_MOVED))
        self.assertIn('LOCK_TAMPERED', self.gate('build-args', '--lock', lock).stderr)
        lock.write_text(original)
        record = lock.parent / 'verification-record.json'
        record.write_text(record.read_text().replace(RUNTIME, RUNTIME_MOVED))
        result = self.gate('build-args', '--lock', lock)
        self.assertEqual(result.returncode, 1)
        self.assertIn('LOCK_TAMPERED', result.stderr)

    def test_build_args_come_only_from_the_lock(self):
        lock = self.trusted_lock()
        result = self.gate('build-args', '--lock', lock)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            '--build-arg', f'BUILD_IMAGE={REGISTRY}/image-base-go1-26-dev@{BUILD}',
            '--build-arg', f'RUNTIME_IMAGE={REGISTRY}/image-base-go1-26@{RUNTIME}'])

    def test_example_dockerfile_passes_and_unverified_patterns_fail(self):
        gate = load_gate()
        args = {'RUNTIME_IMAGE', 'BUILD_IMAGE'}
        findings, stages = gate.check_dockerfile((EXAMPLE / 'Dockerfile').read_text(), args, 'RUNTIME_IMAGE')
        self.assertEqual(findings, [])
        self.assertEqual(stages, [('arg', 'BUILD_IMAGE'), ('arg', 'RUNTIME_IMAGE')])
        header = 'ARG BUILD_IMAGE\nARG RUNTIME_IMAGE\n'
        cases = {
            'DOCKERFILE_UNVERIFIED_FROM': header + 'FROM registry.example/image-base-go1-26:stable\n',
            'DOCKERFILE_ARG_DEFAULT': 'ARG BUILD_IMAGE\nARG RUNTIME_IMAGE=registry.example/x:stable\nFROM ${RUNTIME_IMAGE}\n',
            'DOCKERFILE_FINAL_STAGE_NOT_RUNTIME': header + 'FROM ${RUNTIME_IMAGE} AS r\nFROM ${BUILD_IMAGE}\n',
            'DOCKERFILE_EXTERNAL_IMAGE': header + 'FROM ${RUNTIME_IMAGE}\nCOPY --from=alpine:3 /bin/sh /bin/sh\n',
            'DOCKERFILE_UNDECLARED_ARG': 'FROM ${RUNTIME_IMAGE}\n',
            'DOCKERFILE_REMOTE_ADD': header + 'FROM ${RUNTIME_IMAGE}\nADD https://example.invalid/x /x\n',
        }
        for code, text in cases.items():
            with self.subTest(code=code):
                findings, _ = gate.check_dockerfile(text, args, 'RUNTIME_IMAGE')
                self.assertIn(code, [f['code'] for f in findings], findings)
        staged = header + 'FROM ${BUILD_IMAGE} AS build\nFROM build AS test\nFROM ${RUNTIME_IMAGE} AS final\n' \
                          'COPY --from=build /a /a\nRUN --mount=type=cache,from=test,target=/c true\nFROM final\n'
        self.assertEqual(gate.check_dockerfile(staged, args, 'RUNTIME_IMAGE')[0], [])
        with self.assertRaises(gate.GateError):
            gate.check_dockerfile('# syntax=docker/dockerfile:1\n' + header + 'FROM ${RUNTIME_IMAGE}\n', args,
                                  'RUNTIME_IMAGE')
        lock = self.trusted_lock()
        result = self.gate('check-dockerfile', '--lock', lock, '--dockerfile', EXAMPLE / 'Dockerfile')
        self.assertEqual((result.returncode, json.loads(result.stdout)['status']), (0, 'PASS'), result.stdout)


class ConsumeScriptTests(AuditedConsumerTestCase):
    def consume(self, *args, policy=None):
        options = ['bash', str(CONSUME), '--policy', self.write('policy.json', policy or self.policy()),
                   '--out', str(self.case / 'run'), '--verifier-script', str(VERIFY_IMAGE),
                   '--factory-checkout', str(self.factory), *map(str, args)]
        return subprocess.run(options, capture_output=True, text=True, env=self.env(), timeout=180)

    def build_calls(self):
        return [c for c in self.calls('docker') if c[1:3] == ['buildx', 'build']]

    def test_tag_moved_after_verification_is_not_consumed(self):
        # stable aponta para r1 na verificação e para r2 em qualquer consulta posterior.
        self.world['tags']['image-base-go1-26']['stable'] = [RUNTIME, RUNTIME_MOVED]
        result = self.consume('--runtime', 'stable', '--build', BUILD)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        build = self.build_calls()
        self.assertEqual(len(build), 1)
        self.assertIn(f'RUNTIME_IMAGE={REGISTRY}/image-base-go1-26@{RUNTIME}', build[0])
        self.assertFalse(any(RUNTIME_MOVED in a or a.endswith(':stable') for a in build[0]))
        describe = [c for c in self.calls('aws') if 'describe-images' in c]
        self.assertEqual(len(describe), 1)
        consumption = json.loads((self.case / 'run/consumption-record.json').read_text())
        self.assertEqual((consumption['status'], consumption['build_args']['RUNTIME_IMAGE']),
                         ('PASS', f'{REGISTRY}/image-base-go1-26@{RUNTIME}'))
        run = next(c for c in self.calls('docker') if c[1] == 'run')
        for flag in ('--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges'):
            self.assertIn(flag, run)
        self.assertNotIn('--user', run)  # o UID/GID 10000 vem da base e é conferido em /info

    def test_unverified_dockerfile_never_reaches_docker_build(self):
        context = self.case / 'context'
        context.mkdir()
        (context / 'Dockerfile').write_text('ARG RUNTIME_IMAGE\nFROM registry.example/image-base-go1-26:stable\n')
        result = self.consume('--runtime', RUNTIME, '--build', BUILD, '--context', context)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('DOCKERFILE_UNVERIFIED_FROM', result.stderr)
        self.assertEqual(self.build_calls(), [])

    def test_untrusted_base_never_reaches_docker_build(self):
        self.world['images'][RUNTIME]['signature']['identity'] = f'https://github.com/attacker/fork/{WORKFLOW}@refs/heads/develop'
        result = self.consume('--runtime', RUNTIME, '--build', BUILD)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SIGNATURE_REJECTED', result.stderr)
        self.assertEqual(self.build_calls(), [])
        self.assertFalse((self.case / 'run/verification/verified-bases.lock.json').exists())

    def test_application_test_failure_and_smoke_failure_block_consumption(self):
        self.world['build_exit'] = 1
        result = self.consume('--runtime', RUNTIME, '--build', BUILD)
        self.assertEqual(result.returncode, 1)
        self.assertIn('BUILD_FAILED', result.stderr)
        self.assertFalse((self.case / 'run/consumption-record.json').exists())
        shutil.rmtree(self.case / 'run')
        self.world = world()
        self.world['smoke_uid'] = 0
        result = self.consume('--runtime', RUNTIME, '--build', BUILD)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads((self.case / 'run/consumption-record.json').read_text())['status'], 'FAIL')


class ExampleContractTests(unittest.TestCase):
    def test_example_identity_matches_the_factory_signing_policy(self):
        example = json.loads((EXAMPLE / 'policy.example.json').read_text())
        identities = json.loads((ROOT / 'policies/release/signing-identities.json').read_text())
        self.assertIn(example['source_repository'], identities)
        contract = (ROOT / 'docs/consumer-verification-contract.md').read_text(encoding='utf-8')
        for value in (example['source_repository'], example['oidc_issuer'], example['signer_ref']):
            self.assertIn(value, contract)
        self.assertEqual(example['signer_workflow'], WORKFLOW)
        self.assertEqual(example['verification_level'], 'full-policy')

    def test_gate_source_carries_no_sandbox_identity(self):
        source = GATE.read_text(encoding='utf-8') + CONSUME.read_text(encoding='utf-8')
        for value in ('712107929769', '1360616627', '178685987', 'alric-corp', 'itau'):
            self.assertNotIn(value, source)


if __name__ == '__main__':
    unittest.main()
