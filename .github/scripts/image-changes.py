"""Conservative image-build decision; unknown paths or missing history build."""
import os
from pathlib import PurePosixPath
import subprocess


def documentation_only(path):
    return (path in {'README.md', 'LICENSE', 'fex/README.md', 'fex/RESULTS.md',
                     'ops/diagnostics/README.md'} or
            (path.startswith('docs/') and PurePosixPath(path).suffix == '.md'))


def needs_image(event, base, head):
    if event not in {'push', 'pull_request'} or not base or not head or set(base) == {'0'}:
        return True
    try:
        # No rename folding: deleting an image input and moving it into docs must build.
        result = subprocess.run(
            ['git', 'diff', '--no-renames', '--name-only', '-z', base, head, '--'],
            check=True, capture_output=True, timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return True
    paths = result.stdout.decode('utf-8', errors='surrogateescape').split('\0')
    return any(not documentation_only(path) for path in paths if path)


if __name__ == '__main__':
    decision = needs_image(os.environ['CHANGE_EVENT'], os.environ.get('CHANGE_BASE'),
                           os.environ.get('CHANGE_HEAD'))
    print(f'Image build required: {decision}')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write(f'image={str(decision).lower()}\n')
