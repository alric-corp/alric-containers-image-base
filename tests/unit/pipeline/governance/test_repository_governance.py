"""G02: branch protection profiles, CODEOWNERS template and read-only verify."""
import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.pipeline.governance import repository_protection as governance

ROOT = Path(__file__).resolve().parents[4]
REPOSITORY = 'alric-corp/alric-containers-image-base'
# Only what the contract reads; the rest of the tree is irrelevant here.
SUBTREES = ('.github/workflows', 'policies', 'melange/keys', 'melange/certificates', 'infra/iam')
FILES = ('scripts/pipeline/governance/wolfi_trust.py', 'scripts/verify-image.sh', 'infra/backend.py')


def live_protection(**changes):
    protection = {
        'required_status_checks': {'strict': True, 'contexts': ['Unit & integration tests',
                                                                'Repository & workflow lint'],
                                   'checks': [{'context': 'Unit & integration tests', 'app_id': 15368},
                                              {'context': 'Repository & workflow lint', 'app_id': 15368}]},
        'required_pull_request_reviews': {'dismiss_stale_reviews': True,
                                          'require_code_owner_reviews': False,
                                          'require_last_push_approval': False,
                                          'required_approving_review_count': 0},
        'required_signatures': {'enabled': False}, 'enforce_admins': {'enabled': False},
        'required_linear_history': {'enabled': False}, 'allow_force_pushes': {'enabled': False},
        'allow_deletions': {'enabled': False}, 'block_creations': {'enabled': False},
        'required_conversation_resolution': {'enabled': False}, 'lock_branch': {'enabled': False},
        'allow_fork_syncing': {'enabled': False}}
    protection.update(changes)
    return protection


def live_environments():
    def environment(name, reviewers=None):
        rules = [{'type': 'branch_policy'}]
        if reviewers is not None:
            rules.insert(0, {'type': 'required_reviewers', 'prevent_self_review': False,
                             'reviewers': [{'type': 'User', 'reviewer': {'login': login}}
                                           for login in reviewers]})
        return {'name': name, 'can_admins_bypass': False, 'protection_rules': rules,
                'deployment_branch_policy': {'protected_branches': False,
                                             'custom_branch_policies': True}}
    return {'environments': [environment('DEV'), environment('HOM'),
                             environment('lab-image-base-infra', ['TomasAlric'])]}


