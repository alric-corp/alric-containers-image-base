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
``python3_test_environment`` makes ``python3`` resolve to the real
interpreter for such a script's subprocess, without touching the script
itself, for exactly the duration of a ``with`` block.

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
import contextlib
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


def _write_python3_shim(directory):
    """Write a working 'python3' into `directory`, for both invocation
    styles seen in this suite: from bash (a plain POSIX shell script,
    run via its shebang like any other script on PATH) and from a plain
    native subprocess with no shell involved (a copy of this interpreter
    named 'python3.exe' -- a real launcher is the only thing Windows'
    CreateProcess can run by a bare name; unlike the 'aws' case in
    windows_native_stub, no argv-intercepting hook is needed here, since
    every caller invokes it as '-B -m some.module ...', which is exactly
    the CLI shape this interpreter already knows how to run itself).
    Both forward argv, stdio and exit status untouched. Always written
    fresh against the *current* sys.executable -- see
    python3_test_environment for why this must never be a stale, reused
    copy from an earlier process.
    """
    directory = Path(directory)
    shim = directory / 'python3'
    shim.write_text('#!/bin/sh\nexec "%s" "$@"\n' % sys.executable.replace('\\', '/'))
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    if os.name == 'nt':
        shutil.copy2(sys.executable, directory / 'python3.exe')


# Reentrancy bookkeeping for python3_test_environment: nested `with` blocks
# share the outermost one's shim directory and PATH entry instead of each
# creating (and PATH-prepending) their own. Not thread-safe -- this suite
# runs unittest sequentially in one process/thread, never concurrently.
_shim_state = {'depth': 0, 'tmpdir': None, 'saved_path': None}


@contextlib.contextmanager
def python3_test_environment(env):
    """Context manager yielding a copy of `env` with a working 'python3'
    on PATH, for exactly the duration of the `with` block.

    No-op on Linux/macOS -- yields `env` unchanged and touches nothing --
    where 'python3' already resolves normally; the workflow scripts under
    test keep calling 'python3' exactly as they do on the GitHub Actions
    runner, only its resolution changes, and only on Windows.

    On Windows, the shim lives in a fresh TemporaryDirectory scoped to
    this context -- never a cached, reused directory -- so there is no
    risk of running a copy of an interpreter that no longer matches
    sys.executable (e.g. after a Python upgrade between test runs). The
    directory is removed, and this process' own os.environ['PATH'] is
    restored to its exact prior value, in a `finally` on exit -- even if
    the `with` block raises. PATH must be restored on the real
    os.environ, not just the returned copy, because a plain
    ``subprocess.run(['python3', ...], env=...)`` with no shell involved
    resolves the bare name via Windows' CreateProcess, which -- unlike a
    shell -- searches using the *calling* process' real environment, not
    the `env=` argument being handed to the child.

    Reentrant: a nested ``with python3_test_environment(...)`` inside
    another reuses the same shim directory and does not add a second
    PATH entry; only the outermost exit restores PATH and removes the
    directory.
    """
    if os.name != 'nt':
        yield env
        return
    is_outermost = _shim_state['depth'] == 0
    if is_outermost:
        tmpdir = tempfile.TemporaryDirectory(prefix='alric-python3-shim-')
        _write_python3_shim(tmpdir.name)
        _shim_state['tmpdir'] = tmpdir
        _shim_state['saved_path'] = os.environ.get('PATH', '')
        os.environ['PATH'] = tmpdir.name + os.pathsep + _shim_state['saved_path']
    _shim_state['depth'] += 1
    try:
        shim_dir = _shim_state['tmpdir'].name
        shimmed = dict(env)
        shimmed['PATH'] = shim_dir + os.pathsep + shimmed.get('PATH', '')
        yield shimmed
    finally:
        _shim_state['depth'] -= 1
        if _shim_state['depth'] == 0:
            os.environ['PATH'] = _shim_state['saved_path']
            _shim_state['tmpdir'].cleanup()
            _shim_state['tmpdir'] = None
            _shim_state['saved_path'] = None


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

    Implicit dependency: the copied interpreter still needs its native
    runtime DLL (e.g. python313.dll) to start, which Windows locates via
    the normal DLL search order -- including PATH. PYTHONHOME only tells
    it where the *standard library* lives, not the DLL. This works today
    because callers build their env from ``{**os.environ, 'PATH': ...}``,
    which keeps the original interpreter's directory on PATH; an env
    that dropped it would fail to launch the copy at all.
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
