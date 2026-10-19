"""Build, validate and package allowlisted Windows/source release assets."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import __version__

SOURCE_FILES = [
    "app.py", "version.py", "animation_sequence.py", "decoder.py", "layout.py", "project_match.py",
    "compression.py", "compression_fast.py", "workshop.py", "workshop_app.py", "repacking.py",
    "test_workshop.py", "workshop.spec", "requirements.txt", "requirements-dev.txt",
    ".python-version", ".gitignore", ".gitattributes", "README.md", "LICENSE",
    "CHANGELOG.md", "CONTRIBUTING.md", "docs/CUSTOM_SPRITES.md", "docs/WORKFLOW.md",
    "docs/RELEASING.md", "scripts/build_release.py", ".github/workflows/windows.yml",
    ".github/ISSUE_TEMPLATE/bug_report.md", "docs/licenses/Tcl.txt", "docs/licenses/Tk.txt",
    "docs/licenses/README.md",
]


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def licenses():
    notices = {}
    for name in ["numpy", "Pillow", "scipy", "numba", "llvmlite", "pyinstaller", "pyinstaller-hooks-contrib"]:
        distribution = importlib.metadata.distribution(name)
        found = 0
        for file in distribution.files or []:
            if not Path(file).name.lower().startswith(("license", "licence", "copying", "notice")):
                continue
            path = Path(distribution.locate_file(file))
            if not path.is_file():
                continue
            label = str(file).replace("\\", "/").replace("..", "parent").replace("/", "__")
            notices[f"third-party-licenses/{name}/{label}"] = path.read_bytes()
            found += 1
        if not found:
            raise RuntimeError(f"No license notices found for bundled dependency {name}")
    python_license = next((Path(sys.base_prefix) / name for name in ["LICENSE.txt", "LICENSE"]
                           if (Path(sys.base_prefix) / name).is_file()), None)
    if python_license is None:
        raise RuntimeError("Cannot locate the bundled Python license")
    notices["third-party-licenses/Python/LICENSE.txt"] = python_license.read_bytes()
    import tkinter
    window = tkinter.Tk()
    window.withdraw()
    try:
        libraries = [Path(window.tk.eval("info library")), Path(window.tk.eval("set tk_library"))]
    finally:
        window.destroy()
    for name, library in zip(["Tcl", "Tk"], libraries):
        license_path = next((library / filename for filename in ["license.terms", "license", "LICENSE"]
                             if (library / filename).is_file()), None)
        if license_path is None:
            license_path = ROOT / "docs" / "licenses" / f"{name}.txt"
        if not license_path.is_file():
            raise RuntimeError(f"Cannot locate the bundled {name} license")
        notices[f"third-party-licenses/{name}/LICENSE.txt"] = license_path.read_bytes()
    notices["THIRD_PARTY_NOTICES.txt"] = (
        "Skullgirls Sprite Workshop includes Python, Tcl/Tk, NumPy, Pillow, SciPy, "
        "Numba/llvmlite and the PyInstaller bootloader. Their license texts, "
        "including notices for bundled library components, are included in "
        "third-party-licenses/. The app source is licensed under MIT. "
        "Skullgirls game assets are not distributed with this package.\n"
    ).encode("utf-8")
    return notices


def write_zip(path, files):
    prefix = f"Skullgirls-Sprite-Workshop-{__version__}"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, content in sorted(files.items()):
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError("Invalid package path")
            archive.writestr(f"{prefix}/{name}", content)
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Corrupt package member: {bad}")


def main():
    if os.name != "nt" or platform.architecture()[0] != "64bit":
        raise SystemExit("Build the supported portable release on Windows x64")
    release = ROOT / "release"
    staging = release / "staging"
    validation = release / "validation"
    validation.mkdir(parents=True, exist_ok=True)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", staging,
        "--workpath", ROOT / "build" / "pyinstaller", ROOT / "workshop.spec")
    executable = staging / "Skullgirls Sprite Workshop.exe"
    self_test = validation / "packaged-tests.json"
    smoke_test = validation / "packaged-ui.json"
    run(executable, "--self-test", self_test)
    results = json.loads(self_test.read_text(encoding="utf-8"))
    if results.get("status") != "passed" or not results.get("native_cpu_available"):
        raise RuntimeError("Packaged tests or native CPU backend failed")
    run(executable, "--smoke-test", smoke_test)
    if json.loads(smoke_test.read_text(encoding="utf-8")).get("ui") != "passed":
        raise RuntimeError("Packaged UI smoke test failed")
    source = {name: (ROOT / name).read_bytes() for name in SOURCE_FILES}
    portable = {name: source[name] for name in ["README.md", "LICENSE", "CHANGELOG.md",
                                               "docs/CUSTOM_SPRITES.md", "docs/WORKFLOW.md"]}
    portable[executable.name] = executable.read_bytes()
    portable.update(licenses())
    packages = [release / f"Skullgirls-Sprite-Workshop-v{__version__}-windows-x64.zip",
                release / f"Skullgirls-Sprite-Workshop-v{__version__}-source.zip"]
    write_zip(packages[0], portable)
    write_zip(packages[1], source)
    checksums = []
    for path in packages:
        with path.open("rb") as stream:
            checksums.append(f"{hashlib.file_digest(stream, 'sha256').hexdigest()}  {path.name}")
    (release / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    # Retain one conveniently launchable build beside the source, excluded from Git.
    import shutil
    try:
        shutil.copy2(executable, ROOT / executable.name)
    except PermissionError:
        launcher = ROOT / f"Skullgirls Sprite Workshop {__version__}.exe"
        shutil.copy2(executable, launcher)
        print(f"The previous launcher is open. Updated launcher: {launcher}")
    print(json.dumps({"version": __version__, "checks": len(results["checks"]),
                      "native_cpu": True, "assets": [str(p) for p in packages]}, indent=2))


if __name__ == "__main__":
    main()
