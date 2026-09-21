import ast
from fnmatch import fnmatchcase
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[4]
PIPELINE_DOMAINS = {'artifacts', 'catalog', 'consumer_apps', 'governance', 'operations', 'release', 'runtime'}
LEGACY_ADAPTERS = {'runtime_images.py', 'validate_inputs.py', 'oci_artifact.py',
                   'scan_images.py', 'tool_versions.py', 'report_unfixed_cves.py'}
DEPENDENCIES = {
    'artifacts': {'governance'}, 'catalog': set(), 'governance': set(),
    'runtime': {'artifacts'}, 'release': {'artifacts'},
    'operations': {'governance', 'runtime'},
    'consumer_apps': set(),
}
# Promotion reuses the canonical pair model and input validation without
# opening release to every implementation module in those domains.
MODULE_DEPENDENCIES = {
    'release': {'scripts.pipeline.runtime.runtime_images',
                'scripts.pipeline.catalog.validate_inputs'},
    # Consumers reuse identity/metadata validation and architecture reporting,
    # never the internal runtime executor or release mutation mechanisms.
    'consumer_apps': {'scripts.pipeline.artifacts.oci_artifact',
                      'scripts.pipeline.release.verify_publication',
                      'scripts.pipeline.runtime',
                      'scripts.pipeline.runtime.runtime_images'},
}


class RepositoryLayoutTests(unittest.TestCase):
    def test_all_regression_tests_are_discoverable_in_their_layer(self):
        for path in (ROOT / 'tests').rglob('test_*.py'):
            self.assertIn(path.relative_to(ROOT / 'tests').parts[0], {'unit', 'integration'}, path)
            for parent in path.parents:
                if parent == ROOT:
                    break
                self.assertTrue((parent / '__init__.py').is_file(), parent)

    def test_pipeline_domains_are_explicit_packages(self):
        pipeline = ROOT / 'scripts/pipeline'
        actual = {path.name for path in pipeline.iterdir()
                  if path.is_dir() and path.name != '__pycache__'}
        self.assertEqual(actual, PIPELINE_DOMAINS)
        for domain in PIPELINE_DOMAINS:
            self.assertTrue((pipeline / domain / '__init__.py').is_file())

    def test_legacy_workflow_directory_contains_only_adapters(self):
        legacy = ROOT / '.github/scripts'
        actual = {path.name for path in legacy.glob('*.py')}
        self.assertEqual(actual, LEGACY_ADAPTERS)
        for adapter in actual:
            self.assertIn('scripts.pipeline.', (legacy / adapter).read_text())
            tree = ast.parse((legacy / adapter).read_text())
            self.assertFalse(any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                                 for node in ast.walk(tree)), adapter)

    def test_dependencies_follow_domain_boundaries(self):
        pipeline = ROOT / 'scripts/pipeline'
        module_names = {path.stem for path in pipeline.rglob('*.py')}
        for path in pipeline.rglob('*.py'):
            if path.parent == pipeline:
                continue
            domain = path.parent.name
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertEqual(node.level, 0, path)
                    names = [node.module or '']
                elif isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                else:
                    continue
                for name in names:
                    self.assertNotEqual(name.split('.')[0], 'tests', path)
                    self.assertNotIn(name, module_names, f'{path}: use qualified imports')
                    if name.startswith('scripts.pipeline.'):
                        target = name.split('.')[2]
                        self.assertTrue(target in DEPENDENCIES[domain] | {domain}
                                        or name in MODULE_DEPENDENCIES.get(domain, set()),
                                        f'{path}: undeclared dependency {name}')

    def test_image_pipeline_triggers_cover_migrated_sources(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/workflow.yml').read_text())
        events = workflow.get('on', workflow.get(True))
        sources = [path for directory in ('scripts', 'policies', 'frameworks', 'distroless', 'melange',
                                          'tests/runtime', '.github/scripts')
                   for path in (ROOT / directory).rglob('*')
                   if path.is_file() and path.suffix in ('.py', '.sh', '.yaml', '.cjs',
                                                         '.sha256', '.pub', '.txt', '.json', '.go', '.cs', '.java')]
        for event in ('push', 'pull_request'):
            for path in sources:
                relative = path.relative_to(ROOT).as_posix()
                self.assertTrue(any(fnmatchcase(relative, pattern)
                                    for pattern in events[event]['paths']), (event, relative))

    def test_product_workflows_do_not_execute_legacy_script_paths(self):
        workflows = ROOT / '.github/workflows'
        for path in workflows.glob('*.yml'):
            document = yaml.safe_load(path.read_text())
            for job in (document.get('jobs') or {}).values():
                for step in job.get('steps') or []:
                    self.assertNotIn('.github/scripts/', step.get('run') or '', path.name)


if __name__ == '__main__':
    unittest.main()
