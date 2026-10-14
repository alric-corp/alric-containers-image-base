"""Regression tests for the subprocess portability helpers themselves --
in particular that python3_test_environment restores everything it
touches, even across nested use and exceptions."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import subprocess_env
from tests.helpers.subprocess_env import bash_command, python3_test_environment


class Python3TestEnvironmentTests(unittest.TestCase):
    def test_environment_restored_after_context(self):
        before = os.environ.get('PATH')
        with python3_test_environment(dict(os.environ)):
            pass
        self.assertEqual(os.environ.get('PATH'), before)

    def test_environment_restored_after_exception(self):
        before = os.environ.get('PATH')
        with self.assertRaises(ValueError):
            with python3_test_environment(dict(os.environ)):
                raise ValueError('boom')
        self.assertEqual(os.environ.get('PATH'), before)

    def test_nested_contexts_reuse_the_shim_and_restore_correctly(self):
        original = os.environ.get('PATH')
        with python3_test_environment(dict(os.environ)):
            after_outer = os.environ.get('PATH')
            with python3_test_environment(dict(os.environ)):
                # The inner context must not add a second PATH entry.
                self.assertEqual(os.environ.get('PATH'), after_outer)
            # Leaving the inner context must not disturb the outer one.
            self.assertEqual(os.environ.get('PATH'), after_outer)
        self.assertEqual(os.environ.get('PATH'), original)

    def test_shim_directory_is_removed_after_the_outermost_context_exits(self):
        with python3_test_environment(dict(os.environ)):
            shim_dir = subprocess_env._shim_state['tmpdir'].name
            self.assertTrue(os.path.isdir(shim_dir))
        self.assertFalse(os.path.exists(shim_dir))

    def test_python3_is_this_interpreter_even_with_another_python3_first_on_path(self):
        # Reproduces a developer PATH whose first python3 is not the test interpreter.
        with tempfile.TemporaryDirectory() as foreign:
            stub = Path(foreign) / 'python3'
            stub.write_text('#!/bin/sh\nexit 3\n')
            stub.chmod(0o755)
            before = os.environ.get('PATH')
            env = dict(os.environ, PATH=foreign + os.pathsep + os.environ.get('PATH', ''))
            with python3_test_environment(env) as shimmed:
                if os.name != 'nt':
                    self.assertEqual(os.environ.get('PATH'), before)
                result = subprocess.run(['python3', '-c', 'import sys; print(sys.prefix)'],
                                        env=shimmed, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            if os.name != 'nt':  # The Windows shim is a relocated copy of the interpreter.
                self.assertEqual(result.stdout.strip(), sys.prefix)
            self.assertEqual(os.environ.get('PATH'), before)

    def test_python3_argv_stdout_stderr_and_exit_code_are_preserved(self):
        with python3_test_environment(dict(os.environ)) as env:
            result = subprocess.run(
                ['python3', '-c',
                 'import sys; sys.stdout.write("out:" + sys.argv[1]); '
                 'sys.stderr.write("err:" + sys.argv[2]); sys.exit(5)',
                 'hello', 'world two'],
                env=env, capture_output=True, text=True)
        self.assertEqual(result.stdout, 'out:hello')
        self.assertEqual(result.stderr, 'err:world two')
        self.assertEqual(result.returncode, 5)

    def test_python3_via_bash_argv_stdout_stderr_and_exit_code_are_preserved(self):
        code = ('import sys; sys.stdout.write("out:" + sys.argv[1]); '
                'sys.stderr.write("err:" + sys.argv[2])')
        with python3_test_environment(dict(os.environ)) as env:
            result = subprocess.run(
                # 'bash0' fills bash -c's own $0 slot so $1.. line up with
                # the values that follow it (code, then the two argv words).
                bash_command('-c', 'python3 -c "$1" "$2" "$3"; exit "$4"',
                             'bash0', code, 'hello', 'world two', '7'),
                env=env, capture_output=True, text=True)
        self.assertEqual(result.stdout, 'out:hello')
        self.assertEqual(result.stderr, 'err:world two')
        self.assertEqual(result.returncode, 7)


if __name__ == '__main__':
    unittest.main()
