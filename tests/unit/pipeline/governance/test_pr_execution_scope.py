"""Independent path/profile tests for PR validation selection."""

import unittest

from scripts.pipeline.governance.pr_execution_scope import profile_for_paths


class PRExecutionScopeTests(unittest.TestCase):
    def assert_profile(self, expected, *paths):
        self.assertEqual(profile_for_paths(paths), expected)

    def test_go_specific_framework_change_uses_p0_04(self):
        self.assert_profile('P0_04', 'frameworks/go1-26.yaml')
        self.assert_profile('P0_04', 'frameworks/go1-26-dev.yaml',
                            'tests/runtime/projects/go/main.go')

    def test_docs_only_change_remains_p0_04(self):
        self.assert_profile('P0_04', 'docs/repository-architecture.md',
                            'docs/corporate-production-readiness.md')

    def test_shared_workflow_and_pipeline_changes_use_full(self):
        self.assert_profile('FULL', '.github/workflows/build-base-images.yml')
        self.assert_profile('FULL', '.reusable-workflows/.github/workflows/test-runtime-images.yml')
        self.assert_profile('FULL', 'scripts/pipeline/runtime/runtime_images.py')

    def test_shared_composition_ca_scanner_and_trust_use_full(self):
        self.assert_profile('FULL', 'distroless/image-base.yaml')
        self.assert_profile('FULL', 'melange/image-base-ca-certificates.yaml')
        self.assert_profile('FULL', 'scripts/pipeline/artifacts/scan_images.py')
        self.assert_profile('FULL', 'scripts/pipeline/governance/wolfi_trust.py')

    def test_non_p0_framework_and_ambiguous_paths_fail_safe_to_full(self):
        for path in ('frameworks/java21.yaml', 'frameworks/nodejs22.yaml',
                     'frameworks/python3-13.yaml', 'frameworks/dotnet10.yaml',
                     'frameworks/go1-25.yaml', 'frameworks/go1-25-dev.yaml',
                     'Makefile', 'unknown/path'):
            with self.subTest(path=path):
                self.assert_profile('FULL', path)


if __name__ == '__main__':
    unittest.main()
