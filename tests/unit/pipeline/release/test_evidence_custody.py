"""Historical public inputs + disposable TEST_ONLY trust, never durable authority."""
import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from scripts.pipeline.release import evidence_custody as custody
from scripts.pipeline.release.evidence_archive import (
    InvalidEvidence, canonical, document, inventory, make_zip, read_zip, sha256,
)
from scripts.pipeline.release.evidence_store import (
    EvidenceStore, MemoryTransport, ReadStatus, StoredObject, TransportError, WriteStatus,
)
from tests.unit.pipeline.release.custody_support import (
    POLICY_ID, ORIGINAL_SHA256, TestAuthenticator, TestSigner, fixture_inputs,
    frozen_fixture, prepared_fixture,
)


class CustodyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared, cls.expected = prepared_fixture()
        cls.signer = TestSigner()
        cls.attacker = TestSigner()

    @classmethod
    def tearDownClass(cls):
        cls.signer.close()
        cls.attacker.close()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='hgc04-offline-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.store = EvidenceStore(MemoryTransport())
        self.counter = 0

    def read(self, **options):
        self.counter += 1
        arguments = dict(store=self.store, expected=self.expected, policy=self.signer.policy(),
                         authenticator=TestAuthenticator(), target=self.root / f'read-{self.counter}')
        arguments.update(options)
        return custody.recover(**arguments)

    def ready(self):
        frozen = frozen_fixture(self.store, self.prepared, self.expected, self.signer)
        result = self.store.create_once(self.expected.prefix + 'commit.json', frozen.content)
        self.assertEqual(result.status, WriteStatus.CREATED)
        return frozen

    def forge(self, mutate_files=None, mutate_plan=None, signer=None):
        """Attacker-controlled self-consistent hash envelope, only in memory."""
        self.store = EvidenceStore(MemoryTransport())
        files = read_zip(self.prepared.data, custody=True)
        plan = document(self.prepared.plan)
        if mutate_files:
            mutate_files(files)
        context = document(files['acquisition/context.json'])
        artifacts = {a['id']: a for a in context['artifacts']}
        for name in custody.CORE:
            path = f'originals/{name}.zip'
            original = files[path]
            artifact = artifacts[context['producers'][name]['artifact_id']]
            artifact.update(size=len(original), sha256=sha256(original))
            plan['core_archives'][name] = dict(path=path, size=len(original), sha256=sha256(original),
                                              members=inventory(read_zip(original)))
        files['acquisition/context.json'] = canonical(context)
        jobs = {j['id']: j for j in context['jobs']}
        plan['producers'] = {n: dict(artifact=artifacts[p['artifact_id']], job=jobs[p['job_id']])
                             for n, p in context['producers'].items()}
        plan['inventory'] = inventory(files)
        raw = make_zip(files)
        stored = self.store.create_once(custody.payload_key(self.expected, raw), custody.object_content(raw, 'hgc04-payload'))
        plan['payload'] = dict(key=custody.payload_key(self.expected, raw), size=len(raw), sha256=sha256(raw),
                               version_id=stored.object.version_id)
        if mutate_plan:
            mutate_plan(plan)
        manifest = canonical(plan)
        bundle = (signer or self.signer).sign(manifest)
        # Deliberately bypass the public freeze/finalize guards for hostile input.
        raw_commit = canonical(dict(schema_version=1, kind='hgc04-commit', manifest=custody._encoded(manifest),
                                    bundle=custody._encoded(bundle)))
        self.store.create_once(self.expected.prefix + 'commit.json', custody.object_content(raw_commit, 'hgc04-commit'))

    def test_full_local_sequence_positive_before_and_after(self):
        frozen = frozen_fixture(self.store, self.prepared, self.expected, self.signer)
        self.assertEqual(self.read().state, custody.CustodyState.PARTIAL)
        result = custody.commit_record(self.store, frozen, self.expected, self.signer.policy(), TestAuthenticator(), self.root / 'finalize')
        self.assertEqual(result.status, WriteStatus.CREATED)
        recovered = self.read()
        self.assertEqual(recovered.state, custody.CustodyState.COMPLETE_VERIFIED)
        self.assertEqual(recovered.report['result'], 'READBACK_VERIFIED')
        self.assertEqual(recovered.profile, 'TEST_ONLY')
        self.assertFalse(recovered.production_authority)
        retry = custody.commit_record(self.store, frozen, self.expected, self.signer.policy(), TestAuthenticator(), self.root / 'restart')
        self.assertEqual(retry.status, WriteStatus.ALREADY_PRESENT_IDENTICAL)
        self.assertEqual(self.read().state, custody.CustodyState.COMPLETE_VERIFIED)

    def test_original_zips_receipts_and_binary_members_survive(self):
        self.ready()
        recovered = self.read()
        self.assertEqual(recovered.state, custody.CustodyState.COMPLETE_VERIFIED)
        files = read_zip(self.prepared.data, custody=True)
        for name in custody.CORE:
            original = files[f'originals/{name}.zip']
            self.assertEqual(sha256(original), ORIGINAL_SHA256[name])
            expanded = read_zip(original)
            recovered_root = self.root / f'read-{self.counter}/extracted' / name
            actual = {p.relative_to(recovered_root).as_posix(): p.read_bytes() for p in recovered_root.rglob('*') if p.is_file()}
            self.assertEqual(actual, expanded)
        self.assertFalse((self.root / f'read-{self.counter}/extracted/melange-repo/reports').exists())

    def test_packaging_is_predictable_and_preserves_external_json_representation(self):
        again, _ = prepared_fixture()
        self.assertEqual(again, self.prepared)
        zips, materials, origins, expected = fixture_inputs()
        original = materials['acquisition/context.json']
        self.assertNotEqual(original, canonical(document(original)))
        files = read_zip(again.data, custody=True)
        self.assertEqual(files['acquisition/context.json'], original)
        self.assertEqual(json.loads(files['release/store-candidate.json']), json.loads(files['release/artifact-candidate.json']))
        self.assertNotEqual(files['release/store-candidate.json'], files['release/artifact-candidate.json'])

    def test_selected_artifact_zip_digest_is_explicitly_not_recalculable(self):
        plan = document(self.prepared.plan)
        selected = [r for r in plan['materials'] if r['origin']['kind'] == 'github-artifact']
        self.assertTrue(selected)
        for record in selected:
            self.assertFalse(record['origin']['zip_preserved'])
            self.assertIn('source_zip_sha256', record['origin'])
        self.assertEqual(set(plan['core_archives']), set(custody.CORE))

    def test_no_hash_cycle_and_exact_signed_bytes_in_commit(self):
        frozen = frozen_fixture(self.store, self.prepared, self.expected, self.signer)
        manifest, bundle, plan, payload = custody.inspect_commit(frozen.content.data, self.expected)
        self.assertNotIn('payload', plan)
        self.assertNotIn('bundle', document(manifest))
        self.assertNotIn('commit', document(manifest))
        self.assertEqual(payload['sha256'], sha256(self.prepared.data))
        self.assertEqual(custody._decoded(document(frozen.content.data)['manifest']), manifest)
        self.assertEqual(custody._decoded(document(frozen.content.data)['bundle']), bundle)

    def test_new_valid_signature_is_not_an_identical_retry(self):
        original = self.ready()
        manifest, _, _, _ = custody.inspect_commit(original.content.data, self.expected)
        replacement = custody.freeze_commit(manifest, self.signer.sign(manifest), self.signer.policy(), self.expected, TestAuthenticator())
        self.assertNotEqual(original.content.data, replacement.content.data)
        with patch.object(self.store.transport, 'put_if_absent', side_effect=AssertionError('restart must not write')):
            result = custody.commit_record(self.store, replacement, self.expected, self.signer.policy(), TestAuthenticator(), self.root / 'restart')
        self.assertEqual(result.status, WriteStatus.CONFLICT)

    def concurrent_commits(self, different):
        first = frozen_fixture(self.store, self.prepared, self.expected, self.signer)
        manifest, _, _, _ = custody.inspect_commit(first.content.data, self.expected)
        second = custody.freeze_commit(manifest, self.signer.sign(manifest), self.signer.policy(),
                                       self.expected, TestAuthenticator()) if different else first
        barrier = Barrier(2)

        def finalize(item):
            number, frozen = item
            barrier.wait(timeout=10)
            return custody.commit_record(self.store, frozen, self.expected, self.signer.policy(),
                                         TestAuthenticator(), self.root / f'concurrent-{number}').status

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(finalize, enumerate((first, second))))
        self.assertCountEqual(results, [WriteStatus.CREATED,
                              WriteStatus.CONFLICT if different else WriteStatus.ALREADY_PRESENT_IDENTICAL])
        self.assertEqual(self.read().state, custody.CustodyState.COMPLETE_VERIFIED)

    def test_concurrent_identical_commits(self):
        self.concurrent_commits(False)

    def test_concurrent_different_signatures_conflict(self):
        self.concurrent_commits(True)

    def test_integrity_inspection_does_not_authenticate_or_execute(self):
        frozen = self.ready()
        with patch('subprocess.run', side_effect=AssertionError('inspection cannot execute')):
            manifest, _, _, _ = custody.inspect_commit(frozen.content.data, self.expected)
        self.assertTrue(manifest)
        for options in (dict(policy=None), dict(authenticator=None)):
            with self.subTest(options=options), patch('subprocess.run', side_effect=AssertionError('no unauthenticated execution')):
                result = self.read(**options)
            self.assertEqual(result.state, custody.CustodyState.INVALID)

    def test_structural_inspection_rejects_unsupported_manifest_before_authentication(self):
        frozen = frozen_fixture(self.store, self.prepared, self.expected, self.signer)
        envelope = document(frozen.content.data)
        manifest = document(custody._decoded(envelope['manifest']))
        manifest['schema_version'] = 99
        envelope['manifest'] = custody._encoded(canonical(manifest))
        with patch('subprocess.run', side_effect=AssertionError('structure cannot execute')):
            with self.assertRaisesRegex(InvalidEvidence, 'unsupported custody schema'):
                custody.inspect_commit(canonical(envelope), self.expected)

    def test_failing_or_nonaffirmative_authenticator_is_rejected(self):
        self.ready()
        class Failed:
            def authenticate(self, *args):
                raise RuntimeError('unavailable verifier')
        class Boolean:
            def authenticate(self, *args):
                return True
        for auth in (Failed(), Boolean()):
            with self.subTest(auth=auth), patch.object(custody, '_readback', side_effect=AssertionError('unauthenticated execution')):
                result = self.read(authenticator=auth)
            self.assertEqual(result.state, custody.CustodyState.INVALID)

    def test_production_profile_cannot_be_approved(self):
        self.ready()
        with patch.object(custody, '_readback', side_effect=AssertionError('production profile disabled')):
            result = self.read(policy=replace(self.signer.policy(), profile='PRODUCTION'))
        self.assertEqual(result.state, custody.CustodyState.INVALID)
        self.assertIn('disabled', result.reason)

    def test_document_and_key_replaced_jointly_fail_original_external_trust(self):
        def mutate(plan):
            next(m for m in plan['materials'] if m['role'] == 'acquisition')['origin']['locator'] = 'attacker replacement'
        self.forge(mutate_plan=mutate, signer=self.attacker)
        result = self.read()
        self.assertEqual(result.state, custody.CustodyState.INVALID)
        self.assertIn('external test trust differs', result.reason)

    def test_manifest_or_bundle_tampering_is_rejected(self):
        original = self.ready()
        envelope = document(original.content.data)
        for part in ('manifest', 'bundle'):
            with self.subTest(part=part):
                changed = document(original.content.data)
                decoded = bytearray(base64.b64decode(changed[part]['data']))
                decoded[len(decoded)//2] ^= 1
                changed[part] = custody._encoded(bytes(decoded))
                raw = canonical(changed)
                current = self.store.transport._objects[self.expected.prefix + 'commit.json']
                self.store.transport._objects[self.expected.prefix + 'commit.json'] = StoredObject(custody.object_content(raw, 'hgc04-commit'), current.version_id)
                self.assertEqual(self.read().state, custody.CustodyState.INVALID)

    def test_arbitrary_verifier_is_not_enabled_by_allowed_test_signer(self):
        self.forge(mutate_files=lambda f: f.update({'verifier/verify_reproducibility.py': b'raise RuntimeError("arbitrary")\n'}))
        with patch.object(custody, '_readback', side_effect=AssertionError('unauthorized code execution')):
            result = self.read()
        self.assertEqual(result.state, custody.CustodyState.INVALID)
        self.assertIn('Git source blob differs', result.reason)

    def test_external_verifier_authorization_cannot_select_other_code(self):
        self.ready()
        bad = replace(self.signer.policy().verifier, sha256='0' * 64)
        with patch.object(custody, '_readback', side_effect=AssertionError('unauthorized code')):
            result = self.read(policy=replace(self.signer.policy(), verifier=bad))
        self.assertEqual(result.state, custody.CustodyState.INVALID)

    def test_missing_commit_states_require_external_adoption_policy(self):
        key = f'{self.expected.value["repository_id"]}/{self.expected.value["release_id"]}'
        self.assertEqual(self.read().state, custody.CustodyState.ADOPTION_UNKNOWN)
        self.assertEqual(self.read(adoption=custody.AdoptionPolicy(frozenset(), frozenset({key}))).state, custody.CustodyState.LEGACY_NO_CUSTODY)
        self.assertEqual(self.read(adoption=custody.AdoptionPolicy(frozenset({key}), frozenset())).state, custody.CustodyState.REQUIRED_MISSING)
        self.assertEqual(self.read(adoption=custody.AdoptionPolicy(frozenset(), frozenset())).state, custody.CustodyState.ADOPTION_UNKNOWN)

    def test_orphan_payload_is_partial_and_is_never_deleted(self):
        custody.store_payload(self.store, self.prepared, self.expected)
        before = self.store.keys(self.expected.prefix).keys
        self.assertEqual(self.read().state, custody.CustodyState.PARTIAL)
        self.assertEqual(self.store.keys(self.expected.prefix).keys, before)

    def test_premature_commit_is_invalid_and_finalize_refuses_it(self):
        other = EvidenceStore(MemoryTransport())
        frozen = frozen_fixture(other, self.prepared, self.expected, self.signer)
        self.store.create_once(self.expected.prefix + 'commit.json', frozen.content)
        self.assertEqual(self.read().state, custody.CustodyState.INVALID)
        empty = EvidenceStore(MemoryTransport())
        result = custody.commit_record(empty, frozen, self.expected, self.signer.policy(), TestAuthenticator(), self.root / 'premature')
        self.assertEqual(result.status, WriteStatus.ERROR)
        self.assertEqual(empty.get(self.expected.prefix + 'commit.json').status, ReadStatus.MISSING)

    def test_specific_payload_version_missing_never_falls_back(self):
        self.ready()
        get = self.store.transport.get
        calls = []
        def no_version(key, version_id=None):
            calls.append((key, version_id))
            if version_id is not None:
                from scripts.pipeline.release.evidence_store import MissingObject
                raise MissingObject('requested version missing')
            return get(key, version_id)
        with patch.object(self.store.transport, 'get', side_effect=no_version):
            result = self.read()
        self.assertEqual(result.state, custody.CustodyState.INVALID)
        payload_calls = [v for k, v in calls if '/payload/' in k]
        self.assertEqual(len(payload_calls), 1)
        self.assertIsNotNone(payload_calls[0])

    def test_denied_or_unavailable_reads_are_error(self):
        for error in (TransportError('403 AccessDenied'), TimeoutError('timeout')):
            with self.subTest(error=error), patch.object(self.store.transport, 'get', side_effect=error):
                self.assertEqual(self.read().state, custody.CustodyState.ERROR)
        with patch.object(self.store.transport, 'keys', side_effect=TransportError('denied list')):
            self.assertEqual(self.read().state, custody.CustodyState.ERROR)

    def test_denied_specific_payload_version_is_error_without_latest_fallback(self):
        self.ready()
        get = self.store.transport.get
        calls = []

        def deny_version(key, version_id=None):
            calls.append((key, version_id))
            if '/payload/' in key:
                raise TransportError('403 AccessDenied on requested version')
            return get(key, version_id)

        with patch.object(self.store.transport, 'get', side_effect=deny_version):
            result = self.read()
        self.assertEqual(result.state, custody.CustodyState.ERROR)
        self.assertEqual(len([key for key, version in calls if '/payload/' in key]), 1)
        self.assertTrue(all(version is not None for key, version in calls if '/payload/' in key))

    def test_payload_altered_after_preparation_cannot_commit(self):
        frozen = frozen_fixture(self.store, self.prepared, self.expected, self.signer)
        key = custody.payload_key(self.expected, self.prepared.data)
        stored = self.store.transport._objects[key]
        raw = stored.content.data[:-1] + bytes([stored.content.data[-1] ^ 1])
        self.store.transport._objects[key] = StoredObject(custody.object_content(raw, 'hgc04-payload'), stored.version_id)
        result = custody.commit_record(self.store, frozen, self.expected, self.signer.policy(), TestAuthenticator(), self.root / 'corrupt')
        self.assertEqual(result.status, WriteStatus.ERROR)
        self.assertEqual(self.store.get(self.expected.prefix + 'commit.json').status, ReadStatus.MISSING)

    def test_external_identity_fields_are_reconciled(self):
        for field, value in [('repository', 'other/repo'), ('repository_id', 42), ('owner_id', 43),
                             ('run_id', 37806495088), ('run_attempt', 2), ('ref', 'refs/pull/1/merge'), ('source_sha', '0' * 40)]:
            with self.subTest(field=field):
                def mutate(files):
                    context = document(files['acquisition/context.json'])
                    context['run'][{'run_id': 'id', 'source_sha': 'head_sha'}.get(field, field)] = value
                    files['acquisition/context.json'] = canonical(context)
                self.forge(mutate_files=mutate)
                self.assertEqual(self.read().state, custody.CustodyState.INVALID)

    def test_pr_receipt_release_id_does_not_authorize_release(self):
        zips, materials, origins, expected = fixture_inputs()
        identity = expected.value
        identity.update(event='pull_request', ref='refs/pull/112/merge')
        with self.assertRaisesRegex(InvalidEvidence, 'ineligible'):
            custody.ExpectedIdentity.freeze(identity)

    def test_caller_ref_does_not_replace_external_reusable_resolution(self):
        def mutate(files):
            context = document(files['acquisition/context.json'])
            context['referenced_workflows'][0]['sha'] = self.expected.value['source_sha']
            files['acquisition/context.json'] = canonical(context)
        self.forge(mutate_files=mutate)
        result = self.read()
        self.assertEqual(result.state, custody.CustodyState.INVALID)
        self.assertIn('external reusable resolution differs', result.reason)

    def test_artifact_from_another_job_or_attempt_is_rejected(self):
        for change in ('job', 'attempt', 'run'):
            with self.subTest(change=change):
                def mutate(files):
                    context = document(files['acquisition/context.json'])
                    if change == 'job':
                        context['producers']['melange-reproducibility']['job_id'] = context['producers']['melange-repo']['job_id']
                    elif change == 'attempt':
                        context['jobs'][0]['run_attempt'] = 2
                    else:
                        context['artifacts'][0]['run_id'] += 1
                    files['acquisition/context.json'] = canonical(context)
                self.forge(mutate_files=mutate)
                self.assertEqual(self.read().state, custody.CustodyState.INVALID)

    def test_distinct_runner_names_do_not_replace_distinct_native_runner_ids(self):
        def mutate(files):
            context = document(files['acquisition/context.json'])
            jobs = {j['id']: j for j in context['jobs']}
            reference = jobs[context['producers']['melange-reproduction-reference']['job_id']]
            rebuild = jobs[context['producers']['melange-reproducibility']['job_id']]
            rebuild['runner_id'] = reference['runner_id']
            files['acquisition/context.json'] = canonical(context)
        self.forge(mutate_files=mutate)
        self.assertIn('independent producer', self.read().reason)

    def test_selected_trust_artifact_from_wrong_producer_is_rejected(self):
        def mutate(files):
            context = document(files['acquisition/context.json'])
            artifact_id = context['candidates'][0]['trust_artifact_id']
            artifact = next(a for a in context['artifacts'] if a['id'] == artifact_id)
            artifact['producer_job_id'] = context['candidates'][0]['publication_job_id']
            files['acquisition/context.json'] = canonical(context)
        self.forge(mutate_files=mutate)
        result = self.read()
        self.assertEqual(result.state, custody.CustodyState.INVALID)
        self.assertIn('cryptographic material producer', result.reason)

    def test_boolean_attempt_is_not_an_integer_identity(self):
        def mutate(files):
            context = document(files['acquisition/context.json'])
            context['run']['run_attempt'] = True
            files['acquisition/context.json'] = canonical(context)
        self.forge(mutate_files=mutate)
        self.assertEqual(self.read().state, custody.CustodyState.INVALID)

    def test_earlier_producer_attempt_is_explicit_not_relabelled_as_latest(self):
        files = read_zip(self.prepared.data, custody=True)
        core = {name: read_zip(files[f'originals/{name}.zip']) for name in custody.CORE}
        context, jobs, _ = custody._acquisition(files['acquisition/context.json'], self.expected)
        identity = self.expected.value
        identity.update(run_attempt=2, release_id=f'r{identity["run_id"]}-a2')
        identity['publisher']['run_attempt'] = 2
        audited_second_attempt = custody.ExpectedIdentity.freeze(identity)
        # Set/producer reconciliation only: no historical attempt-2 custody
        # or completed hosted run is asserted by this synthetic unit case.
        custody._core_sets(core, context, jobs, audited_second_attempt)
        context['producers'][custody.CORE[0]]['job_id'] = context['producers'][custody.CORE[2]]['job_id']
        with self.assertRaises(InvalidEvidence):
            custody._core_sets(core, context, jobs, audited_second_attempt)

    def test_exact_apk_set_is_derived_from_recorded_outputs(self):
        files = read_zip(self.prepared.data, custody=True)
        core = {name: read_zip(files[f'originals/{name}.zip']) for name in custody.CORE}
        context, jobs, _ = custody._acquisition(files['acquisition/context.json'], self.expected)
        environment = document(core[custody.CORE[0]]['melange-environment-evidence.json'])
        reproduction = document(core[custody.CORE[2]]['melange-reproducibility-evidence.json'])
        # This probes set derivation only; duplicate bytes under a second name
        # are not claimed to be a valid signed/reproduced CA package.
        for target in ('x86_64', 'aarch64'):
            original = environment['outputs'][target][0]
            rebuild = reproduction['rebuild']['outputs'][target][0]
            name = 'additional-recorded-output.apk'
            original_path = f'packages/{target}/' + original['path'].rsplit('/', 1)[-1]
            core[custody.CORE[0]][f'packages/{target}/{name}'] = core[custody.CORE[0]][original_path]
            core[custody.CORE[2]][f'rebuild/packages/{target}/{name}'] = core[custody.CORE[2]][f'rebuild/packages/{target}/{rebuild["file"]}']
            environment['outputs'][target].append(dict(original, path=f'packages/{target}/{name}'))
            reproduction['rebuild']['outputs'][target].append(dict(rebuild, file=name))
        core[custody.CORE[0]]['melange-environment-evidence.json'] = canonical(environment)
        core[custody.CORE[2]]['melange-reproducibility-evidence.json'] = canonical(reproduction)
        custody._core_sets(core, context, jobs, self.expected)
        del core[custody.CORE[2]]['rebuild/packages/x86_64/additional-recorded-output.apk']
        with self.assertRaises(InvalidEvidence):
            custody._core_sets(core, context, jobs, self.expected)

    def test_missing_rebuild_apk_or_key_and_extra_inner_member_are_rejected(self):
        for change in ('apk', 'key', 'extra'):
            def mutate(files):
                path = 'originals/melange-reproducibility.zip'
                contents = read_zip(files[path])
                if change == 'apk':
                    del contents[next(n for n in contents if n.endswith('.apk'))]
                elif change == 'key':
                    del contents['rebuild/melange.rsa.pub']
                else:
                    contents['extra.txt'] = b'extra'
                files[path] = make_zip(contents)
            with self.subTest(change=change):
                self.forge(mutate_files=mutate)
                self.assertEqual(self.read().state, custody.CustodyState.INVALID)

    def test_candidate_digest_and_incomplete_unit_are_rejected(self):
        for change in ('digest', 'pair'):
            with self.subTest(change=change):
                identity = self.expected.value
                if change == 'digest':identity['candidates'][0]['digest'] = 'sha256:' + '0' * 64
                else:identity['candidates'].pop()
                if change == 'pair':
                    with self.assertRaises(ValueError):custody.ExpectedIdentity.freeze(identity)
                else:
                    self.forge(mutate_plan=lambda p: p.update(identity=identity))
                    self.assertEqual(self.read().state, custody.CustodyState.INVALID)

    def test_candidate_document_digest_and_propagated_receipt_mutations(self):
        for path in ('candidates/go1-26/validated-index.json', 'candidates/go1-26/receipts/validated/binfmt-evidence.json'):
            with self.subTest(path=path):
                def mutate(files):
                    value = document(files[path])
                    if 'digest' in value:value['digest'] = 'sha256:' + '0' * 64
                    else:value['extra'] = True
                    files[path] = canonical(value)
                self.forge(mutate_files=mutate)
                self.assertEqual(self.read().state, custody.CustodyState.INVALID)

    def test_original_release_v1_tag_and_spdx_predicate_links_are_checked(self):
        for change in ('tag', 'predicate'):
            def mutate(files):
                path = 'release/store-candidate.json'
                value = document(files[path])
                image = value['images']['go1-26']
                if change == 'tag':
                    image['tag'] = image['tag'].replace('1319', '1320')
                else:
                    image['sboms'][0]['predicate_digest'] = 'sha256:' + '0' * 64
                files[path] = canonical(value)
            with self.subTest(change=change):
                self.forge(mutate_files=mutate)
                result = self.read()
                self.assertEqual(result.state, custody.CustodyState.INVALID)
                self.assertIn('release', result.reason)

    def test_source_configuration_and_git_date_are_bound(self):
        for change in ('source', 'date'):
            with self.subTest(change=change):
                def mutate(files):
                    if change == 'source':files['source/melange/image-base-ca-certificates.yaml'] += b'\n'
                    else:
                        context = document(files['acquisition/context.json'])
                        context['build_date'] = '2026-10-08T16:08:48+00:00'
                        files['acquisition/context.json'] = canonical(context)
                self.forge(mutate_files=mutate)
                self.assertEqual(self.read().state, custody.CustodyState.INVALID)

    def test_changed_application_policy_or_payload_location_is_rejected(self):
        for change in ('policy', 'location', 'version', 'size'):
            with self.subTest(change=change):
                def mutate(plan):
                    if change == 'policy':plan['policy']['id'] = 'other-policy'
                    if change == 'location':plan['payload']['key'] = 'releases/r1-a1/other.zip'
                    if change == 'version':plan['payload']['version_id'] = 'absent-version'
                    if change == 'size':plan['payload']['size'] += 1
                self.forge(mutate_plan=mutate)
                self.assertEqual(self.read().state, custody.CustodyState.INVALID)

    def test_schema_missing_fields_invalid_types_and_inventory_digests(self):
        for change in ('schema', 'missing', 'type', 'digest', 'extra'):
            with self.subTest(change=change):
                def mutate(plan):
                    if change == 'schema':plan['schema_version'] = 99
                    if change == 'missing':plan.pop('verifier')
                    if change == 'type':plan['inventory'][0]['size'] = str(plan['inventory'][0]['size'])
                    if change == 'digest':plan['inventory'][0]['sha256'] = '0' * 64
                    if change == 'extra':plan['unrecognized'] = True
                self.forge(mutate_plan=mutate)
                self.assertEqual(self.read().state, custody.CustodyState.INVALID)

    def test_selected_source_zip_digest_cannot_be_claimed_as_preserved(self):
        def mutate(plan):
            item = next(m for m in plan['materials'] if m['origin']['kind'] == 'github-artifact')
            item['origin']['zip_preserved'] = True
        self.forge(mutate_plan=mutate)
        self.assertEqual(self.read().state, custody.CustodyState.INVALID)

    def test_unauthorized_extra_or_missing_material_is_rejected(self):
        for change in ('missing', 'extra'):
            with self.subTest(change=change):
                def mutate(files):
                    if change == 'missing':files.pop('source/melange/certificates/manifest.json')
                    else:files['source/unrecorded.txt'] = b'extra'
                self.forge(mutate_files=mutate)
                self.assertEqual(self.read().state, custody.CustodyState.INVALID)

    def test_recovery_has_no_network_tools_or_original_scratch_fallback(self):
        self.ready()
        real_run = subprocess.run
        calls = []
        def isolated(args, **kwargs):
            calls.append(args)
            self.assertNotIn(args[0], ('gh', 'aws', 'docker', 'melange', 'curl', 'git'))
            if args[0] != 'openssl':
                self.assertEqual(set(kwargs['env']), {'PATH', 'LANG', 'PYTHONNOUSERSITE'})
                self.assertIn(str(self.root), args[3])
            return real_run(args, **kwargs)
        with patch('socket.socket', side_effect=AssertionError('network forbidden')), patch('subprocess.run', side_effect=isolated):
            recovered = self.read()
        self.assertEqual(recovered.state, custody.CustodyState.COMPLETE_VERIFIED)
        self.assertTrue(calls)

    def test_hgc03_exit_and_result_are_both_required(self):
        self.ready()
        positive = self.read()
        self.assertEqual(positive.state, custody.CustodyState.COMPLETE_VERIFIED)
        real_run = subprocess.run
        for code, output in ((1, canonical(positive.report)), (0, b'{"result":"REPRODUCED"}')):
            with self.subTest(code=code):
                def fake(args, **kwargs):
                    if args[0] == 'openssl':return real_run(args, **kwargs)
                    return subprocess.CompletedProcess(args, code, stdout=output, stderr=b'negative probe')
                with patch('subprocess.run', side_effect=fake):result = self.read()
                self.assertEqual(result.state, custody.CustodyState.INVALID)

    def test_invalid_rebuild_signature_fails_pinned_verifier_with_positive_controls(self):
        self.ready()
        self.assertEqual(self.read().state, custody.CustodyState.COMPLETE_VERIFIED)
        def mutate(files):
            core = read_zip(files['originals/melange-reproducibility.zip'])
            core['rebuild/melange.rsa.pub'] = self.attacker.public
            receipt = document(core['melange-reproducibility-evidence.json'])
            receipt['signatures']['rebuild']['public_key_sha256'] = sha256(self.attacker.public)
            raw = canonical(receipt)
            core['melange-reproducibility-evidence.json'] = raw
            files['originals/melange-reproducibility.zip'] = make_zip(core)
            for path in list(files):
                if path.startswith('candidates/') and path.endswith('/melange-reproducibility-evidence.json'):files[path] = raw
        self.forge(mutate_files=mutate)
        result = self.read()
        self.assertEqual(result.state, custody.CustodyState.INVALID)
        self.assertIn('HGC-03 verifier exit 1', result.reason)
        stderr = (self.root / f'read-{self.counter}/reports/stderr').read_text()
        self.assertIn('APKINDEX signature does not verify', stderr)
        self.store = EvidenceStore(MemoryTransport())
        self.ready()
        self.assertEqual(self.read().state, custody.CustodyState.COMPLETE_VERIFIED)

    def test_changed_apk_is_rejected_even_in_authenticated_repack(self):
        def mutate(files):
            core = read_zip(files['originals/melange-reproducibility.zip'])
            apk = next(p for p in core if p.endswith('.apk'))
            core[apk] = core[apk][:-1] + bytes([core[apk][-1] ^ 1])
            files['originals/melange-reproducibility.zip'] = make_zip(core)
        self.forge(mutate_files=mutate)
        result = self.read()
        self.assertEqual(result.state, custody.CustodyState.INVALID)
        self.assertIn('rebuild output hash/size differs', result.reason)

    def test_existing_extraction_directory_is_never_overwritten(self):
        self.ready()
        occupied = self.root / 'occupied'
        occupied.mkdir()
        (occupied / 'sentinel').write_bytes(b'keep')
        result = self.read(target=occupied)
        self.assertEqual(result.state, custody.CustodyState.INVALID)
        self.assertEqual((occupied / 'sentinel').read_bytes(), b'keep')
