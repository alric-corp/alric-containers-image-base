"""Cross-platform subprocess helpers for tests that shell out to bash.

Windows note: ``subprocess.run(['bash', ...])`` resolves the bare name
through Windows' CreateProcess search order (application directory,
current directory, System32, the Windows directory, then PATH) rather
than a shell-style left-to-right PATH scan. Many Windows machines have
``C:\\Windows\\System32\\bash.exe`` -- the WSL launcher -- which wins
that search even when Git Bash is correctly on PATH, and fails outright
if no WSL distro is installed. ``bash_executable`` walks PATH itself and
validates each candidate is actually Git Bash/MSYS2 before using it.

Some of the same scripts also call ``python3``, exactly as the GitHub
Actions runner does. A stock python.org install on Windows only provides
``python.exe`` -- the ``python3`` name on PATH is normally the
WindowsApps execution-alias stub, which fails unless configured.
``with_python3_shim`` makes ``python3`` resolve to the real interpreter
for such a script's subprocess, without touching the script itself.

A third case needs more than PATH resolution: a test that runs a product
script directly (``[sys.executable, '-m', ...]``, no bash involved)
where that script itself does ``subprocess.run(['some-cli', ...])`` with
a fake ``some-cli`` on PATH. On POSIX this fake is a ``#!/bin/sh``
script and the kernel execs it directly -- no shell needed. Windows has
no such fallback: without a shell in the picture, a bare name only ever
resolves to a real ``.exe``, so a shebang script is simply not
launchable there. ``windows_native_stub`` builds a real one (a copy of
this interpreter plus a ``sitecustomize`` hook) for that one case.

None of this changes behaviour on Linux/macOS: ``bash`` and ``python3``
already resolve normally there, and ``windows_native_stub`` is a no-op.
"""
import functools
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

_BASH_MARKERS = ('MINGW', 'MSYS', 'CYGWIN')


def _bash_name():
    return 'bash.exe' if os.name == 'nt' else 'bash'


def _path_candidates():
    """Executables named bash found by walking PATH directly, in PATH
    order. Deliberately not shutil.which()/CreateProcess: both apply
    OS-specific search rules that can prefer a non-functional launcher
    over one earlier in PATH (see module docstring)."""
    name = _bash_name()
    seen = set()
    for directory in os.environ.get('PATH', '').split(os.pathsep):
        if not directory:
            continue
        candidate = os.path.join(directory, name)
        if candidate not in seen and os.path.isfile(candidate):
            seen.add(candidate)
            yield candidate


def _is_usable_bash(path):
    """True if `path` runs and is Git Bash/MSYS2 (or, off Windows, any
    working bash). Rejects a working-but-wrong shell -- e.g. the WSL
    launcher, which happily reports success while being a different
    OS environment that doesn't share Windows temp paths or env vars
    the way the tests' fake executables and PATH overrides expect."""
    try:
        result = subprocess.run([path, '-c', 'uname -s'], capture_output=True, text=True, timeout=10)
    except OSError:
        return False
    if result.returncode != 0:
        return False
    if os.name == 'nt':
        return any(marker in result.stdout for marker in _BASH_MARKERS)
    return True


@functools.lru_cache(maxsize=1)
def bash_executable():
    """Absolute path to a working, Git Bash/MSYS2-compatible bash.

    Raises RuntimeError with an actionable message if none is found.
    Tests should let that propagate rather than skip: a missing bash is
    an environment problem to fix, not a platform to avoid.
    """
    for candidate in _path_candidates():
        if _is_usable_bash(candidate):
            return candidate
    raise RuntimeError(
        "No working Git Bash/MSYS2 'bash' found on PATH. On Windows this "
        "usually means Git for Windows is not installed, or PATH only "
        "exposes the WSL launcher (C:\\Windows\\System32\\bash.exe) "
        "instead. Install Git for Windows and ensure its usr/bin is on PATH.")


def bash_command(*args):
    """['bash', *args], with 'bash' replaced by a validated absolute path."""
    return [bash_executable(), *args]


