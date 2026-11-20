"""The release bundle of the built reports: what is packed comes out unchanged, and nothing unsafe or incomplete is unpacked."""

from __future__ import annotations

import importlib.util
import io
import json
import tarfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bundle = _load("site_bundle")
check = _load("check_output")


def _output(root: Path) -> Path:
    output = root / "output"
    run = output / "heart" / "models" / "chain"
    run.mkdir(parents=True)
    (output / "catalog.json").write_text(
        json.dumps(
            {
                "@graph": [
                    {"@id": "https://example.org/semsynth/output/#catalog"},
                    {"dcat:downloadURL": {"@id": "https://example.org/semsynth/output/heart/models/chain/synthetic.csv"}},
                    {"dcat:downloadURL": {"@id": "https://elsewhere.org/not-ours.csv"}},
                ]
            }
        )
    )
    (output / "index.html").write_text("<html></html>")
    (output / "heart" / "dataset.codebook.jsonld").write_text("{}")
    (run / "metrics.privacy.json").write_text(json.dumps({"status": "ok"}))
    (run / "metrics.baselines.json").write_text("{}")
    (run / "provenance.json").write_text("{}")
    (run / "synthetic.csv").write_text("a,b\n1,2\n")
    return output


def _pack(tmp_path: Path) -> Path:
    cache = tmp_path / "downloads-cache" / "uciml"
    cache.mkdir(parents=True)
    (cache / "45.csv.gz").write_bytes(b"data")
    return bundle.pack(_output(tmp_path), tmp_path / "dist", docs_data=[cache / "45.csv.gz"], commit="abc123", config="configs/demo_config.toml")


def _tar(path: Path, members: dict[str, bytes], *, extra: list[tarfile.TarInfo] | None = None) -> Path:
    with tarfile.open(path, "w:gz") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for info in extra or []:
            tar.addfile(info)
    return path


MANIFEST = json.dumps({"format": 1, "datasets": ["heart"], "built_at": "now", "semsynth_commit": "abc"}).encode()


def test_what_is_packed_comes_out_unchanged_with_a_manifest(tmp_path: Path) -> None:
    archive = _pack(tmp_path)
    target = tmp_path / "site"
    manifest = bundle.unpack(archive, target, sha256_file=archive.with_name(archive.name + ".sha256"))
    assert manifest["datasets"] == ["heart"] and manifest["semsynth_commit"] == "abc123" and manifest["config"] == "configs/demo_config.toml"
    assert (target / "output" / "heart" / "models" / "chain" / "synthetic.csv").read_text() == "a,b\n1,2\n"
    assert (target / "downloads-cache" / "uciml" / "45.csv.gz").read_bytes() == b"data"
    assert check.problems(target / "output") == []


def test_a_changed_bundle_does_not_match_its_checksum(tmp_path: Path) -> None:
    archive = _pack(tmp_path)
    checksum = archive.with_name(archive.name + ".sha256")
    archive.write_bytes(archive.read_bytes() + b"x")
    with pytest.raises(bundle.BundleError, match="does not match"):
        bundle.unpack(archive, tmp_path / "site", sha256_file=checksum)


@pytest.mark.parametrize("name", ["../evil.txt", "/etc/evil.txt", "output/../../evil.txt", "elsewhere/file.txt"])
def test_a_path_outside_the_bundle_is_refused(tmp_path: Path, name: str) -> None:
    archive = _tar(tmp_path / "bad.tar.gz", {"site-manifest.json": MANIFEST, name: b"x"})
    with pytest.raises(bundle.BundleError, match=r"outside the bundle|is not under"):
        bundle.unpack(archive, tmp_path / "site", sha256_file=None)
    assert not (tmp_path / "evil.txt").exists()


def test_a_link_is_refused(tmp_path: Path) -> None:
    link = tarfile.TarInfo("output/link")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    archive = _tar(tmp_path / "bad.tar.gz", {"site-manifest.json": MANIFEST}, extra=[link])
    with pytest.raises(bundle.BundleError, match="not a regular file"):
        bundle.unpack(archive, tmp_path / "site", sha256_file=None)


