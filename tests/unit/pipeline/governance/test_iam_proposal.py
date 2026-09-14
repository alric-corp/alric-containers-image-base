"""Offline structure and rendering checks; never evaluate AWS authorization."""
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

from tools import render_iam_proposal as renderer
from tools.check_ai_context import link_targets


ROOT = Path(__file__).resolve().parents[4]
PROPOSAL = ROOT / 'policies/aws/proposals/factory-permissions'
FIXTURE = PROPOSAL / 'parameters.fixture.json'
TOKEN = {'ecr:GetAuthorizationToken'}
READ = {'ecr:BatchGetImage', 'ecr:GetDownloadUrlForLayer',
        'ecr:BatchCheckLayerAvailability', 'ecr:DescribeImages'}
WRITE = {'ecr:InitiateLayerUpload', 'ecr:UploadLayerPart',
         'ecr:CompleteLayerUpload', 'ecr:PutImage'}
PROVISION = {'ecr:DescribeRepositories', 'ecr:CreateRepository',
             'ecr:PutImageTagMutability'}


def fixture():
    return renderer.read_json(FIXTURE)


class ProposalStructureTests(unittest.TestCase):
    def setUp(self):
        self.parameters = fixture()
        self.documents = renderer.render(self.parameters)

    def test_fixture_is_synthetic_and_repositories_render_as_sorted_typed_arrays(self):
        self.assertEqual(self.parameters['AWS_ACCOUNT_ID'], '111122223333')
        self.assertEqual(self.parameters['GITHUB_REPOSITORY'], 'example-org/factory-iam-fixture')
        self.assertEqual(len(self.parameters['ECR_REPOSITORIES']), 2)
        original = deepcopy(self.parameters)
        reversed_repos = dict(self.parameters,
                              ECR_REPOSITORIES=list(reversed(self.parameters['ECR_REPOSITORIES'])))
        self.assertEqual(self.documents, renderer.render(reversed_repos))
        self.assertEqual(self.parameters, original)
        expected = [f'arn:aws:ecr:us-east-1:111122223333:repository/{repo}'
                    for repo in sorted(self.parameters['ECR_REPOSITORIES'])]
        for name in ('execution.identity.json', 'provisioning.identity.json'):
            for statement in self.documents[name]['Statement']:
                if statement['Action'] != ['ecr:GetAuthorizationToken']:
                    self.assertIsInstance(statement['Resource'], list)
                    self.assertEqual(statement['Resource'], expected)
        # JSON serialization preserves the replacement's type and leaves no placeholder.
        serialized = json.dumps(self.documents, sort_keys=True)
        self.assertEqual(json.loads(serialized), self.documents)
        self.assertNotIn('${', serialized)

    def test_identity_actions_are_explicit_and_execution_provisioning_are_disjoint(self):
        expected = {
            'execution.identity.json': {
                'EcrAuthorizationToken': TOKEN,
                'ReadImagesAndEvidence': READ,
                'WriteImagesAndEvidence': WRITE,
            },
            'provisioning.identity.json': {
                'InspectRepositoryConfiguration': {'ecr:DescribeRepositories'},
                'EnsureRepositoryConfiguration': {'ecr:CreateRepository', 'ecr:PutImageTagMutability'},
            },
        }
        phases = {}
        for name, statements in expected.items():
            policy = self.documents[name]
            self.assertEqual(set(policy), {'Version', 'Statement'})
            self.assertEqual(policy['Version'], '2012-10-17')
            actual = policy['Statement']
            self.assertEqual(len(actual), len(statements))
            self.assertEqual({entry['Sid'] for entry in actual}, set(statements))
            phases[name] = set()
            for entry in actual:
                with self.subTest(policy=name, sid=entry['Sid']):
                    self.assertEqual(set(entry), {'Sid', 'Effect', 'Action', 'Resource', 'Condition'})
                    self.assertEqual(entry['Effect'], 'Allow')
                    self.assertIsInstance(entry['Action'], list)
                    self.assertEqual(len(entry['Action']), len(set(entry['Action'])))
                    self.assertEqual(set(entry['Action']), statements[entry['Sid']])
                    self.assertEqual(entry['Condition'], {
                        'StringEquals': {'aws:RequestedRegion': self.parameters['AWS_REGION']}})
                    phases[name].update(entry['Action'])
        execution, provisioning = (phases[name] for name in expected)
        self.assertFalse(execution & provisioning)
        self.assertEqual(execution | provisioning, TOKEN | READ | WRITE | PROVISION)

    def test_only_authorization_token_uses_global_resource(self):
        token_statements = []
        for name in ('execution.identity.json', 'provisioning.identity.json'):
            for statement in self.documents[name]['Statement']:
                resource = statement['Resource']
                if resource == '*':
                    token_statements.append(statement)
                    self.assertEqual(statement['Action'], ['ecr:GetAuthorizationToken'])
                else:
                    for arn in resource:
                        self.assertNotIn('*', arn)
                        self.assertNotIn('?', arn)
                        self.assertRegex(arn, r'^arn:aws:ecr:us-east-1:111122223333:repository/image-base-')
        self.assertEqual(len(token_statements), 1)

    def test_trust_binds_provider_names_ids_main_and_audience_without_extra_conditions(self):
        policy = self.documents['trust.json']
        self.assertEqual(set(policy), {'Version', 'Statement'})
        self.assertEqual(policy['Version'], '2012-10-17')
        self.assertEqual(len(policy['Statement']), 1)
        statement = policy['Statement'][0]
        self.assertEqual(set(statement), {'Sid', 'Effect', 'Principal', 'Action', 'Condition'})
        self.assertEqual(statement['Effect'], 'Allow')
        self.assertEqual(statement['Action'], 'sts:AssumeRoleWithWebIdentity')
        self.assertEqual(statement['Principal'], {
            'Federated': 'arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com'})
        expected = {'aud': 'sts.amazonaws.com', 'sub': self.parameters['GITHUB_SUB'],
                    'repository': self.parameters['GITHUB_REPOSITORY'],
                    'repository_id': self.parameters['GITHUB_REPOSITORY_ID'],
                    'repository_owner_id': self.parameters['GITHUB_OWNER_ID'],
                    'ref': 'refs/heads/main'}
        self.assertEqual(statement['Condition'], {'StringEquals': {
            'token.actions.githubusercontent.com:' + key: value for key, value in expected.items()}})
        # Equality above also rejects StringLike, job_workflow_ref and tag-based claims.
        self.assertNotIn('*', json.dumps(statement))

    def test_parameter_changes_scope_every_repository_and_provider(self):
        parameters = dict(self.parameters, AWS_ACCOUNT_ID='444455556666', AWS_REGION='eu-west-1',
                          ECR_REPOSITORIES=['image-base-python3-14'])
        documents = renderer.render(parameters)
        for name in ('execution.identity.json', 'provisioning.identity.json'):
            for statement in documents[name]['Statement']:
                self.assertEqual(statement['Condition']['StringEquals']['aws:RequestedRegion'],
                                 'eu-west-1')
                if statement['Resource'] != '*':
                    self.assertEqual(statement['Resource'], [
                        'arn:aws:ecr:eu-west-1:444455556666:repository/image-base-python3-14'])
        provider = documents['trust.json']['Statement'][0]['Principal']['Federated']
        self.assertEqual(provider, 'arn:aws:iam::444455556666:oidc-provider/token.actions.githubusercontent.com')


