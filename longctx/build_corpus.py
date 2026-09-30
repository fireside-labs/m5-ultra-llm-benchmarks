#!/usr/bin/env python3
"""Build a reproducible long-context corpus.

books: public-domain Project Gutenberg novels, fixed IDs and order (~2.5M+ tokens).
code:  source files from the local llama.cpp checkout at its current commit ($LLAMA_CPP,
       default ../llama.cpp; the manifest records the commit).

Writes corpus/<kind>.txt plus corpus/<kind>.manifest.json (sources + sha256)
so anyone can rebuild the exact same prompts.
"""
import argparse, hashlib, http.client, json, os, pathlib, subprocess, time, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "corpus"

# Fixed order. Do not reorder: prompts are prefixes of this concatenation.
BOOKS = [
    (2600, "War and Peace"),
    (135, "Les Miserables"),
    (1399, "Anna Karenina"),
    (28054, "The Brothers Karamazov"),
    (145, "Middlemarch"),
    (1023, "Bleak House"),
    (996, "Don Quixote"),
    (2701, "Moby Dick"),
    (1400, "Great Expectations"),
    (766, "David Copperfield"),
]


def strip_gutenberg(text):
    start = text.find("*** START OF")
    if start != -1:
        text = text[text.find("\n", start) + 1:]
    end = text.find("*** END OF")
    if end != -1:
        text = text[:end]
    return text.strip()


def fetch(url, tries=5):
    for i in range(tries):
        try:
            return urllib.request.urlopen(url, timeout=120).read().decode("utf-8", "replace")
        except (OSError, http.client.HTTPException) as e:
            if i == tries - 1:
                raise
            print(f"  retry {url}: {e.__class__.__name__}")
            time.sleep(3 * (i + 1))


def build_books():
    parts, sources = [], []
    for gid, title in BOOKS:
        url = f"https://www.gutenberg.org/cache/epub/{gid}/pg{gid}.txt"
        raw = fetch(url)
        body = strip_gutenberg(raw).replace("\r\n", "\n")
        parts.append(f"\n\n===== {title} =====\n\n{body}")
        sources.append({"gutenberg_id": gid, "title": title, "url": url, "chars": len(body)})
        print(f"  {title}: {len(body):,} chars")
    return "".join(parts), sources


def build_code():
    repo = pathlib.Path(os.path.expanduser(os.environ.get("LLAMA_CPP", str(HERE.parent / "llama.cpp"))))
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    files = sorted(
        p for d in ("src", "ggml/src", "common", "tools")
        for p in (repo / d).rglob("*")
        if p.suffix in (".c", ".cpp", ".h", ".hpp", ".py", ".m", ".metal") and p.is_file()
    )
    parts, sources = [], []
    for p in files:
        rel = p.relative_to(repo).as_posix()
        body = p.read_text(errors="replace")
        parts.append(f"\n\n// ===== file: {rel} =====\n\n{body}")
        sources.append({"path": rel, "chars": len(body)})
    return "".join(parts), [{"repo": "ggml-org/llama.cpp", "commit": commit, "files": len(sources)}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["books", "code"], default="books")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    text, sources = build_books() if args.kind == "books" else build_code()
    path = OUT / f"{args.kind}.txt"
    path.write_text(text)
    sha = hashlib.sha256(text.encode()).hexdigest()
    (OUT / f"{args.kind}.manifest.json").write_text(json.dumps(
        {"kind": args.kind, "chars": len(text), "sha256": sha, "sources": sources}, indent=2))
    print(f"wrote {path} ({len(text):,} chars, sha256 {sha[:12]})")


if __name__ == "__main__":
    main()
