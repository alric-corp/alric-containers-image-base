"""Workflow guards for an Infra-owned, publication-only ECR destination."""

from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / '.github/workflows/build-base-images.yml'
PREFLIGHT = ROOT / 'scripts/pipeline/release/validate_ecr_repository.py'


class PublisherPreprovisionedEcrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text()
        document = yaml.safe_load(cls.text)
        cls.steps = document['jobs']['build-push']['steps']

    def test_publisher_contains_no_ecr_provisioning_or_configuration_write(self):
        normalized = re.sub(r'[^a-z0-9]', '', self.text.lower() + PREFLIGHT.read_text().lower())
        forbidden = (
            'createrepository',
            'putimagetagmutability',
            'putimagescanningconfiguration',
            'putlifecyclepolicy',
            'setrepositorypolicy',
            'tagresource',
            'untagresource',
        )
        for operation in forbidden:
            with self.subTest(operation=operation):
                self.assertNotIn(operation, normalized)

    def test_read_only_preflight_precedes_login_and_publication(self):
        names = [step.get('name') for step in self.steps]
        preflight = names.index('Validate pre-provisioned ECR repository')
        login = names.index('Login to Amazon ECR')
        publication = names.index('Publish validated OCI artifact (multi-arch)')
        self.assertLess(preflight, login)
        self.assertLess(login, publication)

        command = self.steps[preflight]['run']
        self.assertIn('aws ecr describe-repositories', command)
        self.assertIn('scripts.pipeline.release.validate_ecr_repository', command)
        self.assertNotIn('continue-on-error', self.steps[preflight])

    def test_missing_repository_fails_with_infra_source_of_truth_message(self):
        step = next(step for step in self.steps
                    if step.get('name') == 'Validate pre-provisioned ECR repository')
        command = step['run']
        self.assertIn('RepositoryNotFoundException', command)
        self.assertIn('Pre-provisioned ECR repository not found.', command)
        self.assertIn('alric-containers-registry', command)
        self.assertIn('exit 1', command)

    def test_repository_name_is_derived_from_validated_framework(self):
        step = next(step for step in self.steps
                    if step.get('name') == 'Validate pre-provisioned ECR repository')
        self.assertEqual(step['env']['FRAMEWORK'], '${{ matrix.framework }}')
        self.assertIn('REPO="image-base-${FRAMEWORK}"', step['run'])


if __name__ == '__main__':
    unittest.main()
