"""G07: fail-closed acceptance scenarios for DEV->HOM promotion and recovery.

Local regression cases for the hosted acceptance plan
(docs/dev-hom-hosted-acceptance.md). Registry, Store, trust and scan are
replaced; each case asserts only the safety outcome: no stable movement, no
PASS or `promoted/` receipt, and holds kept wherever a write may have
happened. They do not prove HOM, IAM or ECR behavior.
"""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.pipeline.release import lifecycle as flow
from scripts.pipeline.release import release_manifest as model
from tests.unit.pipeline.consumer_apps.support import digest, good_result

CLOCK = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
PAIR = ['go1-26', 'go1-26-dev']


def policy(environment):
    return dict(schema_version=1, enabled=True, frameworks=PAIR,
                soak_hours=0 if environment == 'DEV' else 6)


def approved(run=12345, age=7):
    """DEV_STABLE manifest accepted by release_manifest.validate.

    Digests follow the consumer-app support inventory, as in test_lifecycle.
    """
    images = {}
    for name in PAIR:
        platforms = {f'linux/{arch}': digest(name + arch) for arch in ('amd64', 'arm64')}
        index = digest(name)
        images[name] = dict(digest=index, platforms=platforms, tag=f'131026-0000-r{run}-a1',
                            sboms=[dict(subject=item, predicate_digest=digest('SBOM'))
                                   for item in [index, *platforms.values()]])
    manifest = dict(schema_version=1, release_id=f'r{run}-a1', run_id=run, attempt=1, source_sha='a' * 40,
                    repository=model.configuration()['repository'], branch='develop',
                    source_registry=model.registry('DEV'), units=[PAIR], images=images,
                    state='DEV_STABLE', dev_stable_at=(CLOCK - timedelta(hours=age)).isoformat(),
                    dev_readback={name: item['digest'] for name, item in images.items()},
                    consumer_results={})
    for arch in ('amd64', 'arm64'):
        result = good_result(architecture=arch)
        result['source_run_id'] = run
        for role, name in (('runtime', PAIR[0]), ('dev', PAIR[1])):
            result[role + '_image_ref'] = f'{manifest["source_registry"]}/image-base-{name}@{images[name]["digest"]}'
        manifest['consumer_results'][f'go1-26-{arch}'] = result
    return manifest


class MemoryStore:
    """Release Store double with the immutable-record semantics of release_store.Store."""

    def __init__(self, records=None):
        self.records = copy.deepcopy(records or {})

    def get(self, key, optional=False):
        if key not in self.records:
            if optional:
                return None
            raise ValueError('missing record: ' + key)
        return copy.deepcopy(self.records[key])

    def put(self, key, value, immutable=False):
        if immutable and key in self.records and self.records[key] != value:
            raise ValueError('immutable release record already exists with different content')
        self.records[key] = copy.deepcopy(value)

    def keys(self, prefix):
        return [key for key in self.records if key.startswith(prefix)]

    def held(self, name):
        return (self.records.get(f'state/{name}.json') or {}).get('hold') is True

    def receipts(self, suffix):
        return [key for key in self.records if key.startswith('events/') and key.endswith(suffix)]


class AcceptanceCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.reports = Path(directory.name)
        for patcher in (patch.dict(os.environ, GITHUB_RUN_ID='555', GITHUB_RUN_ATTEMPT='1',
                                   GITHUB_EVENT_NAME='workflow_dispatch'),
                        patch.object(flow, 'now', return_value=CLOCK),
                        patch.object(flow, 'promotion_policy', side_effect=policy),
                        patch.object(flow, 'validate_destination'),
                        patch.object(flow, 'load_quarantined_digests', return_value=[])):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.manifest = approved()
        self.source = MemoryStore({flow.manifest_key(self.manifest['release_id']): self.manifest})
        self.target = MemoryStore()

    def stores(self):
        return patch.object(flow, 'Store', side_effect=lambda environment: {
            'DEV': self.source, 'HOM': self.target}[environment])

    def args(self, **values):
        return SimpleNamespace(**dict(dict(release=None, soak_hours=6, resume=False, reports=self.reports),
                                      **values))

    def outcome(self):
        return json.loads((self.reports / 'release-outcome.json').read_text())

    def assert_no_stable_movement(self, store):
        self.assertEqual(store.keys('promoted/'), [])
        self.assertEqual(store.receipts('/completed.json'), [])


