#!/usr/bin/env python3
"""Pack and unpack the built reports of the demo site.

The reports take hours to build, so they are built by hand (``make site``) and uploaded as a release asset. The Pages workflow
downloads the latest release, checks the bundle with :func:`unpack` and builds the documentation and the explorer around it.

The bundle ``semsynth-site.tar.gz`` holds ``output/`` (what the site publishes), ``downloads-cache/`` (the small tables that the
documentation notebooks read, which are not published) and ``site-manifest.json``. The sidecar ``semsynth-site.tar.gz.sha256``
has its checksum in ``sha256sum`` format. Only the standard library is used, so this runs before anything is installed.

    python scripts/site_bundle.py pack --dest dist-site
    python scripts/site_bundle.py unpack dist-site/semsynth-site.tar.gz --dest .
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

BUNDLE = "semsynth-site.tar.gz"
MANIFEST = "site-manifest.json"
FORMAT = 1
ALLOWED_TOP = ("output", "downloads-cache")
FORBIDDEN_SUFFIXES = (".pickle", ".pkl")  # loading a pickle can run code, so a published run folder must not hold one
MAX_BYTES = 500 * 1024 * 1024  # a bundle that unpacks to more than this is not a bundle of reports


class BundleError(Exception):
    """The bundle is missing something, does not match its checksum, or holds a file that it must not."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink())


def pack(
    output: Path,
    dest_dir: Path,
    *,
    docs_data: list[Path] | None = None,
    commit: str,
    config: str,
    lock: Path | None = None,
) -> Path:
    """Write the bundle and its checksum to ``dest_dir`` and return the path of the bundle.

    Args:
        output: The output folder of the reports (``output/``); it must hold ``catalog.json`` and at least one dataset.
        dest_dir: Where the bundle and ``<bundle>.sha256`` are written.
        docs_data: Files under ``downloads-cache/`` that the documentation notebooks read, such as ``downloads-cache/uciml/45.csv.gz``.
        commit: The commit of semsynth that built the reports.
        config: The pipeline configuration that built them.
        lock: The lock file whose hash is recorded.
    """
    if not (output / "catalog.json").is_file():
        raise BundleError(f"{output}/catalog.json is missing: build the catalog first (python -m semsynth mappings)")
    datasets = sorted(p.name for p in output.iterdir() if (p / "dataset.codebook.jsonld").is_file())
    if not datasets:
        raise BundleError(f"no dataset with a codebook under {output}")
    members = [(f, PurePosixPath("output") / f.relative_to(output).as_posix()) for f in _files(output)]
    pickles = [str(name) for _, name in members if name.suffix in FORBIDDEN_SUFFIXES]
    if pickles:
        raise BundleError(f"the output holds pickles, which are not published: {', '.join(pickles[:3])}")
    for extra in docs_data or []:
        if not extra.is_file():
            raise BundleError(f"{extra} does not exist")
        members.append((extra, PurePosixPath("downloads-cache") / PurePosixPath(*extra.parts[extra.parts.index("downloads-cache") + 1 :])))
    manifest = {
        "format": FORMAT,
        "semsynth_commit": commit,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": config,
        "lock_sha256": sha256_of(lock) if lock and lock.is_file() else None,
        "datasets": datasets,
        "files": len(members),
    }
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive = dest_dir / BUNDLE
    text = json.dumps(manifest, indent=2).encode()
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo(MANIFEST)
        info.size, info.mtime = len(text), 0
        tar.addfile(info, io.BytesIO(text))
        for source, name in sorted(members, key=lambda m: str(m[1])):
            info = tar.gettarinfo(str(source), arcname=str(name))
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with source.open("rb") as handle:
                tar.addfile(info, handle)
    (dest_dir / f"{BUNDLE}.sha256").write_text(f"{sha256_of(archive)}  {BUNDLE}\n", encoding="utf-8")
    return archive


