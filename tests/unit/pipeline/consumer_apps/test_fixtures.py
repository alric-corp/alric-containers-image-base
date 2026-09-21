"""Offline regression checks for the downstream app fixtures' build boundaries."""
import ast
import errno
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / 'tests' / 'consumer-apps'
FAMILIES = ('go', 'java', 'dotnet', 'node', 'python')


def python_app():
    spec = importlib.util.spec_from_file_location('consumer_python_fixture', FIXTURES / 'python' / 'app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConsumerFixtureTests(unittest.TestCase):
    def test_final_stage_always_uses_runtime_and_preserves_base_user(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                lines = (FIXTURES / family / 'Dockerfile').read_text().splitlines()
                stages = [line for line in lines if line.startswith('FROM ')]
                self.assertEqual(stages[-1], 'FROM ${RUNTIME_IMAGE}')
                self.assertFalse(any(line.startswith('USER ') for line in lines))
                self.assertFalse(any(line.startswith('ADD ') for line in lines))
                final = lines[lines.index(stages[-1]):]
                self.assertFalse(any(line.startswith('RUN ') for line in final))
                self.assertIn('EXPOSE 8080', final)

    def test_compiled_and_node_build_from_dev_then_copy_application_only(self):
        for family in ('go', 'java', 'dotnet', 'node'):
            with self.subTest(family=family):
                text = (FIXTURES / family / 'Dockerfile').read_text()
                self.assertIn('FROM ${BUILD_IMAGE} AS build', text)
                final = text.split('FROM ${RUNTIME_IMAGE}', 1)[1]
                self.assertIn('COPY --from=build --chown=10000:10000 ', final)
                self.assertNotIn('/usr/bin', final.split('ENTRYPOINT', 1)[0])

    def test_python_has_no_build_companion_or_package_download(self):
        text = (FIXTURES / 'python' / 'Dockerfile').read_text()
        self.assertNotIn('BUILD_IMAGE', text)
        self.assertNotIn('RUN ', text)
        tree = ast.parse((FIXTURES / 'python' / 'app.py').read_text())
        imported = {node.module.split('.')[0] for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)}
        imported.update(alias.name.split('.')[0] for node in ast.walk(tree)
                        if isinstance(node, ast.Import) for alias in node.names)
        self.assertLessEqual(imported, {'errno', 'json', 'os', 'platform', 'signal', 'tempfile',
                                       'threading', 'http', 'pathlib', 'urllib'})

    def test_go_module_cannot_require_external_dependencies(self):
        module = (FIXTURES / 'go' / 'go.mod').read_text()
        self.assertNotIn('require', module)
        self.assertNotIn('replace', module)
        self.assertIn('GOPROXY=off', (FIXTURES / 'go' / 'Dockerfile').read_text())

    def test_dotnet_is_real_aspnet_without_external_nuget_sources(self):
        project = ET.fromstring((FIXTURES / 'dotnet' / 'App.csproj').read_text())
        self.assertEqual(project.attrib['Sdk'], 'Microsoft.NET.Sdk.Web')
        self.assertEqual(project.findall('.//PackageReference'), [])
        config = ET.fromstring((FIXTURES / 'dotnet' / 'NuGet.config').read_text())
        self.assertEqual([node.tag for node in config.find('packageSources')], ['clear'])

    def test_node_lock_is_dependency_free_and_npm_prepares_final_application(self):
        package = json.loads((FIXTURES / 'node' / 'package.json').read_text())
        lock = json.loads((FIXTURES / 'node' / 'package-lock.json').read_text())
        self.assertNotIn('dependencies', package)
        self.assertNotIn('devDependencies', package)
        self.assertEqual(set(lock['packages']), {''})
        self.assertEqual(lock['packages']['']['version'], package['version'])
        self.assertEqual(lock['packages']['']['name'], package['name'])
        dockerfile = (FIXTURES / 'node' / 'Dockerfile').read_text()
        self.assertIn('npm ci --offline --ignore-scripts --no-audit --no-fund', dockerfile)
        self.assertIn('npm run build --offline', dockerfile)

    @unittest.skipUnless(shutil.which('node'), 'Node is optional for local fixture syntax validation')
    def test_node_preparation_emits_a_syntax_valid_application(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            for filename in ('build.cjs', 'server.cjs'):
                shutil.copyfile(FIXTURES / 'node' / filename, work / filename)
            subprocess.run(['node', 'build.cjs'], cwd=work, check=True, capture_output=True)
            subprocess.run(['node', '--check', 'dist/server.cjs'], cwd=work,
                           check=True, capture_output=True)
            self.assertIn((work / 'server.cjs').read_text(), (work / 'dist/server.cjs').read_text())

    def test_python_probe_rejects_permission_denial_as_read_only_proof(self):
        app = python_app()
        proc = 'Uid:\t10000\t10000\t10000\t10000\nGid:\t10000\t10000\t10000\t10000\nCapEff:\t0000000000000000\nNoNewPrivs:\t1\n'
        with patch.object(app.Path, 'read_text', return_value=proc), \
             patch.object(app.Path, 'write_text', side_effect=PermissionError(errno.EACCES, 'denied')), \
             patch.object(app, 'writable', return_value=True):
            self.assertFalse(app.security()['read_only_root'])

    def test_python_probe_requires_kernel_erofs(self):
        app = python_app()
        proc = 'CapEff:\t0000000000000000\nNoNewPrivs:\t1\n'
        with patch.object(app.Path, 'read_text', return_value=proc), \
             patch.object(app.Path, 'write_text', side_effect=OSError(errno.EROFS, 'read-only')), \
             patch.object(app, 'writable', return_value=True):
            result = app.security()
        self.assertTrue(result['read_only_root'])
        self.assertTrue(result['no_new_privileges'])
        self.assertEqual(result['cap_eff'], '0000000000000000')

    def test_python_writable_probe_writes_reads_and_removes_temporary_file(self):
        app = python_app()
        with tempfile.TemporaryDirectory() as temporary:
            self.assertTrue(app.writable(temporary))
            self.assertEqual(list(Path(temporary).iterdir()), [])
            self.assertFalse(app.writable(str(Path(temporary) / 'absent')))


if __name__ == '__main__':
    unittest.main()