class PromotionPreWriteTests(AcceptanceCase):
    """Every gate before the first tag write keeps HOM untouched."""

    def promote(self, **patches):
        defaults = dict(verify_image=None, scan_images=0, copy_image=None, read_index=None)
        defaults.update(patches)
        mocks = {}
        with self.stores(), patch.object(flow, 'publish_states') as publish:
            stack = []
            for name, value in defaults.items():
                kwargs = {'side_effect': value} if callable(value) or isinstance(value, Exception) \
                    else {'return_value': value}
                stack.append(patch.object(flow, name, **kwargs))
            for patcher in stack:
                mocks[patcher.attribute] = patcher.start()
            try:
                with self.assertRaises(ValueError):
                    flow.promote_hom(self.args(release=self.manifest['release_id']))
            finally:
                for patcher in stack:
                    patcher.stop()
        publish.assert_not_called()
        self.assert_no_stable_movement(self.target)
        self.assertEqual(self.target.keys('state/'), [])
        return mocks

    def test_missing_dev_approval_is_rejected_before_any_copy(self):
        self.source.records.clear()
        mocks = self.promote()
        mocks['copy_image'].assert_not_called()

    def test_divergent_hom_manifest_for_the_same_release_is_rejected(self):
        divergent = copy.deepcopy(self.manifest)
        divergent['images']['go1-26']['tag'] = '131026-0001-r12345-a1'
        key = flow.manifest_key(self.manifest['release_id'])
        self.target.records[key] = divergent
        self.promote()
        self.assertEqual(self.target.records[key], divergent)

    def test_target_tag_resolving_to_another_digest_blocks_the_release(self):
        def read_index(image, item, directory):
            if image.startswith(model.registry('HOM')):
                raise ValueError('index digest does not match the release')
        self.promote(read_index=read_index)
        self.assertNotIn(flow.manifest_key(self.manifest['release_id']), self.target.records)

    def test_quarantined_digest_is_rejected_before_copy(self):
        with patch.object(flow, 'load_quarantined_digests',
                          return_value=[self.manifest['images']['go1-26']['digest']]):
            mocks = self.promote()
        mocks['copy_image'].assert_not_called()

    def test_one_corrupted_dev_record_stops_selection_instead_of_splitting(self):
        broken = approved(12346)
        broken['dev_readback']['go1-26-dev'] = digest('other')
        self.source.records[flow.manifest_key(broken['release_id'])] = broken
        with self.stores(), patch.object(flow, 'copy_image') as copy_image, \
                patch.object(flow, 'publish_states') as publish, self.assertRaises(ValueError):
            flow.promote_hom(self.args())
        copy_image.assert_not_called()
        publish.assert_not_called()

    def test_failed_gate_never_reports_promotion_to_operational_health(self):
        def verify(manifest, name, registry, directory):
            if registry == model.registry('HOM'):
                raise ValueError('target attestation missing')
        self.promote(verify_image=verify)
        batch = json.loads((self.reports / 'health/promotion-batch.json').read_text())
        self.assertEqual((batch['promoted'], batch['prewrite_authorized']), (False, False))
        for name in PAIR:
            evidence = json.loads((self.reports / f'health/promotion-{name}-1/promotion-evidence.json').read_text())
            self.assertEqual((evidence['promoted'], evidence['read_back_status']), (False, 'not_run'))

    def test_explicit_rerun_of_a_completed_promotion_is_refused_without_copy(self):
        for name, item in self.manifest['images'].items():
            self.target.records[f'state/{name}.json'] = dict(
                release_id=self.manifest['release_id'], digest=item['digest'], hold=False,
                high_watermark=[self.manifest['run_id'], 1])
        with self.stores(), patch.object(flow, 'copy_image') as copy_image, self.assertRaises(ValueError):
            flow.promote_hom(self.args(release=self.manifest['release_id']))
        copy_image.assert_not_called()


