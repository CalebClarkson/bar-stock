import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="osb-test-")
os.environ["OSB_DATA_DIR"] = _tmp
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
