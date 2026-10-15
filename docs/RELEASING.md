# Preparing a release

The supported build is Windows x64 with Python 3.12. No game installation is needed for build or fixture validation.

1. Update `version.py`, the matching release section in `CHANGELOG.md`, and user documentation.
2. Install `requirements-dev.txt` in a clean virtual environment.
3. Run `python scripts/build_release.py`. It builds the executable, runs packaged smoke/self-tests, collects dependency license notices, creates allowlisted source and portable ZIPs, and writes SHA-256 checksums.
4. Review the contents of both ZIPs and the reports in `release/validation`. Inspect the app manually. For art-fitting changes, also check a locally owned game without distributing its assets.
5. Create the GitHub repository and push the source. Create a release for the corresponding version tag (for example `v0.2.0`) and upload the Windows ZIP, source ZIP, and `SHA256SUMS.txt`. Use the matching changelog section for release notes.

The Windows workflow builds and validates artifacts on pushes, pull requests, and manual runs. It uploads build artifacts without publishing a GitHub release. Its action usage follows the official [checkout](https://github.com/actions/checkout), [setup-python](https://github.com/actions/setup-python), and [upload-artifact](https://github.com/actions/upload-artifact) documentation.

Generated build directories, validation fixtures, local archives, executables and release ZIPs are excluded from Git. The source package uses an explicit file allowlist. No game art, game archives, user sprite projects, local backups, credentials or personal test reports belong in public source archives.