class StableWriteTests(AcceptanceCase):
    """Partial and ambiguous writes leave an operator-visible pause."""

    def before(self):
        return {name: None for name in PAIR}

    def test_stable_changed_outside_the_factory_blocks_before_holds_and_writes(self):
        before = {name: dict(release_id='r1-a1', digest=digest(name + 'old'), hold=False,
                             high_watermark=[1, 1]) for name in PAIR}
        observed = [before['go1-26']['digest'], digest('changed by hand')]
        with patch.object(flow, 'stable_digest', side_effect=observed), \
                patch.object(flow, 'write_stable') as write, self.assertRaises(ValueError):
            flow.publish_states(self.target, self.manifest, before, 'HOM', self.reports)
        write.assert_not_called()
        self.assertEqual(self.target.records, {})

    def test_persistent_ambiguous_readback_keeps_every_member_held(self):
        # The 01/10 DEV incident failed on an ambiguous read-back after the
        # writes; whatever retries exist, it must never become a PASS.
        ambiguous = ValueError('ambiguous stable read-back')
        with patch.object(flow, 'write_stable'), \
                patch.object(flow, 'stable_digest', side_effect=[None, None] + [ambiguous] * 4), \
                self.assertRaises(ValueError):
            flow.publish_states(self.target, self.manifest, self.before(), 'HOM', self.reports)
        for name in PAIR:
            self.assertTrue(self.target.held(name))
            self.assertEqual(self.target.records[f'state/{name}.json']['pending_release'],
                             self.manifest['release_id'])
        self.assert_no_stable_movement(self.target)
        self.assertEqual(len(self.target.receipts('/failed.json')), 1)
        self.assertEqual(self.outcome()['status'], 'FAIL')

    def test_abrupt_interruption_after_one_member_leaves_holds_and_no_pass(self):
        written = []

        def write(manifest, name, environment, reports):
            written.append(name)
            if len(written) == 2:
                raise KeyboardInterrupt  # runner killed: no except clause runs
        with patch.object(flow, 'write_stable', side_effect=write), \
                patch.object(flow, 'stable_digest', return_value=None), self.assertRaises(KeyboardInterrupt):
            flow.publish_states(self.target, self.manifest, self.before(), 'HOM', self.reports)
        self.assertTrue(all(self.target.held(name) for name in PAIR))
        self.assertEqual(len(self.target.receipts('/started.json')), 1)
        self.assertEqual(self.target.receipts('/failed.json'), [])
        self.assert_no_stable_movement(self.target)
        self.assertEqual(self.outcome()['status'], 'IN_PROGRESS')

    def test_metadata_failure_after_the_tag_writes_re_holds_the_pair(self):
        original = self.target.put

        def put(key, value, immutable=False):
            if key == 'state/go1-26-dev.json' and value.get('hold') is False:
                raise OSError('S3 unavailable')
            return original(key, value, immutable)
        digests = [self.manifest['images'][name]['digest'] for name in PAIR]
        with patch.object(self.target, 'put', side_effect=put), patch.object(flow, 'write_stable'), \
                patch.object(flow, 'stable_digest', side_effect=[None, None] + digests * 2), \
                self.assertRaises(OSError):
            flow.publish_states(self.target, self.manifest, self.before(), 'HOM', self.reports)
        for name in PAIR:
            self.assertTrue(self.target.held(name))
            self.assertEqual(self.target.records[f'state/{name}.json']['reason'], 'incomplete stable operation')

    def test_readback_failures_are_never_treated_as_no_stable(self):
        def describe(*details):
            return json.dumps({'imageDetails': list(details)}).encode()
        entry = {'imageDigest': digest('a'), 'imageTags': ['stable']}
        for response in (describe(entry, dict(entry, imageDigest=digest('b'))),
                         describe(dict(entry, imageTags=['131026-0000-r1-a1'])), describe()):
            with self.subTest(response=response), patch.object(flow, 'aws', return_value=response), \
                    self.assertRaises(ValueError):
                flow.stable_digest('HOM', 'go1-26')
        denied = subprocess.CalledProcessError(254, ['aws'], stderr=b'(AccessDeniedException)')
        with patch.object(flow, 'aws', side_effect=denied), self.assertRaises(subprocess.CalledProcessError):
            flow.stable_digest('HOM', 'go1-26')
        missing = subprocess.CalledProcessError(254, ['aws'], stderr=b'(ImageNotFoundException)')
        with patch.object(flow, 'aws', side_effect=missing):
            self.assertIsNone(flow.stable_digest('HOM', 'go1-26'))


class ReexecutionTests(AcceptanceCase):
    def test_interruption_between_manifest_and_writes_completes_exactly_once(self):
        digests = [self.manifest['images'][name]['digest'] for name in PAIR]
        gates = (patch.object(flow, 'verify_image'), patch.object(flow, 'scan_images', return_value=0),
                 patch.object(flow, 'copy_image'), patch.object(flow, 'read_index'))
        for gate in gates:
            gate.start()
            self.addCleanup(gate.stop)
        with self.stores(), patch.object(flow, 'publish_states', side_effect=KeyboardInterrupt), \
                self.assertRaises(KeyboardInterrupt):
            flow.promote_hom(self.args())
        self.assertIn(flow.manifest_key(self.manifest['release_id']), self.target.records)
        self.assertEqual(self.target.keys('state/'), [])
        with self.stores(), patch.object(flow, 'write_stable'), \
                patch.object(flow, 'stable_digest', side_effect=[None, None] + digests):
            flow.promote_hom(self.args())
        self.assertEqual(self.target.keys('promoted/'), ['promoted/' + self.manifest['release_id'] + '.json'])
        self.assertEqual(self.target.records[flow.manifest_key(self.manifest['release_id'])], self.manifest)
        for name in PAIR:
            self.assertFalse(self.target.held(name))
        with self.stores(), patch.object(flow, 'publish_states') as publish:
            flow.promote_hom(self.args())
        publish.assert_not_called()
        self.assertEqual(self.outcome()['status'], 'SKIPPED')