class ParameterValidationTests(unittest.TestCase):
    def test_parameter_keys_are_exact_and_input_must_be_an_object(self):
        parameters = fixture()
        cases = [None, [], 'parameters', dict(parameters, UNKNOWN='value'),
                 dict(parameters, GITHUB_REF='refs/heads/main')]
        cases += [{key: value for key, value in parameters.items() if key != missing}
                  for missing in parameters]
        for invalid in cases:
            with self.subTest(parameters=invalid), self.assertRaises(ValueError):
                renderer.render(invalid)

    def test_invalid_accounts_regions_names_and_ids_are_rejected(self):
        invalid_values = {
            'AWS_ACCOUNT_ID': ['123', '1111222233334', '11112222*333', 111122223333, None],
            'AWS_REGION': ['us-east-*', 'us-east-1/', 'US-EAST-1', 'us-east-1\n',
                           'cn-north-1', 'us-gov-west-1', None],
            'GITHUB_REPOSITORY': ['missing-owner', 'owner/repo/extra', 'owner/*', 'owner/repo?', None],
            'GITHUB_REPOSITORY_ID': ['0', '-1', '0123', '123*', 'abc', 123, None],
            'GITHUB_OWNER_ID': ['0', '-1', '0987', '987?', 'abc', 987, None],
        }
        for field, values in invalid_values.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    renderer.render(dict(fixture(), **{field: value}))

    def test_repository_list_rejects_duplicates_wildcards_and_invalid_names(self):
        for repositories in ([], None, 'image-base-go1-26', ['image-base-go1-26'] * 2,
                             ['image-base-*'], ['image-base-go?'], ['other-go1-26'],
                             ['image-base-Upper'], ['image-base-'], ['image-base--go'],
                             ['image-base-go/name'], ['image-base-go1-26', 7]):
            with self.subTest(repositories=repositories), self.assertRaises(ValueError):
                renderer.render(dict(fixture(), ECR_REPOSITORIES=repositories))

    def test_both_documented_exact_subject_formats_are_preserved(self):
        parameters = fixture()
        for subject in (parameters['GITHUB_SUB'],
                        'repo:example-org/factory-iam-fixture:ref:refs/heads/main'):
            with self.subTest(subject=subject):
                documents = renderer.render(dict(parameters, GITHUB_SUB=subject))
                condition = documents['trust.json']['Statement'][0]['Condition']['StringEquals']
                self.assertEqual(condition['token.actions.githubusercontent.com:sub'], subject)
                self.assertEqual(condition['token.actions.githubusercontent.com:repository_id'],
                                 parameters['GITHUB_REPOSITORY_ID'])

    def test_subject_rejects_other_ids_names_refs_pr_environment_and_wildcards(self):
        parameters = fixture()
        subject = parameters['GITHUB_SUB']
        invalid = [None, '*', subject + '*', subject.replace('main', '*'),
                   subject.replace('main', 'feature'), subject.replace('heads/main', 'tags/v1'),
                   subject.replace('@987654321', '@987654320'),
                   subject.replace('@123456789', '@123456780'),
                   subject.replace('example-org', 'another-org'),
                   subject.replace('factory-iam-fixture', 'another-repo'),
                   'repo:example-org/factory-iam-fixture:pull_request',
                   'repo:example-org/factory-iam-fixture:environment:production']
        for value in invalid:
            with self.subTest(subject=value), self.assertRaises(ValueError):
                renderer.render(dict(parameters, GITHUB_SUB=value))


