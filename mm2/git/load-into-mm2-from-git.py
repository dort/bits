#!/usr/bin/env python3
r"""Convert a git repository into an MM2 fact file, per bits/mm2/git/plan.

Walks the repository's full object graph (refs, commits, trees, blobs)
with git plumbing commands and writes one S-expression fact per line,
loadable by `mork run` and queryable with MM2 joins. Free text (names,
messages, paths, blob contents) is emitted as MM2 quoted-string symbols;
any value whose raw size exceeds the truncation limit (default 10000
bytes) is cut and recorded with a (truncated ...) fact.

Fact schema (shas, modes, sizes, and unix timestamps are bare symbols —
timestamps and sizes are i64 literals usable with MORK's pure sink):

  (repo "<absolute path>")
  (head-ref "<refname>")                        symbolic HEAD, if any
  (head <sha>)                                  resolved HEAD commit
  (ref "<refname>" <sha>)                       every ref (for-each-ref)
  (commit <sha>)
  (commit-tree <sha> <tree-sha>)
  (commit-parent <sha> <parent-sha>)            one per parent
  (commit-author <sha> "<name>" "<email>" <unix-ts> <tz>)
  (commit-committer <sha> "<name>" "<email>" <unix-ts> <tz>)
  (commit-subject <sha> "<first message line>")
  (commit-message <sha> "<full message>")       truncated per the limit
  (commit-change <sha> <STATUS> "<path>")       A/M/D/T per --name-status
  (commit-rename <sha> "<old path>" "<new path>")
  (commit-file <sha> "<path>" <blob-sha>)       full snapshot per commit
  (tree <sha>)
  (tree-entry <tree-sha> "<name>" <mode> <type> <obj-sha>)
  (blob <sha> <size>)
  (blob-text <sha> "<content>")                 truncated per the limit
  (blob-binary <sha>)                           content withheld
  (truncated <sha> <original-size>)             a value above was cut

String encoding: MM2's parser keeps quoted symbols verbatim (escapes are
not decoded), so the stored text IS the encoded form. This converter
escapes backslash and double quote with a backslash, and control
characters as \n \r \t \xNN, keeping every fact on one line. Queries
that match literal text must use the same encoding; this converter is
the single producer, so encodings are consistent across all facts.

Usage:
  load-into-mm2-from-git.py [REPO] [OUTPUT] [LIMIT]
    REPO    repository path        (default: the repo containing this script)
    OUTPUT  .mm2 file to write     (default: <repo parent>/<repo name>-git-info.mm2,
                                    i.e. /home/ni/repos/m/bits-git-info.mm2 for bits)
    LIMIT   truncation limit, bytes (default: 10000)
"""

import subprocess
import sys
from pathlib import Path