def _safe(member: tarfile.TarInfo) -> PurePosixPath | None:
    """The path of a member, or ``None`` for a directory entry; anything that could land outside the target is an error."""
    if member.isdir():
        return None
    if not member.isreg():
        raise BundleError(f"{member.name!r} is not a regular file (links and devices are not allowed)")
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts or "\\" in member.name:
        raise BundleError(f"{member.name!r} is outside the bundle")
    if path.suffix in FORBIDDEN_SUFFIXES:
        raise BundleError(f"{member.name!r} is a pickle; a bundle does not carry them")
    if path.name != MANIFEST and path.parts[0] not in ALLOWED_TOP:
        raise BundleError(f"{member.name!r} is not under {' or '.join(ALLOWED_TOP)}")
    if path.name == MANIFEST and len(path.parts) != 1:
        raise BundleError(f"{member.name!r}: the manifest must be at the top")
    return path


def unpack(archive: Path, dest: Path, *, sha256_file: Path | None) -> dict[str, object]:
    """Check the bundle and extract it into ``dest``; return its manifest.

    Raises:
        BundleError: If the checksum does not match, a member is unsafe or unexpected, the manifest is missing or of another
            format, or the bundle does not hold what a site needs.
    """
    if sha256_file is not None:
        expected = sha256_file.read_text(encoding="utf-8").split()[0].lower()
        if sha256_of(archive) != expected:
            raise BundleError(f"{archive.name} does not match {sha256_file.name}")
    total, seen = 0, set()
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            _safe(member)
            total += member.size
        if total > MAX_BYTES:
            raise BundleError(f"the bundle unpacks to {total} bytes, more than {MAX_BYTES}")
        for member in members:
            path = _safe(member)
            if path is None:
                continue
            target = dest / path
            target.parent.mkdir(parents=True, exist_ok=True)
            handle = tar.extractfile(member)
            assert handle is not None
            target.write_bytes(handle.read())
            seen.add(str(path))
    if MANIFEST not in seen:
        raise BundleError(f"{MANIFEST} is missing")
    manifest = json.loads((dest / MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT:
        raise BundleError(f"the bundle has format {manifest.get('format')!r}; this script reads format {FORMAT}")
    if "output/catalog.json" not in seen or not manifest.get("datasets"):
        raise BundleError("the bundle has no catalog or no dataset")
    return manifest  # type: ignore[no-any-return]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("pack", help="write the bundle of the reports of this checkout")
    make.add_argument("--output", type=Path, default=Path("output"))
    make.add_argument("--dest", type=Path, default=Path("dist-site"))
    make.add_argument("--docs-data", type=Path, action="append", default=[])
    make.add_argument("--config", default="configs/demo_config.toml")
    make.add_argument("--allow-dirty", action="store_true", help="pack although the working tree has uncommitted changes")
    take = sub.add_parser("unpack", help="check a bundle and extract it")
    take.add_argument("archive", type=Path)
    take.add_argument("--dest", type=Path, default=Path("."))
    take.add_argument("--sha256", type=Path, help="checksum file; default: <archive>.sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "pack":
            if not args.allow_dirty and _git("status", "--porcelain"):
                raise BundleError("the working tree has uncommitted changes; commit them or pass --allow-dirty")
            archive = pack(args.output, args.dest, docs_data=args.docs_data, commit=_git("rev-parse", "HEAD"), config=args.config, lock=Path("uv.lock"))
            print(f"wrote {archive} ({archive.stat().st_size} bytes) and {archive.name}.sha256")
        else:
            checksum = args.sha256 or args.archive.with_name(args.archive.name + ".sha256")
            if not checksum.is_file():
                raise BundleError(f"{checksum} not found: a bundle is only unpacked with its checksum")
            manifest = unpack(args.archive, args.dest, sha256_file=checksum)
            print(f"unpacked {manifest['datasets']} built {manifest['built_at']} from {str(manifest['semsynth_commit'])[:10]}")
    except BundleError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
