"""Fetch Studio agent skills from GitHub into skills/ (no homemade copies).

Preferred on Windows when git/API is blocked: download zip from
  https://codeload.github.com/{owner}/{repo}/zip/refs/heads/main
into skills/_vendor/, extract, then copy:
  html-ppt-skill-main            -> skills/html-ppt
  .../skills/video-podcast-maker -> skills/video-podcast-maker
  humanizer-main/{SKILL,AGENTS,LICENSE,README}.md -> skills/humanizer

Always write ORIGIN.txt with do_not_rewrite=true.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "skills"
VENDOR = OUT / "_vendor"

# Official sources — do not replace with local rewrites
SOURCES = {
    "humanizer": {
        "repo": "blader/humanizer",
        "paths": ["SKILL.md", "AGENTS.md", "LICENSE", "README.md"],
        "zip_url": "https://codeload.github.com/blader/humanizer/zip/refs/heads/main",
    },
    "html-ppt": {
        "repo": "lewislulu/html-ppt-skill",
        "recursive": True,
        "root": "",
        "zip_url": "https://codeload.github.com/lewislulu/html-ppt-skill/zip/refs/heads/main",
        "zip_subdir": "html-ppt-skill-main",
    },
    "video-podcast-maker": {
        "repo": "Agents365-ai/video-podcast-maker",
        "recursive": True,
        "root": "skills/video-podcast-maker",
        "dest_name": "video-podcast-maker",
        "zip_url": "https://codeload.github.com/Agents365-ai/video-podcast-maker/zip/refs/heads/main",
        "zip_subdir": "video-podcast-maker-main/skills/video-podcast-maker",
    },
}

API = "https://api.github.com/repos/{repo}/contents/{path}"
RAW = "https://raw.githubusercontent.com/{repo}/main/{path}"


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "PhotosXAgent-skill-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def list_dir(repo: str, path: str = "") -> list[dict]:
    url = API.format(repo=repo, path=path.strip("/"))
    data = json.loads(http_get(url).decode("utf-8"))
    if isinstance(data, dict) and data.get("message"):
        raise RuntimeError(data["message"])
    return data


def download_file(repo: str, path: str, dest: Path) -> None:
    url = RAW.format(repo=repo, path=path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(http_get(url))
    print(f"  + {path}")


def download_tree(repo: str, remote_root: str, local_root: Path) -> None:
    stack = [remote_root.strip("/")]
    while stack:
        cur = stack.pop()
        try:
            entries = list_dir(repo, cur)
        except Exception as exc:
            print(f"  ! skip list {cur}: {exc}")
            continue
        for item in entries:
            name = item["name"]
            # skip heavy / irrelevant
            if name in {".git", "node_modules", "__pycache__", ".venv"}:
                continue
            rel = item["path"]
            if item["type"] == "dir":
                stack.append(rel)
            elif item["type"] == "file":
                # strip remote_root prefix for local layout
                if remote_root and rel.startswith(remote_root.strip("/") + "/"):
                    local_rel = rel[len(remote_root.strip("/")) + 1 :]
                elif remote_root and rel == remote_root.strip("/"):
                    continue
                else:
                    local_rel = rel
                try:
                    download_file(repo, rel, local_root / local_rel)
                except Exception as exc:
                    print(f"  ! fail {rel}: {exc}")


def write_origin(dest: Path, cfg: dict) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "ORIGIN.txt").write_text(
        f"source=https://github.com/{cfg['repo']}\n"
        f"path={cfg.get('root') or '/'}\n"
        f"do_not_rewrite=true\n",
        encoding="utf-8",
    )


def fetch_via_zip(name: str, cfg: dict, dest: Path) -> None:
    import shutil

    VENDOR.mkdir(parents=True, exist_ok=True)
    zip_path = VENDOR / f"{name}.zip"
    print(f"  zip {cfg['zip_url']}")
    zip_path.write_bytes(http_get(cfg["zip_url"]))
    extract_to = VENDOR / f"{name}-tmp"
    if extract_to.exists():
        shutil.rmtree(extract_to)
    extract_to.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_to)

    if dest.exists():
        shutil.rmtree(dest)

    if name == "humanizer":
        src = next(extract_to.glob("humanizer-*"))
        dest.mkdir(parents=True, exist_ok=True)
        for fname in cfg.get("paths") or ["SKILL.md"]:
            p = src / fname
            if p.exists():
                shutil.copy2(p, dest / Path(fname).name)
        scripts = src / "scripts"
        if scripts.exists():
            shutil.copytree(scripts, dest / "scripts")
    else:
        sub = cfg.get("zip_subdir") or ""
        src = extract_to / sub if sub else extract_to
        if not src.exists():
            # fallback: first top-level dir
            src = next(p for p in extract_to.iterdir() if p.is_dir())
        shutil.copytree(src, dest)

    write_origin(dest, cfg)
    print(f"  installed -> {dest}")


def fetch_via_api(cfg: dict, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if cfg.get("recursive"):
        download_tree(cfg["repo"], cfg.get("root") or "", dest)
    else:
        for path in cfg.get("paths") or ["SKILL.md"]:
            download_file(cfg["repo"], path, dest / Path(path).name)
    write_origin(dest, cfg)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"fetched": [], "note": "Vendored from GitHub; do not hand-edit skill bodies."}
    for name, cfg in SOURCES.items():
        dest_name = cfg.get("dest_name") or name
        dest = OUT / dest_name
        print(f"==> {dest_name} from {cfg['repo']}")
        ok = False
        err = None
        if cfg.get("zip_url"):
            try:
                fetch_via_zip(name, cfg, dest)
                ok = True
            except Exception as exc:
                err = str(exc)
                print(f"  zip failed, try API: {exc}")
        if not ok:
            try:
                fetch_via_api(cfg, dest)
                ok = True
                err = None
            except Exception as exc:
                err = str(exc)
                print(f"FAILED {name}: {exc}")
        meta["fetched"].append(
            {"name": dest_name, "repo": cfg["repo"], "ok": ok, **({"error": err} if err else {})}
        )
    (OUT / "SOURCES.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(x.get("ok") for x in meta["fetched"]) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
