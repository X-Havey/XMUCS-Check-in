"""Start the portable XMU CLI; no pip install or package patching is required."""
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_bundle():
    manifest = read_json(ROOT / "manifest.json")
    for relative, expected in manifest["sha256"].items():
        path = (ROOT / relative).resolve()
        if ROOT not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Bundle integrity check failed: " + relative)


def select_config_dir():
    explicit = os.environ.get("XMU_ROLLCALL_CONFIG_DIR")
    if explicit:
        selected = Path(explicit).expanduser().resolve()
        selected.mkdir(parents=True, exist_ok=True)
        return selected
    previous = ROOT / ".runtime.json"
    state_files = [previous, ROOT / "install_state.json", ROOT.parent / "xmu-iphone-sync" / "install_state.json"]
    for state_file in state_files:
        if state_file.is_file():
            try:
                selected = Path(read_json(state_file)["config_dir"]).expanduser()
                if (selected / "config.json").is_file():
                    return selected.resolve()
            except (OSError, ValueError, KeyError, TypeError):
                pass
    home = Path.home()
    candidates = [home / ".xmu_rollcall", home / "Documents" / ".xmu_rollcall",
                  ROOT.parent / ".xmu_rollcall", Path.cwd() / ".xmu_rollcall"]
    for selected in candidates:
        if (selected / "config.json").is_file():
            return selected.resolve()
    # iOS permits Documents writes even when its app container root is read-only.
    for selected in [home / "Documents" / ".xmu_rollcall", ROOT / ".xmu_rollcall"]:
        try:
            selected.mkdir(parents=True, exist_ok=True)
            probe = selected / (".write-test-" + uuid.uuid4().hex)
            probe.write_bytes(b"")
            probe.unlink()
            return selected.resolve()
        except OSError:
            continue
    raise RuntimeError("Could not find a writable configuration directory.")


def configure_locations(config_dir):
    template_path = ROOT / "radar_locations.json"
    template = read_json(template_path)
    template_hash = hashlib.sha256(template_path.read_bytes()).hexdigest()
    path = config_dir / "radar_locations.json"
    state_path = ROOT / ".runtime.json"
    old_state = read_json(state_path) if state_path.is_file() else {}
    existing = read_json(path) if path.is_file() else {}
    already_synced = (old_state.get("config_dir") == str(config_dir)
                      and old_state.get("template_hash") == template_hash and path.is_file())
    if not already_synced:
        device = existing.get("device_id")
        if not isinstance(device, str) or not device.strip():
            device = str(uuid.uuid4())
        template["device_id"] = device
        if template != existing:
            if path.is_file():
                backup = ROOT / "backups" / ("locations-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".json")
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(path.read_bytes())
            temporary = path.with_name(".radar-locations-" + uuid.uuid4().hex + ".json")
            temporary.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(path)
        state_path.write_text(json.dumps({"config_dir": str(config_dir), "template_hash": template_hash}, indent=2) + "\n", encoding="utf-8")
    return path


def prepare_requests():
    import requests
    original = requests.sessions.Session.request

    def bounded_request(session, method, url, **kwargs):
        kwargs.setdefault("timeout", (5, 20))
        return original(session, method, url, **kwargs)

    if not getattr(original, "_xmu_bounded", False):
        bounded_request._xmu_bounded = True
        requests.sessions.Session.request = bounded_request


def main():
    verify_bundle()
    print("Local patch: 2026-10-23 (UTC timetable date fix)")
    config_dir = select_config_dir()
    locations = configure_locations(config_dir)
    os.environ["XMU_ROLLCALL_CONFIG_DIR"] = str(config_dir)
    os.environ["XMU_RADAR_LOCATIONS_FILE"] = str(locations)
    sys.path.insert(0, str(ROOT / "lib"))
    prepare_requests()
    from xmu_rollcall.cli import cli
    from xmu_rollcall.config import load_config, is_config_complete
    from xmu_rollcall.radar import load_locations
    configured, _ = load_locations(locations)
    if sys.argv[1:] == ["--check"]:
        print("Ready: portable CLI, pure Python AES-CBC,", len(configured), "radar locations.")
        print("Account config found:", (config_dir / "config.json").is_file())
        return
    arguments = sys.argv[1:] or ["start"]
    if arguments == ["start"] and not is_config_complete(load_config()):
        print("First use: configure your phone account.")
        cli.main(args=["config"], prog_name="xmu", standalone_mode=False)
        if not is_config_complete(load_config()):
            return
    cli.main(args=arguments, prog_name="xmu")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped.")
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        print("Start failed:", error, file=sys.stderr)
        raise SystemExit(1)