def test_a_bundle_without_a_manifest_a_catalog_or_the_right_format_is_refused(tmp_path: Path) -> None:
    with pytest.raises(bundle.BundleError, match=r"site-manifest\.json is missing"):
        bundle.unpack(_tar(tmp_path / "a.tar.gz", {"output/catalog.json": b"{}"}), tmp_path / "a", sha256_file=None)
    with pytest.raises(bundle.BundleError, match="no catalog"):
        bundle.unpack(_tar(tmp_path / "b.tar.gz", {"site-manifest.json": MANIFEST}), tmp_path / "b", sha256_file=None)
    old = json.dumps({"format": 0, "datasets": ["heart"]}).encode()
    with pytest.raises(bundle.BundleError, match="format"):
        bundle.unpack(_tar(tmp_path / "c.tar.gz", {"site-manifest.json": old, "output/catalog.json": b"{}"}), tmp_path / "c", sha256_file=None)


def test_nothing_is_packed_without_a_catalog_or_a_dataset(tmp_path: Path) -> None:
    (tmp_path / "output").mkdir()
    with pytest.raises(bundle.BundleError, match=r"catalog\.json is missing"):
        bundle.pack(tmp_path / "output", tmp_path / "dist", commit="x", config="c")
    (tmp_path / "output" / "catalog.json").write_text("{}")
    with pytest.raises(bundle.BundleError, match="no dataset"):
        bundle.pack(tmp_path / "output", tmp_path / "dist", commit="x", config="c")


def test_the_checks_name_what_a_build_lacks(tmp_path: Path) -> None:
    output = _output(tmp_path)
    (output / "heart" / "models" / "chain" / "metrics.privacy.json").write_text(json.dumps({"status": "skipped"}))
    (output / "heart" / "models" / "chain" / "metrics.baselines.json").unlink()
    found = check.problems(output)
    assert any("privacy metrics skipped" in line for line in found) and any("metrics.baselines.json is missing" in line for line in found)
    assert check.problems(tmp_path / "nowhere") == ["catalog.json is missing", "index.html is missing", "no dataset has a codebook"]


def test_the_command_line_unpacks_a_bundle_only_with_its_checksum(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    archive = _pack(tmp_path)
    assert bundle.main(["unpack", str(archive), "--dest", str(tmp_path / "site")]) == 0
    assert "unpacked ['heart']" in capsys.readouterr().out
    archive.with_name(archive.name + ".sha256").unlink()
    assert bundle.main(["unpack", str(archive), "--dest", str(tmp_path / "again")]) == 1
    assert "only unpacked with its checksum" in capsys.readouterr().err


def test_pack_refuses_a_working_tree_with_uncommitted_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "uncommitted.txt").write_text("x")
    monkeypatch.chdir(tmp_path)
    assert bundle.main(["pack", "--dest", str(tmp_path / "dist")]) == 1
    assert "uncommitted changes" in capsys.readouterr().err


def test_a_pickle_is_neither_packed_nor_unpacked_and_a_missing_download_is_named(tmp_path: Path) -> None:
    output = _output(tmp_path)
    assert check.problems(output) == []
    (output / "heart" / "models" / "chain" / "model.pickle").write_bytes(b"x")
    assert any("is a pickle" in line for line in check.problems(output))
    with pytest.raises(bundle.BundleError, match="pickles"):
        bundle.pack(output, tmp_path / "dist", commit="x", config="c")
    (output / "heart" / "models" / "chain" / "model.pickle").unlink()
    (output / "heart" / "models" / "chain" / "synthetic.csv").unlink()
    assert any("synthetic.csv, which is not in the output" in line for line in check.problems(output))
    archive = _tar(tmp_path / "bad.tar.gz", {"site-manifest.json": MANIFEST, "output/heart/models/chain/model.pickle": b"x"})
    with pytest.raises(bundle.BundleError, match="is a pickle"):
        bundle.unpack(archive, tmp_path / "site", sha256_file=None)