class InventoryAndDocumentationTests(unittest.TestCase):
    def test_inventory_covers_every_statement_action_and_has_executable_sources(self):
        inventory = renderer.read_json(PROPOSAL / 'inventory.json')
        operations = {op['id']: op for op in inventory['operations']}
        self.assertEqual(len(operations), len(inventory['operations']))
        documents = renderer.render(fixture())
        expected = {(name.removesuffix('.json'), statement['Sid']): statement
                    for name, policy in documents.items() for statement in policy['Statement']}
        self.assertEqual({(s['policy'], s['Sid']) for s in inventory['statements']}, set(expected))
        covered = set()
        for record in inventory['statements']:
            statement = expected[record['policy'], record['Sid']]
            actions = statement['Action']
            self.assertEqual(set(record['actions']), set(actions if isinstance(actions, list) else [actions]))
            self.assertTrue(record['reason'])
            supported = set()
            for op_id in record['operation_ids']:
                operation = operations[op_id]
                self.assertEqual(operation['phase'], record['phase'])
                supported.update(operation['iam_actions'])
                covered.add(op_id)
            self.assertTrue(set(record['actions']) <= supported)
        self.assertEqual(covered, set(operations))
        for operation in operations.values():
            with self.subTest(operation=operation['id']):
                for field in ('workflow', 'job', 'step', 'command', 'aws_apis', 'iam_actions',
                              'resource_scope', 'conditions', 'classification', 'code_sources',
                              'official_sources'):
                    self.assertTrue(operation[field], field)
                self.assertEqual(operation['execution_under_proposal'], 'NOT_RUN')
                for source in operation['code_sources']:
                    path = (ROOT / source['path']).resolve()
                    self.assertTrue(path.is_relative_to(ROOT))
                    self.assertIn(source['contains'], path.read_text())
                for url in operation['official_sources']:
                    self.assertEqual(urlsplit(url).scheme, 'https')
                    self.assertIn(urlsplit(url).netloc, {
                        'docs.aws.amazon.com', 'github.com', 'docs.docker.com', 'cli.github.com'})

    def test_referrers_api_maps_to_batch_get_image_not_an_invented_iam_action(self):
        inventory = renderer.read_json(PROPOSAL / 'inventory.json')
        referrer_operations = [op for op in inventory['operations']
                               if 'ListImageReferrers' in op['aws_apis']]
        self.assertTrue(referrer_operations)
        for operation in referrer_operations:
            self.assertIn('ecr:BatchGetImage', operation['iam_actions'])
        for operation in inventory['operations']:
            self.assertNotIn('ecr:ListImageReferrers', operation['iam_actions'])

    def test_full_catalog_can_be_rendered_with_exact_arns_and_reviewable_policy_sizes(self):
        repositories = sorted('image-base-' + p.stem for p in (ROOT / 'frameworks').glob('*.yaml'))
        documents = renderer.render(dict(fixture(), ECR_REPOSITORIES=repositories))
        for name, policy in documents.items():
            # Size limits are structural checks, not AWS validation or existence checks.
            compact = json.dumps(policy, separators=(',', ':'))
            self.assertLessEqual(len(compact), 2048 if name == 'trust.json' else 6144)
            for statement in policy['Statement']:
                resource = statement.get('Resource')
                if isinstance(resource, list):
                    self.assertEqual([arn.split(':repository/', 1)[1] for arn in resource], repositories)

    def test_proposals_are_not_loaded_as_permissions_by_active_workflows_or_pipeline(self):
        for directory in (ROOT / '.github/workflows', ROOT / 'scripts/pipeline'):
            for path in directory.rglob('*'):
                if path.suffix not in ('.py', '.yml', '.yaml'):
                    continue
                with self.subTest(path=path.relative_to(ROOT)):
                    text = path.read_text()
                    self.assertNotIn('proposals/factory-permissions', text)
                    self.assertNotIn('render_iam_proposal', text)

    def test_document_links_and_local_command_syntax(self):
        contract = ROOT / 'docs/iam-permission-contract.md'
        documents = [contract, PROPOSAL / 'README.md', ROOT / 'policies/README.md',
                     ROOT / 'README.md', ROOT / 'docs/README.md',
                     ROOT / 'RFC-013-Image-Base-Completa-com-Mermaid.md']
        documents += list((ROOT / 'specs/2026-09-13-iam-permission-contract').glob('*.md'))
        for document in documents:
            for target in link_targets(document.read_text()):
                parsed = urlsplit(target)
                if parsed.scheme in ('http', 'https', 'mailto') or not parsed.path:
                    continue
                with self.subTest(document=document.relative_to(ROOT), target=target):
                    self.assertFalse(parsed.scheme or parsed.netloc)
                    destination = (document.parent / unquote(parsed.path)).resolve()
                    self.assertTrue(destination.is_relative_to(ROOT))
                    self.assertTrue(destination.exists())
        bash = '\n'.join(re.findall(r'(?ms)^```bash\n(.*?)^```$', contract.read_text()))
        self.assertTrue(bash)
        result = subprocess.run(['bash', '-n'], input=bash, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        for relative in ('tools/render_iam_proposal.py',
                         'policies/aws/proposals/factory-permissions/parameters.fixture.json'):
            self.assertIn(relative, bash)
            self.assertTrue((ROOT / relative).is_file())


class TemplateValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        for name in renderer.TEMPLATES:
            shutil.copyfile(PROPOSAL / (name + '.template.json'),
                            self.directory / (name + '.template.json'))

    def test_unknown_embedded_and_malformed_placeholders_are_rejected(self):
        path = self.directory / 'execution.identity.template.json'
        original = renderer.read_json(path)
        for placeholder in ('${UNDOCUMENTED}', 'arn:aws:ecr:${AWS_REGION}',
                            '${AWS_REGION}-suffix', '${aws_region}', '${AWS_REGION'):
            with self.subTest(placeholder=placeholder):
                document = deepcopy(original)
                document['Statement'][1]['Resource'] = placeholder
                path.write_text(json.dumps(document))
                with self.assertRaises(ValueError):
                    renderer.render(fixture(), self.directory)

    def test_duplicate_json_keys_in_templates_are_rejected(self):
        path = self.directory / 'trust.template.json'
        path.write_text('{"Statement": [{"Effect": "Deny", "Effect": "Allow"}]}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key: Effect'):
            renderer.render(fixture(), self.directory)

    def test_malformed_json_is_rejected(self):
        (self.directory / 'trust.template.json').write_text('{"Statement": [}')
        with self.assertRaises(ValueError):
            renderer.render(fixture(), self.directory)


class RendererCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.checkout = self.directory / 'checkout'
        self.script = self.checkout / 'tools/render_iam_proposal.py'
        self.script.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / 'tools/render_iam_proposal.py', self.script)
        self.proposal = self.checkout / 'policies/aws/proposals/factory-permissions'
        self.proposal.mkdir(parents=True)
        for name in renderer.TEMPLATES:
            shutil.copyfile(PROPOSAL / (name + '.template.json'),
                            self.proposal / (name + '.template.json'))
        self.parameters = self.directory / 'parameters.json'
        shutil.copyfile(FIXTURE, self.parameters)

    def invoke(self, output):
        return subprocess.run([sys.executable, '-B', str(self.script),
                               '--parameters', str(self.parameters), '--output', str(output)],
                              cwd=self.directory, capture_output=True, text=True, timeout=10)

    def test_cli_writes_only_the_three_local_documents_outside_checkout(self):
        output = self.directory / 'rendered'
        result = self.invoke(output)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = renderer.render(fixture())
        self.assertEqual({path.name for path in output.iterdir()}, set(expected))
        for name, document in expected.items():
            self.assertEqual((output / name).read_text(), json.dumps(document, indent=2) + '\n')

    def test_cli_rejects_output_inside_checkout_even_through_a_symlink(self):
        alias = self.directory / 'alias'
        alias.symlink_to(self.checkout, target_is_directory=True)
        for output in (self.checkout, self.checkout / 'rendered', alias / 'rendered'):
            with self.subTest(output=output):
                result = self.invoke(output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('outside the repository', result.stderr)
        self.assertFalse((self.checkout / 'rendered').exists())

    def test_cli_never_overwrites_existing_directory_or_file(self):
        for kind in ('directory', 'file'):
            with self.subTest(kind=kind):
                output = self.directory / kind
                if kind == 'directory':
                    output.mkdir()
                    sentinel = output / 'execution.identity.json'
                else:
                    sentinel = output
                sentinel.write_bytes(b'original review document\n')
                result = self.invoke(output)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sentinel.read_bytes(), b'original review document\n')
                if kind == 'directory':
                    self.assertEqual(list(output.iterdir()), [sentinel])

    def test_cli_rejects_duplicate_parameter_keys_before_creating_output(self):
        content = self.parameters.read_text().replace(
            '{', '{"AWS_ACCOUNT_ID": "444455556666",', 1)
        self.parameters.write_text(content)
        output = self.directory / 'rendered'
        result = self.invoke(output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('duplicate JSON key', result.stderr)
        self.assertFalse(output.exists())

    def test_cli_invalid_template_leaves_no_partial_output_directory(self):
        path = self.proposal / 'trust.template.json'
        path.write_text('{"Statement": "${UNKNOWN}"}')
        output = self.directory / 'rendered'
        result = self.invoke(output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
