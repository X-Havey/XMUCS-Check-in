"""Check source/bundle parity, tests, and isolated portable startup."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "portable"


def main():
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    for relative, digest in manifest["sha256"].items():
        path = (BUNDLE / relative).resolve()
        if BUNDLE not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError("Bundle integrity check failed: " + relative)
    for path in (ROOT / "xmu-rollcall-cli/xmu_rollcall").glob("*.py"):
        if path.read_text(encoding="utf-8") != (BUNDLE / "lib/xmu_rollcall" / path.name).read_text(encoding="utf-8"):
            raise RuntimeError("Source and portable package differ: " + path.name)
    with tempfile.TemporaryDirectory(prefix="xmucs-check-") as temporary:
        work = Path(temporary)
        config = work / "config"
        config.mkdir()
        account = config / "config.json"
        account.write_text(json.dumps({"accounts": [{"id": 1, "name": "Test", "username": "fixture", "password": "fixture"}], "current_account_id": 1}), encoding="utf-8")
        cookie = config / "1.json"
        cookie.write_text('{"fixture": "preserve"}', encoding="utf-8")
        locations = config / "radar_locations.json"
        locations.write_text('{"device_id": "fixture-device"}', encoding="utf-8")
        before = {p.name: p.read_bytes() for p in (account, cookie)}
        env = os.environ.copy()
        env.update({"PYTHONDONTWRITEBYTECODE": "1", "XMU_ROLLCALL_CONFIG_DIR": str(config), "PYTHONPATH": str(BUNDLE / "lib")})
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT / "xmu-rollcall-cli", env=env, check=True)
        copied = work / "project"
        for relative in list(manifest["sha256"]) + ["manifest.json"]:
            target = copied / "portable" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(BUNDLE / relative, target)
        shutil.copyfile(ROOT / "run.py", copied / "run.py")
        script = r'''
import importlib.abc, runpy, sys
from pathlib import Path
class NoCrypto(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "Crypto" or fullname.startswith("Crypto."):
            raise AssertionError("Native Crypto import attempted")
sys.meta_path.insert(0, NoCrypto())
launcher = sys.argv[1]
sys.argv = [launcher, "--check"]
runpy.run_path(launcher, run_name="__main__")
import xmu_rollcall.verify, requests, charset_normalizer, xmulogin
library = Path(launcher).parent.resolve() / "portable/lib"
for module in (xmu_rollcall.verify, requests, charset_normalizer, xmulogin):
    assert library in Path(module.__file__).resolve().parents, module.__name__
'''
        subprocess.run([sys.executable, "-I", "-c", script, str(copied / "run.py")], env=env, cwd=work, check=True)
        for name, contents in before.items():
            assert (config / name).read_bytes() == contents, name
        assert json.loads(locations.read_text(encoding="utf-8"))["device_id"] == "fixture-device"
    print("Passed: bundle hashes, source parity, regression tests, isolated startup, bundled imports, and configuration preservation.")


if __name__ == "__main__":
    main()