@functools.lru_cache(maxsize=1)
def _python3_shim_dir():
    """Directory holding a working 'python3' for both invocation styles
    seen in this suite: from bash (a plain POSIX shell script, run via
    its shebang like any other script on PATH) and from a plain native
    subprocess with no shell involved (a copy of this interpreter named
    'python3.exe' -- a real launcher is the only thing Windows'
    CreateProcess can run by a bare name; unlike the 'aws' case in
    windows_native_stub, no argv-intercepting hook is needed here, since
    every caller invokes it as '-B -m some.module ...', which is exactly
    the CLI shape this interpreter already knows how to run itself).
    Both forward argv, stdio and exit status untouched.
    """
    directory = Path(tempfile.gettempdir()) / 'alric-test-harness-shims'
    directory.mkdir(parents=True, exist_ok=True)
    shim = directory / 'python3'
    content = '#!/bin/sh\nexec "%s" "$@"\n' % sys.executable.replace('\\', '/')
    if not shim.is_file() or shim.read_text() != content:
        shim.write_text(content)
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    if os.name == 'nt':
        native = directory / 'python3.exe'
        if not native.is_file():
            shutil.copy2(sys.executable, native)
    return str(directory)


def with_python3_shim(env):
    """Copy of env with a working 'python3' available on PATH.

    No-op on Linux/macOS, where 'python3' already resolves normally --
    the workflow scripts under test keep calling 'python3' exactly as
    they do on the GitHub Actions runner; only its resolution changes.

    Also prepends the shim to this process' own PATH (os.environ), not
    just the returned copy: a plain ``subprocess.run(['python3', ...],
    env=...)`` with no shell involved resolves the bare name via
    Windows' CreateProcess, which -- unlike a shell -- searches using
    the *calling* process' real environment, not the `env=` argument
    being handed to the child. Without this, callers using ``env=``
    only would still resolve to the broken WindowsApps alias.
    """
    if os.name != 'nt':
        return env
    shim_dir = _python3_shim_dir()
    if shim_dir not in os.environ.get('PATH', ''):
        os.environ['PATH'] = shim_dir + os.pathsep + os.environ.get('PATH', '')
    env = dict(env)
    env['PATH'] = shim_dir + os.pathsep + env.get('PATH', '')
    return env


def windows_native_stub(bin_dir, name, *, stdout_env):
    """Make a POSIX '#!/bin/sh' fake executable also runnable natively
    on Windows, for tests that reach it through a plain (non-bash)
    subprocess -- e.g. product code calling subprocess.run(['aws', ...])
    directly, the same way it does on the GitHub Actions runner.

    The caller must still write the ordinary POSIX stub at
    ``bin_dir/name`` (used as-is on Linux/macOS, and by any bash in the
    same test). This adds a real ``name.exe`` on Windows only: a copy of
    the running interpreter plus a sitecustomize.py hook that, keyed off
    that copy's own sys.executable path (not argv, which by the time
    the hook runs already holds the *faked* command's arguments, not
    the interpreter's), writes os.environ[stdout_env] to stdout and
    exits 0 before CPython would otherwise treat the fake command's
    first argument as a script path to open.

    Returns environment overrides the caller must merge into the
    subprocess env for the stub to work (empty dict off Windows).
    """
    if os.name != 'nt':
        return {}
    bin_dir = Path(bin_dir)
    shutil.copy2(sys.executable, bin_dir / (name + '.exe'))
    hook_dir = bin_dir / '_native_stub_site'
    hook_dir.mkdir(exist_ok=True)
    (hook_dir / 'sitecustomize.py').write_text(
        "import os, sys\n"
        "if os.path.basename(sys.executable).lower() == %r:\n"
        "    sys.stdout.write(os.environ.get(%r, '') + '\\n')\n"
        "    sys.stdout.flush()\n"
        "    os._exit(0)\n" % (name.lower() + '.exe', stdout_env))
    return {'PYTHONHOME': os.path.dirname(sys.executable),
            'PYTHONPATH': str(hook_dir) + os.pathsep + os.environ.get('PYTHONPATH', '')}