class RecoveryTests(AcceptanceCase):
    """Recovery restores only a completed HOM release whose bytes still pass."""

    def setUp(self):
        super().setUp()
        self.target.records.update({
            flow.manifest_key(self.manifest['release_id']): self.manifest,
            f'promoted/{self.manifest["release_id"]}.json': {
                'manifest_digest': model.checksum(self.manifest),
                'digests': {name: item['digest'] for name, item in self.manifest['images'].items()}}})

    def recover(self, reason='regression in newer release', **patches):
        values = dict(verify_image=None, scan_images=0)
        values.update(patches)
        with patch.object(flow, 'Store', return_value=self.target), \
                patch.object(flow, 'verify_image', side_effect=values['verify_image']), \
                patch.object(flow, 'scan_images', return_value=values['scan_images']), \
                patch.object(flow, 'publish_states') as publish:
            with self.assertRaises(ValueError):
                flow.recover_hom(self.args(release=self.manifest['release_id'], reason=reason))
        publish.assert_not_called()

    def test_receipt_bound_to_other_content_is_not_a_recovery_target(self):
        receipt = f'promoted/{self.manifest["release_id"]}.json'
        self.target.records[receipt]['manifest_digest'] = digest('another manifest')
        self.recover()

    def test_expired_bytes_invalid_trust_or_new_vulnerability_block_recovery(self):
        for label, patches in (('expired', dict(verify_image=ValueError('MANIFEST_UNKNOWN'))),
                               ('trust', dict(verify_image=ValueError('provenance does not bind the run'))),
                               ('vulnerability', dict(scan_images=1))):
            with self.subTest(label=label):
                self.recover(**patches)
        self.assertEqual(self.target.keys('state/'), [])

    def test_recovery_requires_an_operational_reason(self):
        with patch.object(flow, 'Store') as store, self.assertRaises(ValueError):
            flow.recover_hom(self.args(release=self.manifest['release_id'], reason='   '))
        store.assert_not_called()

    def test_successful_recovery_keeps_the_post_recovery_pause(self):
        before = {name: dict(release_id='r99999-a1', digest=digest(name + 'newer'), hold=False,
                             high_watermark=[99999, 1]) for name in PAIR}
        for name, state in before.items():
            self.target.records[f'state/{name}.json'] = state
        digests = [self.manifest['images'][name]['digest'] for name in PAIR]
        with patch.object(flow, 'Store', return_value=self.target), patch.object(flow, 'verify_image'), \
                patch.object(flow, 'scan_images', return_value=0), patch.object(flow, 'write_stable'), \
                patch.object(flow, 'stable_digest', side_effect=[before[name]['digest'] for name in PAIR] + digests):
            flow.recover_hom(self.args(release=self.manifest['release_id'], reason='regression in r99999-a1'))
        for name in PAIR:
            state = self.target.records[f'state/{name}.json']
            self.assertEqual((state['hold'], state['high_watermark'], state['release_id']),
                             (True, [99999, 1], self.manifest['release_id']))
        [completed] = self.target.receipts('/completed.json')
        self.assertEqual((self.target.records[completed]['action'], self.target.records[completed]['status']),
                         ('recovery', 'PASS'))
        self.assertEqual(self.target.keys('promoted/'), ['promoted/' + self.manifest['release_id'] + '.json'])


class EntrypointTests(AcceptanceCase):
    def run_main(self, *argv, enabled=True):
        with patch.object(flow, 'promotion_policy', side_effect=lambda environment: dict(
                policy(environment), enabled=enabled)), patch.object(flow, 'Store') as store:
            code = flow.main([*argv, '--reports', str(self.reports)])
        # Constructing a Store reads only local configuration; no record is read.
        store.return_value.get.assert_not_called()
        store.return_value.keys.assert_not_called()
        return code

    def test_resume_requires_an_explicit_manual_dispatch(self):
        with patch.dict(os.environ, GITHUB_EVENT_NAME='schedule'):
            self.assertEqual(self.run_main('promote-hom', '--resume', '--release', 'r12345-a1'), 1)
        self.assertEqual(self.outcome()['status'], 'FAIL')

    def test_disabled_hom_promotion_exits_without_touching_the_store(self):
        self.assertEqual(self.run_main('promote-hom', enabled=False), 1)
        self.assertIn('disabled', self.outcome()['error'])

    def test_release_identity_must_be_exact(self):
        for release in ('latest', 'r12345', 'r12345-a1; rm -rf /', ''):
            with self.subTest(release=release):
                self.assertEqual(self.run_main('recover-hom', '--release', release, '--reason', 'x'), 1)


if __name__ == '__main__':
    unittest.main()