class FakeGitHub:
    """GET responses keyed by path; every call is recorded."""

    def __init__(self, protection=None, rulesets=None, environments=None, policies=None):
        self.calls = []
        self.responses = {
            f'repos/{REPOSITORY}/branches/develop/protection': (200, protection or live_protection()),
            f'repos/{REPOSITORY}/rulesets?includes_parents=true': (200, [] if rulesets is None else rulesets),
            f'repos/{REPOSITORY}/environments?per_page=100': (200, environments or live_environments()),
        }
        for name in ('DEV', 'HOM', 'lab-image-base-infra'):
            branch_policies = (policies or {}).get(name, [{'name': 'develop', 'type': 'branch'}])
            self.responses[f'repos/{REPOSITORY}/environments/{name}/deployment-branch-policies'] = (
                200, {'total_count': len(branch_policies), 'branch_policies': branch_policies})

    def __call__(self, path):
        self.calls.append(path)
        response = self.responses[path]
        if isinstance(response, Exception):
            raise response
        return response


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for subtree in SUBTREES:
            shutil.copytree(ROOT / subtree, self.root / subtree,
                            ignore=shutil.ignore_patterns('.terraform', '*.tfstate*'))
        for name in FILES:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, self.root / name)

    def contract(self):
        return json.loads((self.root / governance.POLICY).read_text())

    def write(self, contract):
        (self.root / governance.POLICY).write_text(json.dumps(contract))

    def test_repository_contract_and_template_are_consistent(self):
        self.assertEqual(governance.lint(ROOT), [])

    def test_lab_profile_is_the_accepted_exception_not_a_corporate_approval(self):
        contract = governance.load(ROOT)
        lab, corporate = contract['profiles']['lab'], contract['profiles']['corporate']
        self.assertEqual(lab['status'], 'OWNER_ACCEPTED_LAB_EXCEPTION')
        self.assertEqual(corporate['status'], 'PROPOSED_AWAITING_APPROVAL')
        self.assertEqual(lab['protection']['required_pull_request_reviews']
                         ['required_approving_review_count'], 0)
        self.assertFalse(lab['protection']['enforce_admins'])
        for status in ('APPROVED', 'PROPOSED_AWAITING_APPROVAL'):
            contract = self.contract()
            contract['profiles']['lab']['status'] = status
            self.write(contract)
            with self.subTest(status=status), self.assertRaises(ValueError):
                governance.load(self.root)
        contract = self.contract()
        contract['profiles']['corporate']['status'] = 'OWNER_ACCEPTED_LAB_EXCEPTION'
        self.write(contract)
        with self.assertRaises(ValueError):
            governance.load(self.root)

    def test_duplicate_or_unknown_keys_are_rejected(self):
        text = (self.root / governance.POLICY).read_text()
        (self.root / governance.POLICY).write_text(text.replace('"branch": "develop",',
                                                                '"branch": "develop", "branch": "main",', 1))
        with self.assertRaises(ValueError):
            governance.load(self.root)
        contract = json.loads(text)
        contract['profiles']['corporate']['protection']['bypass'] = True
        self.write(contract)
        with self.assertRaises(ValueError):
            governance.load(self.root)

    def test_path_filtered_or_foreign_checks_cannot_become_required(self):
        # Infra checks only run for infra paths: requiring them would leave
        # every other PR waiting for a check that never reports.
        for check in ({'context': 'Infra contracts and formatting', 'app_id': 15368},
                      {'context': 'Resolve PR execution profile', 'app_id': 15368},
                      {'context': 'Unit & integration tests', 'app_id': 1}):
            contract = self.contract()
            checks = contract['profiles']['corporate']['protection']['required_status_checks']['checks']
            checks[:] = [item for item in checks if item['context'] != check['context']] + [check]
            self.write(contract)
            with self.subTest(check=check):
                self.assertTrue(governance.lint(self.root))

    def test_corporate_profile_can_never_relax_the_lab_profile(self):
        for mutate in (lambda p: p.update(enforce_admins=False),
                       lambda p: p['required_pull_request_reviews'].update(required_approving_review_count=0),
                       lambda p: p['required_pull_request_reviews'].update(require_code_owner_reviews=False),
                       lambda p: p['required_pull_request_reviews'].update(require_last_push_approval=False),
                       lambda p: p['required_pull_request_reviews'].update(dismiss_stale_reviews=False),
                       lambda p: p.update(allow_force_pushes=True),
                       lambda p: p.update(allow_deletions=True),
                       lambda p: p.update(required_conversation_resolution=False),
                       lambda p: p['required_status_checks']['checks'].pop()):
            contract = self.contract()
            mutate(contract['profiles']['corporate']['protection'])
            self.write(contract)
            with self.subTest(mutate=mutate):
                self.assertTrue(governance.lint(self.root))

    def test_every_environment_used_by_workflows_is_part_of_the_contract(self):
        original = self.contract()
        contract = copy.deepcopy(original)
        for profile in contract['profiles'].values():
            profile['environments'].pop('HOM')
        self.write(contract)
        self.assertTrue(any('environments' in problem for problem in governance.lint(self.root)))
        contract = copy.deepcopy(original)
        contract['profiles']['corporate']['environments']['HOM']['prevent_self_review'] = False
        self.write(contract)
        self.assertIn('corporate/HOM: required reviewers must prevent self-review',
                      governance.lint(self.root))
        contract = copy.deepcopy(original)
        contract['profiles']['lab']['environments']['DEV']['branches'] = ['develop', 'main']
        self.write(contract)
        self.assertTrue(governance.lint(self.root))

    def test_template_keeps_placeholders_and_explicit_privileged_ownership(self):
        template = self.root / governance.TEMPLATE
        original = template.read_text()
        template.write_text(original.replace('@<org>/<factory-maintainers>', '@alric-corp/team', 1))
        self.assertTrue(any('only holds placeholders' in problem for problem in governance.lint(self.root)))
        template.write_text('\n'.join(line for line in original.splitlines()
                                      if 'renovate.yml' not in line) + '\n')
        self.assertIn(f'{governance.TEMPLATE}: .github/workflows/renovate.yml must be owned only by '
                      f'{governance.SECURITY_OWNER}', governance.lint(self.root))
        template.write_text('\n'.join(line for line in original.splitlines()
                                      if not line.startswith('/policies/aws/')) + '\n')
        self.assertTrue(any('policies/aws/' in problem for problem in governance.lint(self.root)))

    def test_a_new_privileged_workflow_needs_an_explicit_security_owner(self):
        (self.root / '.github/workflows/new-publisher.yml').write_text(
            'name: x\non: workflow_dispatch\npermissions: {}\njobs:\n  publish:\n'
            '    runs-on: ubuntu-latest\n    timeout-minutes: 5\n'
            '    permissions:\n      id-token: write\n    steps:\n      - run: echo ok\n')
        self.assertIn(f'{governance.TEMPLATE}: .github/workflows/new-publisher.yml must be owned only by '
                      f'{governance.SECURITY_OWNER}', governance.lint(self.root))

    def test_active_codeowners_cannot_keep_placeholders_or_default_only_ownership(self):
        active = self.root / '.github/CODEOWNERS'
        active.write_text((self.root / governance.TEMPLATE).read_text())
        self.assertIn('.github/CODEOWNERS: active CODEOWNERS still contains template placeholders',
                      governance.lint(self.root))
        active.write_text('* @corp/factory\n')
        self.assertTrue(any('needs an explicit owner rule' in problem
                            for problem in governance.lint(self.root)))
        explicit = ((self.root / governance.TEMPLATE).read_text()
                    .replace('@<org>/<factory-maintainers>', '@corp/factory')
                    .replace('@<org>/<security-reviewers>', '@corp/security')
                    .replace('@<org>/<cloud-iam-reviewers>', '@corp/cloud-iam'))
        active.write_text(explicit)
        self.assertEqual(governance.lint(self.root), [])

    def test_unsupported_codeowners_syntax_is_not_silently_interpreted(self):
        for line in ('docs/** @corp/x', '!/docs/ @corp/x', '/docs/'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                governance.parse_codeowners(line)


class VerifyTests(unittest.TestCase):
    def test_live_lab_settings_match_the_lab_profile(self):
        report = governance.verify('lab', ROOT, FakeGitHub())
        self.assertEqual((report['result'], report['differences']), ('MATCH', []))
        corporate = governance.verify('corporate', ROOT, FakeGitHub())
        self.assertEqual(corporate['result'], 'DRIFT')
        self.assertTrue(any(item.startswith('enforce_admins') for item in corporate['differences']))

    def test_drift_is_reported_for_each_relaxed_or_unmodelled_control(self):
        cases = {
            'unprotected': FakeGitHub(),
            'review count': FakeGitHub(protection=live_protection(required_pull_request_reviews={
                'dismiss_stale_reviews': True, 'require_code_owner_reviews': False,
                'require_last_push_approval': False, 'required_approving_review_count': 1})),
            'force push': FakeGitHub(protection=live_protection(allow_force_pushes={'enabled': True})),
            'missing check': FakeGitHub(protection=live_protection(required_status_checks={
                'strict': True, 'checks': [{'context': 'Unit & integration tests', 'app_id': 15368}]})),
            'foreign app': FakeGitHub(protection=live_protection(required_status_checks={
                'strict': True, 'checks': [{'context': 'Unit & integration tests', 'app_id': 15368},
                                           {'context': 'Repository & workflow lint', 'app_id': None}]})),
            'bypass allowance': FakeGitHub(protection=live_protection(required_pull_request_reviews={
                'dismiss_stale_reviews': True, 'require_code_owner_reviews': False,
                'require_last_push_approval': False, 'required_approving_review_count': 0,
                'bypass_pull_request_allowances': {'users': [{'login': 'someone'}]}})),
            'ruleset': FakeGitHub(rulesets=[{'name': 'shadow'}]),
            'extra deployment ref': FakeGitHub(policies={'HOM': [{'name': 'develop', 'type': 'branch'},
                                                                 {'name': 'main', 'type': 'branch'}]}),
            'tag deployment rule': FakeGitHub(policies={'DEV': [{'name': 'develop', 'type': 'branch'},
                                                                {'name': 'v*', 'type': 'tag'}]}),
        }
        cases['unprotected'].responses[f'repos/{REPOSITORY}/branches/develop/protection'] = (
            404, {'message': 'Branch not protected'})
        environments = live_environments()
        environments['environments'][2]['can_admins_bypass'] = True
        cases['admin bypass'] = FakeGitHub(environments=environments)
        environments = live_environments()
        environments['environments'][2]['protection_rules'][0]['reviewers'] = []
        cases['reviewer removed'] = FakeGitHub(environments=environments)
        for label, fake in cases.items():
            with self.subTest(label=label):
                report = governance.verify('lab', ROOT, fake)
                self.assertEqual(report['result'], 'DRIFT', report)

    def test_ambiguous_or_failed_reads_are_inconclusive_never_a_match(self):
        fake = FakeGitHub()
        fake.responses[f'repos/{REPOSITORY}/branches/develop/protection'] = (404, {'message': 'Not Found'})
        with self.assertRaises(ValueError):
            governance.verify('lab', ROOT, fake)
        fake = FakeGitHub()
        fake.responses[f'repos/{REPOSITORY}/rulesets?includes_parents=true'] = RuntimeError('timeout')
        with self.assertRaises(RuntimeError):
            governance.verify('lab', ROOT, fake)
        fake = FakeGitHub()
        fake.responses[f'repos/{REPOSITORY}/environments?per_page=100'] = (200, None)
        with self.assertRaises(ValueError):
            governance.verify('lab', ROOT, fake)

    def test_cli_exit_codes_and_get_only_requests(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with patch.object(governance, 'verify', return_value={'result': 'MATCH'}):
                self.assertEqual(governance.main(['verify']), 0)
            with patch.object(governance, 'verify', return_value={'result': 'DRIFT'}):
                self.assertEqual(governance.main(['verify', '--profile', 'corporate']), 1)
            with patch.object(governance, 'verify', side_effect=RuntimeError('rate limited')):
                self.assertEqual(governance.main(['verify']), 2)
        completed = subprocess.CompletedProcess([], 1, stdout='{"message":"Branch not protected"}',
                                                stderr='gh: Branch not protected (HTTP 404)')
        with patch.object(governance.subprocess, 'run', return_value=completed) as run:
            self.assertEqual(governance.gh_fetch('repos/x/y/branches/develop/protection'),
                             (404, {'message': 'Branch not protected'}))
        self.assertEqual(run.call_args.args[0][:4], ['gh', 'api', '--method', 'GET'])
        failed = subprocess.CompletedProcess([], 1, stdout='', stderr='HTTP 502')
        with patch.object(governance.subprocess, 'run', return_value=failed), \
                self.assertRaises(RuntimeError):
            governance.gh_fetch('repos/x/y/rulesets')

    def test_verifier_never_mutates_the_profile_it_compares(self):
        before = copy.deepcopy(governance.load(ROOT))
        governance.verify('corporate', ROOT, FakeGitHub())
        self.assertEqual(governance.load(ROOT), before)


if __name__ == '__main__':
    unittest.main()
