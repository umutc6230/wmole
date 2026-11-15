"""Run the suite against a throwaway home directory.

mole.py resolves ~/.wmole at import time, and several tests (plus the `serve`
subprocesses they spawn) log deletions of made-up paths. Against the real home
that filled the user's operations.log with fake entries, which the dashboard
then reported as tens of GB "freed".
"""

import os
import tempfile

_home = tempfile.mkdtemp(prefix="wmole-test-home-")
os.environ["USERPROFILE"] = _home
os.environ["HOME"] = _home
