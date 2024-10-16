import os
import subprocess
import sys

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def test_help():
    # A quick check that the package can be executed as a module which
    # takes arguments, using e.g. "python3 -m west --version" to
    # produce the same results as "west --version", and that both are
    # sane (i.e. the actual version number is printed instead of
    # simply an error message to stderr).

    subprocess.check_output([sys.executable, "-m", "infuse_iot", "--help"])
    subprocess.check_output(["infuse", "--help"])
