"""Batch promotion health must come from exact attempt evidence, not a green job."""
import copy
from datetime import datetime, timezone
import io
import json
import unittest
from unittest.mock import Mock
import zipfile

from scripts.pipeline.operations import operational_health as health


PAIR = ['go1-26', 'go1-26-dev']
RUN = {'id': 42, 'run_attempt': 2, 'event': 'schedule', 'head_branch': 'main',
       'created_at': '2026-09-21T09:17:00Z'}
NOW = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)


def documents():
    result = {'promotion-batch.json': {
        'schema_version': 1, 'frameworks': PAIR, 'units': [PAIR],
        'prewrite_authorized': True, 'promoted': True}}
    for framework, char in zip(PAIR, 'ab'):
        digest = 'sha256:' + char * 64
        result[f'promotion-{framework}-2/promotion-evidence.json'] = {
            'promoted': True, 'candidate_digest': digest,
            'stable_digest_observed': digest, 'read_back_status': 'confirmed',
            'pair_authorization': {
                'source_run_id': '31', 'source_attempt': '1', 'status': 'PAIR_BOUND',
                'runtime_digest': 'sha256:' + 'a' * 64,
                'dev_digest': 'sha256:' + 'b' * 64}}
    return result


def archive(documents):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as zipped:
        for name, document in documents.items():
            zipped.writestr(name, json.dumps(document))
    return output.getvalue()


class BatchArtifactTests(unittest.TestCase):
    def setUp(self):
        self.listing = {'total_count': 1, 'artifacts': [{
            'id': 71, 'name': 'promotion-batch-2', 'expired': False,
            'size_in_bytes': 4096}]}

    def evidence(self, docs=None, run=None):
        fetch = Mock(return_value=self.listing)
        fetch_archive = Mock(return_value=archive(documents() if docs is None else docs))
        result = health.batch_promotion_evidence(fetch, fetch_archive, 'owner/repo', run or RUN)
        fetch.assert_called_once_with('repos/owner/repo/actions/runs/42/artifacts?per_page=100')
        fetch_archive.assert_called_once_with('repos/owner/repo/actions/artifacts/71/zip')
        return result

    def test_pair_readbacks_and_exact_attempt_are_accepted(self):
        evidence = self.evidence()
        self.assertEqual(set(evidence), set(PAIR))
        self.assertTrue(all(item['promoted'] for item in evidence.values()))

    def test_older_attempt_never_falls_back(self):
        self.listing['artifacts'][0]['name'] = 'promotion-batch-1'
        with self.assertRaisesRegex(ValueError, 'ausente'):
            self.evidence()

    def test_missing_expired_duplicate_and_truncated_inventory_fail(self):
        for mode in ('missing', 'expired', 'duplicate', 'truncated'):
            with self.subTest(mode=mode):
                original = copy.deepcopy(self.listing)
                if mode == 'missing':
                    self.listing = {'total_count': 0, 'artifacts': []}
                elif mode == 'expired':
                    self.listing['artifacts'][0]['expired'] = True
                elif mode == 'duplicate':
                    self.listing['artifacts'] *= 2
                    self.listing['total_count'] = 2
                else:
                    self.listing['total_count'] = 2
                with self.assertRaises(ValueError):
                    self.evidence()
                self.listing = original

    def test_partial_pair_or_readback_mismatch_never_sets_freshness(self):
        for field, value in (('promoted', False), ('read_back_status', 'mismatch'),
                             ('stable_digest_observed', 'sha256:' + 'c' * 64),
                             ('pair_authorization', {'source_run_id': 99})):
            with self.subTest(field=field):
                docs = documents()
                docs['promotion-go1-26-dev-2/promotion-evidence.json'][field] = value
                with self.assertRaises(ValueError):
                    self.evidence(docs)

    def test_unapproved_batch_is_not_promotion(self):
        docs = documents()
        docs['promotion-batch.json']['prewrite_authorized'] = False
        with self.assertRaises(ValueError):
            self.evidence(docs)

    def test_missing_member_or_ambiguous_units_is_a_gap(self):
        for mode in ('missing', 'units'):
            docs = documents()
            if mode == 'missing':
                del docs['promotion-go1-26-dev-2/promotion-evidence.json']
            else:
                docs['promotion-batch.json']['units'] = [PAIR, ['go1-26']]
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.evidence(docs)

    def test_all_skipped_evidence_is_valid_but_not_promoted(self):
        docs = documents()
        docs['promotion-batch.json']['promoted'] = False
        for name in PAIR:
            docs[f'promotion-{name}-2/promotion-evidence.json'] = {
                'promoted': False, 'skipped': True, 'read_back_status': 'not_run'}
        self.assertFalse(any(item['promoted'] for item in self.evidence(docs).values()))

    def test_interpreted_framework_needs_no_pair_authorization(self):
        docs = documents()
        item = docs['promotion-go1-26-2/promotion-evidence.json']
        del item['pair_authorization']
        docs = {'promotion-batch.json': {
            'schema_version': 1, 'frameworks': ['python3-13'],
            'units': [['python3-13']], 'prewrite_authorized': True, 'promoted': True},
            'promotion-python3-13-2/promotion-evidence.json': item}
        self.assertTrue(self.evidence(docs)['python3-13']['promoted'])

    def test_metadata_size_is_bounded_before_archive_download(self):
        self.listing['artifacts'][0]['size_in_bytes'] = health.BATCH_ARCHIVE_LIMIT + 1
        fetch_archive = Mock()
        with self.assertRaisesRegex(ValueError, 'tamanho'):
            health.batch_promotion_evidence(lambda _: self.listing, fetch_archive,
                                            'owner/repo', RUN)
        fetch_archive.assert_not_called()


class BatchFreshnessTests(unittest.TestCase):
    def collect(self, evidence, conclusion='success'):
        job = {'name': health.BATCH_PROMOTE_JOB, 'conclusion': conclusion,
               'completed_at': '2026-09-21T10:00:00Z'}
        reader = Mock(side_effect=evidence if isinstance(evidence, Exception) else None,
                      return_value=evidence)
        result = health.framework_health(lambda _: [job], [RUN], PAIR, NOW,
                                          promotion_evidence_for=reader)
        return result, reader

    def test_successful_batch_requires_evidence_for_each_framework(self):
        evidence = {name: {'promoted': True} for name in PAIR}
        result, reader = self.collect(evidence)
        reader.assert_called_once_with(RUN)
        for item in result['frameworks'].values():
            self.assertEqual(item['stable_age_hours'], 2)
            self.assertEqual(item['promotion_source'], 'confirmed_batch_evidence')

    def test_failed_job_cannot_authorize_even_if_artifact_claims_pass(self):
        result, reader = self.collect({name: {'promoted': True} for name in PAIR}, 'failure')
        reader.assert_not_called()
        self.assertTrue(all(item['stable_age_hours'] is None
                            for item in result['frameworks'].values()))

    def test_green_batch_with_missing_artifact_is_visible_gap(self):
        result, _ = self.collect(ValueError('artifact expirado'))
        self.assertEqual(result['promotion_evidence_gaps'],
                         [{'run_id': 42, 'reason': 'artifact expirado'}])
        self.assertTrue(all(item['stable_age_hours'] is None
                            for item in result['frameworks'].values()))

    def test_skipped_pair_is_checked_but_never_promoted(self):
        result, _ = self.collect({name: {'promoted': False, 'skipped': True} for name in PAIR})
        for item in result['frameworks'].values():
            self.assertIsNone(item['stable_age_hours'])
            self.assertEqual(item['promotion_checked_age_hours'], 2)


if __name__ == '__main__':
    unittest.main()