def git(repo, *args, binary=False):
    out = subprocess.run(["git", "-C", str(repo), *args],
                         capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode("utf-8", errors="replace")


def mm2_string(text):
    """Encode text as an MM2 quoted-string symbol, one line, parser-safe."""
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def truncate(data, limit):
    """Cut bytes at the limit; return (text, was_truncated)."""
    if len(data) <= limit:
        return data.decode("utf-8", errors="replace"), False
    return data[:limit].decode("utf-8", errors="ignore"), True


def parse_person(line):
    """'Name Possibly Spaced <email> 1234567890 +0000' -> (name, email, ts, tz)."""
    rest, ts, tz = line.rsplit(" ", 2)
    name, _, email = rest.rpartition(" <")
    return name, email.rstrip(">"), ts, tz


def main():
    script_repo = Path(__file__).resolve().parent
    repo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    if repo is None:
        repo = Path(git(script_repo, "rev-parse", "--show-toplevel").strip())
    out_path = (Path(sys.argv[2]) if len(sys.argv) > 2
                else repo.parent / f"{repo.name}-git-info.mm2")
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10000

    facts = []
    counts = {}

    def emit(kind, *fields):
        facts.append(f"({kind} {' '.join(fields)})" if fields else f"({kind})")
        counts[kind] = counts.get(kind, 0) + 1

    emit("repo", mm2_string(str(repo)))

    # ----- refs and HEAD -------------------------------------------------
    headref = subprocess.run(["git", "-C", str(repo), "symbolic-ref", "-q", "HEAD"],
                             capture_output=True, text=True)
    if headref.returncode == 0:
        emit("head-ref", mm2_string(headref.stdout.strip()))
    emit("head", git(repo, "rev-parse", "HEAD").strip())
    for line in sorted(git(repo, "for-each-ref",
                           "--format=%(refname) %(objectname)").splitlines()):
        refname, sha = line.split(" ", 1)
        emit("ref", mm2_string(refname), sha)

    # ----- object inventory ---------------------------------------------
    objects = {}  # sha -> (type, size)
    for line in git(repo, "cat-file", "--batch-all-objects",
                    "--batch-check=%(objectname) %(objecttype) %(objectsize)").splitlines():
        sha, otype, size = line.split()
        objects[sha] = (otype, int(size))

    # ----- commits -------------------------------------------------------
    commit_shas = sorted(s for s, (t, _) in objects.items() if t == "commit")
    for sha in commit_shas:
        raw = git(repo, "cat-file", "commit", sha, binary=True)
        head_part, _, message = raw.partition(b"\n\n")
        emit("commit", sha)
        for hline in head_part.decode("utf-8", errors="replace").splitlines():
            key, _, val = hline.partition(" ")
            if key == "tree":
                emit("commit-tree", sha, val)
            elif key == "parent":
                emit("commit-parent", sha, val)
            elif key in ("author", "committer"):
                name, email, ts, tz = parse_person(val)
                emit(f"commit-{key}", sha, mm2_string(name),
                     mm2_string(email), ts, tz)
        text, cut = truncate(message, limit)
        emit("commit-subject", sha,
             mm2_string(text.split("\n", 1)[0].strip()))
        emit("commit-message", sha, mm2_string(text.rstrip("\n")))
        if cut:
            emit("truncated", sha, str(len(message)))

        # changed files relative to first parent (empty tree for roots)
        for line in git(repo, "diff-tree", "-r", "--root", "--no-commit-id",
                        "--name-status", "-M", sha).splitlines():
            parts = line.split("\t")
            status = parts[0]
            if status.startswith("R") and len(parts) == 3:
                emit("commit-rename", sha, mm2_string(parts[1]),
                     mm2_string(parts[2]))
            elif len(parts) == 2:
                emit("commit-change", sha, status[0], mm2_string(parts[1]))

        # full snapshot: every file in this commit's tree
        for line in git(repo, "ls-tree", "-r", sha).splitlines():
            meta, path = line.split("\t", 1)
            _mode, otype, bsha = meta.split()
            if otype == "blob":
                emit("commit-file", sha, mm2_string(path), bsha)

    # ----- trees ---------------------------------------------------------
    for sha in sorted(s for s, (t, _) in objects.items() if t == "tree"):
        emit("tree", sha)
        for line in git(repo, "ls-tree", sha).splitlines():
            meta, name = line.split("\t", 1)
            mode, otype, osha = meta.split()
            emit("tree-entry", sha, mm2_string(name), mode, otype, osha)

    # ----- blobs ---------------------------------------------------------
    for sha in sorted(s for s, (t, _) in objects.items() if t == "blob"):
        size = objects[sha][1]
        emit("blob", sha, str(size))
        content = git(repo, "cat-file", "blob", sha, binary=True)
        if b"\x00" in content[:8192]:
            emit("blob-binary", sha)
            continue
        text, cut = truncate(content, limit)
        emit("blob-text", sha, mm2_string(text))
        if cut:
            emit("truncated", sha, str(size))

    out_path.write_text("\n".join(facts) + "\n", encoding="utf-8")
    total = sum(counts.values())
    print(f"wrote {total} facts to {out_path}")
    for kind in sorted(counts):
        print(f"  {counts[kind]:6d}  {kind}")


if __name__ == "__main__":
    main()
