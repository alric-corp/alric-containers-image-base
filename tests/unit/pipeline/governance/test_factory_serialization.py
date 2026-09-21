"""Candidate-producing runs share a slot; read-only PR validation does not."""
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[4]


class FactorySerializationTests(unittest.TestCase):
    def test_slot_covers_the_whole_reusable_candidate_pipeline(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/workflow.yml').read_text())
        job = workflow['jobs']['build-base-images']
        self.assertEqual(job['uses'], './.github/workflows/build-base-images.yml')
        self.assertEqual(job['concurrency'], {
            'group': 'factory-build-publish-${{ github.repository }}',
            'cancel-in-progress': False,
        })
        for event in ('push', 'workflow_dispatch', 'github.event.schedule'):
            self.assertIn(event, job['if'])
        # No event/ref/run-specific lock: every candidate trigger competes for
        # the same repository slot until validation through attestation ends.
        self.assertNotIn('concurrency', workflow)
        for identifier in ('validate-pr', 'validate-pr-full'):
            self.assertNotIn('factory-build-publish',
                             str(workflow['jobs'][identifier].get('concurrency')))


if __name__ == '__main__':
    unittest.main()
