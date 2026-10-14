"""DEV/HOM Environment bootstrap; the branch protection profile is not its job."""

import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('configure_github', ROOT / 'infra/lifecycle/configure_github.py')
github = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(github)


class FakeApi:
    """Records every GitHub call; Environments are absent unless given."""

    def __init__(self, environments=None):
        self.calls = []
        self.environments = environments or {}

    def __call__(self, path, method='GET', payload=None, missing=False):
        self.calls.append((method, path))
        if path.endswith('/deployment-branch-policies'):
            return {'branch_policies': [{'name': 'develop', 'type': 'branch'}]} if method == 'GET' else {}
        if path.startswith('environments/'):
            return self.environments.get(path.split('/')[1]) if method == 'GET' else {}
        if path == 'branches/develop':
            return {'name': 'develop'}
        raise AssertionError(f'unexpected GitHub call: {method} {path}')


class ConfigureGithubTests(unittest.TestCase):
    def test_environment_bootstrap_never_writes_branch_protection(self):
        # On 2026-09-30 this bootstrap replaced the accepted LAB protection of
        # develop with a fixed profile; protection now belongs to the owner.
        fake = FakeApi()
        with patch.object(github, 'api', side_effect=fake), contextlib.redirect_stdout(io.StringIO()):
            github.main()
        self.assertEqual([call for call in fake.calls if 'protection' in call[1]], [])
        self.assertEqual([call for call in fake.calls if call[0] != 'GET'],
                         [('PUT', 'environments/DEV'), ('PUT', 'environments/HOM')])

    def test_existing_review_gates_are_preserved_for_an_explicit_migration(self):
        fake = FakeApi({'HOM': {'protection_rules': [{'type': 'required_reviewers'}]}})
        with patch.object(github, 'api', side_effect=fake), self.assertRaises(ValueError), \
                contextlib.redirect_stdout(io.StringIO()):
            github.main()
        self.assertNotIn(('PUT', 'environments/HOM'), fake.calls)


if __name__ == '__main__':
    unittest.main()
