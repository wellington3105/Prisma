"""Transcript review: apply the agent's corrections to the word-timed transcripts.

The transcriber hears fast and well and still writes "Delta" for "Deocar" or
"Um" for "Então,". After reading takes_packed.md the agent writes
<edit>/revisao.json; this helper turns it into REVISED copies of the
transcripts. The raw transcript is never touched.

    uv run python helpers/revise_transcript.py --edit-dir <edit>           # apply revisao.json
    uv run python helpers/revise_transcript.py --edit-dir <edit> --dry-run # report only
    uv run python helpers/revise_transcript.py --edit-dir <edit> --undo    # back to the raw text

revisao.json: keyed by transcript stem, phrases numbered as in takes_packed.md
(`#n` after the [start-end] range):

    {"<stem>": {
        "fix":   [{"n": 3, "text": "the phrase as it should read"}],
        "drop":  [{"n": 7, "why": "up to 6 words"}],
        "terms": {"Delta": "Deocar"}}}

Portuguese keys work too: corrigir / remover / termos (and texto / motivo).

  fix    TEXT in, TIME out. The corrected phrase is aligned to the phrase's
         timed words by longest common subsequence on normalized tokens (no
         case, no accents, no punctuation). Same word keeps its time; a
         replaced word takes the time of the word it replaces; an inserted word
         gets a time interpolated between its neighbours; a word left out
         disappears from the revised text. Nothing ever leaves the phrase's
         own [start, end] span.
  terms  global, case-preserving replacements over every word (brand names,
         glossary). A key may be several words ("Tem Real" -> "Tempo Real").
         Words already set by a `fix` are final and are not touched.
  drop   the phrase is NOT deleted: its words get `drop: true` + `drop_why`, and
         the revised file lists them under revision.drop with their time
         ranges. EDL builders read them with drop_ranges(). takes_packed.md
         shows them as `DROP`.

Output: <edit>/transcripts/.revised/<stem>.json (same shape as the raw file plus
a `revision` block). pack_transcripts.py, captions_for_remotion.py and
captions_srt.py prefer it automatically (`--raw` opts out). Every run starts
from the raw file, so revisao.json can be rewritten and re-applied freely, and
a stem that left revisao.json loses its revised copy.
"""
from __future__ import annotations

# Windows consoles default to cp1252; force UTF-8 so a status line never kills a run.
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import argparse
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

REVISED_DIRNAME = ".revised"      # dot-dir: `transcripts/*.json` globs never see it
INSERTED_WORD_S = 0.12
REWRITE_COVERAGE_MIN = 0.5


# --------------------------------------------------------------------------- #
# Lookup used by the readers (pack / captions / srt)
# --------------------------------------------------------------------------- #

def revised_path(raw: Path) -> Path:
    return raw.parent / REVISED_DIRNAME / raw.name


def resolve_transcript(raw: Path, use_revised: bool = True) -> Path:
    """The revised copy of `raw` when there is a fresh one, else `raw` itself."""
    raw = Path(raw)
    if not use_revised:
        return raw
    rev = revised_path(raw)
    if not rev.is_file():
        return raw
    if raw.is_file() and raw.stat().st_mtime > rev.stat().st_mtime + 1:
        print(f"warning: {raw.name} is newer than its revised copy; using the raw text "
              f"(re-run revise_transcript.py)", file=sys.stderr)
        return raw
    return rev


def drop_ranges(transcript: Path) -> list[dict]:
    """[{n, start, end, why}] of the phrases marked to cut (revised copy only).
    `transcript` may be the raw path or the revised one."""
    p = Path(transcript)
    rev = p if p.parent.name == REVISED_DIRNAME else revised_path(p)
    if not rev.is_file():
        return []
    return list(json.loads(rev.read_text(encoding="utf-8")).get("revision", {}).get("drop", []))


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #

def norm(text: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFD", (text or "").lower())
                    if unicodedata.category(c) != "Mn")
    return "".join(re.findall(r"[a-z0-9]+", plain))


def tokens_of(text: str) -> list[str]:
    """Whitespace tokens; a lone punctuation mark sticks to the word before it."""
    out: list[str] = []
    for raw in text.split():
        if not norm(raw) and out:
            out[-1] += raw
        elif norm(raw):
            out.append(raw)
    return out


def lcs_pairs(a: list[str], b: list[str]) -> list[tuple[int, int]]:
    """Index pairs of a longest common subsequence. Backtracking from the end
    makes a repeated stretch match its LAST occurrence (the retake)."""
    n, m = len(a), len(b)
    t = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n):
        for j in range(m):
            t[i + 1][j + 1] = t[i][j] + 1 if a[i] == b[j] else max(t[i][j + 1], t[i + 1][j])
    pairs: list[tuple[int, int]] = []
    i, j = n, m
    while i > 0 and j > 0:
        if a[i - 1] == b[j - 1]:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif t[i - 1][j] >= t[i][j - 1]:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def align_phrase(orig: list[dict], text: str, span: tuple[float, float]) -> tuple[list[dict], dict]:
    """Re-time `text` over the timed words `orig` of one phrase. Returns
    (new words, stats). Every time stays inside `span`."""
    lo, hi = span
    toks = tokens_of(text)
    no = [norm(w.get("text", "")) for w in orig]
    nt = [norm(t) for t in toks]
    pairs = lcs_pairs(no, nt)
    stats = {"kept": len(pairs), "swapped": 0, "inserted": 0, "removed": 0,
             "coverage": (len(pairs) / len(nt)) if nt else 1.0}
    out: list[dict] = []

    def gap(i0: int, i1: int, j0: int, j1: int) -> None:
        k, q = i1 - i0, j1 - j0
        swaps = min(k, q)
        stats["removed"] += k - swaps
        for x in range(swaps):                         # replaced: inherit the old time
            w = dict(orig[i0 + x])
            w["heard"] = w.get("text", "")
            w["text"] = toks[j0 + x]
            out.append(w)
            stats["swapped"] += 1
        ins = q - swaps
        if ins:                                        # inserted: interpolate between neighbours
            before = out[-1]["end"] if out else lo
            after = orig[i1]["start"] if i1 < len(orig) else hi
            room = after - before
            step = room / ins if room > 0 else 0.0
            width = min(INSERTED_WORD_S, step) if step > 0 else 0.04
            proto = orig[min(i0 + swaps, len(orig) - 1)] if orig else {}
            for x in range(ins):
                start = min(max(lo, before + x * step), max(lo, hi - 0.01))
                end = min(hi, start + width)
                out.append({"text": toks[j0 + swaps + x], "start": round(start, 3),
                            "end": round(max(end, start), 3), "type": "word",
                            "speaker_id": proto.get("speaker_id", "speaker_0"),
                            "inserted": True})
                stats["inserted"] += 1

    pi = pj = 0
    for io, jt in pairs:
        gap(pi, io, pj, jt)
        w = dict(orig[io])
        if w.get("text", "") != toks[jt]:              # same word, spelling/punctuation differs
            w["heard"] = w.get("text", "")
            w["text"] = toks[jt]
            stats["swapped"] += 1
        out.append(w)
        pi, pj = io + 1, jt + 1
    gap(pi, len(orig), pj, len(nt))
    for w in out:
        w["revised"] = "fix"
    return out, stats


def split_punct(token: str) -> tuple[str, str, str]:
    m = re.match(r"^([^\w]*)(.*?)([^\w]*)$", token, re.S)
    return m.group(1), m.group(2), m.group(3)


def cased(orig_core: str, repl: str) -> str:
    """Give `repl` the casing pattern of the word it replaces; brand casing
    (a capital after the first letter, e.g. ChatGPT) is kept as typed."""
    if len(orig_core) > 1 and orig_core.isupper():
        return repl.upper()
    if any(c.isupper() for c in repl[1:]):
        return repl
    if orig_core[:1].isupper():
        return repl[:1].upper() + repl[1:]
    if orig_core[:1].islower():
        return repl[:1].lower() + repl[1:]
    return repl


def apply_terms(words: list[dict], terms: dict[str, str]) -> list[dict]:
    """Replace terms over the word-type items of `words` (in place). Spacing
    items between words are skipped when matching, so a multi-word key still
    matches. Returns [{t, before, after}]."""
    found: list[dict] = []
    keys = [(k, [norm(x) for x in k.split() if norm(x)]) for k in terms]
    keys = sorted([(k, nk) for k, nk in keys if nk], key=lambda kv: -len(kv[1]))
    pos = [i for i, w in enumerate(words)
           if w.get("type", "word") == "word" and norm(w.get("text", ""))]
    splices: list[tuple[int, int, list[dict]]] = []
    p = 0
    while p < len(pos):
        hit = None
        for key, nk in keys:
            span = pos[p:p + len(nk)]
            if len(span) == len(nk) and all(
                    norm(words[i]["text"]) == nk[x] and words[i].get("revised") != "fix"
                    for x, i in enumerate(span)):
                hit = (key, span)
                break
        if not hit:
            p += 1
            continue
        key, span = hit
        rt = terms[key].split()
        olds = [words[i] for i in span]
        before = " ".join(w["text"] for w in olds)
        if len(rt) == len(olds):
            for w, r in zip(olds, rt):
                pre, core, post = split_punct(w["text"])
                rp, rcore, rpost = split_punct(r)
                w["heard"] = w["text"]
                w["text"] = (rp or pre) + cased(core, rcore) + (rpost or post)
                w["revised"] = "term"
            after = " ".join(w["text"] for w in olds)
        else:                                           # word count changes: spread over the old span
            t0, t1 = olds[0]["start"], olds[-1]["end"]
            pre = split_punct(olds[0]["text"])[0]
            core0 = split_punct(olds[0]["text"])[1]
            post = split_punct(olds[-1]["text"])[2]
            step = (t1 - t0) / len(rt)
            new = []
            for x, r in enumerate(rt):
                rp, rcore, rpost = split_punct(r)
                txt = ((rp or pre) if x == 0 else rp) + (cased(core0, rcore) if x == 0 else rcore) \
                    + (rpost or (post if x == len(rt) - 1 else ""))
                new.append({**olds[0], "text": txt, "start": round(t0 + x * step, 3),
                            "end": round(t0 + (x + 1) * step, 3), "revised": "term",
                            "heard": before if x == 0 else ""})
            splices.append((span[0], span[-1], new))
            after = " ".join(w["text"] for w in new)
        found.append({"t": round(olds[0]["start"], 2), "before": before, "after": after})
        p += len(span)
    for a, b, new in sorted(splices, key=lambda s: -s[0]):
        words[a:b + 1] = new
    return found


# --------------------------------------------------------------------------- #
# Per-transcript application
# --------------------------------------------------------------------------- #

def pick(d: dict, *names, default=None):
    for n in names:
        if n in d:
            return d[n]
    return default


def revise_one(raw_path: Path, entry: dict, silence: float) -> tuple[dict | None, dict]:
    """Returns (revised document or None when nothing changed, report)."""
    from pack_transcripts import group_into_phrases

    data = json.loads(raw_path.read_text(encoding="utf-8"))
    words: list[dict] = [dict(w) for w in data.get("words", [])]
    phrases = group_into_phrases(words, silence)
    rep: dict = {"stem": raw_path.stem, "phrases": len(phrases), "fix": [], "drop": [],
                 "terms": [], "errors": [], "warnings": []}

    fixes = pick(entry, "fix", "corrigir", default=[]) or []
    drops = pick(entry, "drop", "remover", default=[]) or []
    terms = pick(entry, "terms", "termos", default={}) or {}

    def phrase_of(item: dict, what: str) -> tuple[int, dict] | None:
        try:
            n = int(item.get("n"))
        except (TypeError, ValueError):
            rep["errors"].append(f"{what}: missing/invalid n in {item}")
            return None
        if not 1 <= n <= len(phrases):
            rep["errors"].append(f"{what} #{n}: phrase does not exist ({len(phrases)} phrases)")
            return None
        return n, phrases[n - 1]

    todo = []
    for it in fixes:
        r = phrase_of(it, "fix")
        txt = pick(it, "text", "texto")
        if r and isinstance(txt, str) and txt.strip():
            todo.append((r[0], r[1], txt.strip()))
        elif r:
            rep["errors"].append(f"fix #{r[0]}: empty text")
    seen: set[int] = set()
    for n, ph, txt in sorted(todo, key=lambda x: -x[0]):   # last phrase first: earlier indices stay valid
        if n in seen:
            rep["errors"].append(f"fix #{n}: given twice, only one is used")
            continue
        seen.add(n)
        if " ".join(txt.split()) == " ".join(ph["text"].split()):
            continue                                       # already reads that way
        idx = ph["word_idx"]
        orig = [words[i] for i in idx if (words[i].get("text") or "").strip()]
        span = (ph["start"], ph["end"])
        new, st = align_phrase(orig, txt, span)
        if st["coverage"] < REWRITE_COVERAGE_MIN:
            rep["warnings"].append(f"fix #{n}: only {st['coverage']:.0%} of the new text matches the "
                                   f"spoken words (a rewrite?); times are approximate")
        words[idx[0]:idx[-1] + 1] = new
        rep["fix"].append({"n": n, "start": span[0], "end": span[1], "before": ph["text"],
                           "after": " ".join(w["text"] for w in new),
                           **{k: st[k] for k in ("kept", "swapped", "inserted", "removed")}})
    rep["fix"].sort(key=lambda x: x["n"])

    if terms:
        rep["terms"] = apply_terms(words, {str(k): str(v) for k, v in terms.items()})

    # Numbering comes from the RAW grouping; regrouping the revised words gives
    # the same boundaries (edits stay inside their phrase), so drops land right.
    regrouped = group_into_phrases(words, silence)
    if len(regrouped) != len(phrases):
        rep["errors"].append(f"revised text regroups into {len(regrouped)} phrases, raw has "
                             f"{len(phrases)}: drop numbering may be off")
    drop_list = []
    for it in drops:
        r = phrase_of(it, "drop")
        if not r or r[0] > len(regrouped):
            continue
        n = r[0]
        ph = regrouped[n - 1]
        why = str(pick(it, "why", "motivo", default="") or "").strip()
        for i in ph["word_idx"]:
            words[i]["drop"] = True
            if why:
                words[i]["drop_why"] = why
        d = {"n": n, "start": ph["start"], "end": ph["end"], "why": why}
        drop_list.append(d)
        rep["drop"].append({**d, "text": ph["text"]})
    drop_list.sort(key=lambda d: d["n"])
    rep["drop"].sort(key=lambda d: d["n"])

    if not (rep["fix"] or rep["terms"] or drop_list):
        return None, rep
    out = {k: v for k, v in data.items() if k != "words"}
    out["words"] = words
    out["revision"] = {
        "source": raw_path.name,
        "applied_at": datetime.now().isoformat(timespec="seconds"),
        "silence_threshold": silence,
        "fix": [{k: f[k] for k in ("n", "before", "after")} for f in rep["fix"]],
        "terms": {str(k): str(v) for k, v in terms.items()},
        "drop": drop_list,
    }
    return out, rep


def print_report(rep: dict) -> None:
    print(f"\n## {rep['stem']}  ({rep['phrases']} phrases)")
    for f in rep["fix"]:
        print(f"  fix #{f['n']} [{f['start']:.2f}-{f['end']:.2f}]  "
              f"(kept {f['kept']}, swapped {f['swapped']}, inserted {f['inserted']}, removed {f['removed']})")
        print(f"    - {f['before']}")
        print(f"    + {f['after']}")
    if rep["terms"]:
        by: dict[str, int] = {}
        for t in rep["terms"]:
            k = f"{t['before']} -> {t['after']}"
            by[k] = by.get(k, 0) + 1
        print("  terms: " + ", ".join(f"{k} x{v}" for k, v in by.items()))
        for t in rep["terms"][:12]:
            print(f"    @{t['t']:.2f}s  {t['before']} -> {t['after']}")
        if len(rep["terms"]) > 12:
            print(f"    ... +{len(rep['terms']) - 12} more")
    for d in rep["drop"]:
        print(f"  drop #{d['n']} [{d['start']:.2f}-{d['end']:.2f}] {d['why'] or '(no reason)'}: {d['text']}")
    for w in rep["warnings"]:
        print(f"  warning: {w}")
    for e in rep["errors"]:
        print(f"  ERROR: {e}")
    print(f"  = {len(rep['fix'])} fixed phrases, {len(rep['terms'])} term replacements, "
          f"{len(rep['drop'])} dropped phrases")


def main() -> None:
    ap = argparse.ArgumentParser(description="Apply revisao.json to the word-timed transcripts")
    ap.add_argument("--edit-dir", type=Path, required=True)
    ap.add_argument("--revisao", type=Path, default=None, help="default: <edit-dir>/revisao.json")
    ap.add_argument("--undo", action="store_true", help="delete the revised copies (raw was never touched)")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    ap.add_argument("--silence-threshold", type=float, default=0.5,
                    help="phrase break used for numbering; must match pack_transcripts.py (0.5)")
    args = ap.parse_args()

    edit = args.edit_dir.resolve()
    tdir = edit / "transcripts"
    rdir = tdir / REVISED_DIRNAME
    if args.undo:
        n = len(list(rdir.glob("*.json"))) if rdir.is_dir() else 0
        if rdir.is_dir():
            shutil.rmtree(rdir)
        print(f"undo: {n} revised transcript(s) removed; raw transcripts are as the transcriber wrote them")
        return

    rev_file = (args.revisao or edit / "revisao.json").resolve()
    if not rev_file.is_file():
        sys.exit(f"no review file at {rev_file}")
    review = json.loads(rev_file.read_text(encoding="utf-8"))
    if not isinstance(review, dict):
        sys.exit("revisao.json must be an object keyed by transcript stem")

    changed = errors = 0
    wanted: set[str] = set()
    for key, entry in review.items():
        stem = key[:-5] if key.endswith(".json") else key
        raw = tdir / f"{stem}.json"
        if not raw.is_file():
            print(f"\n## {stem}\n  ERROR: no transcript {raw}")
            errors += 1
            continue
        wanted.add(raw.name)
        doc, rep = revise_one(raw, entry or {}, args.silence_threshold)
        print_report(rep)
        errors += len(rep["errors"])
        target = rdir / raw.name
        if doc is None:
            if target.exists() and not args.dry_run:
                target.unlink()
            continue
        changed += 1
        if not args.dry_run:
            rdir.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    if rdir.is_dir() and not args.dry_run:
        for stale in rdir.glob("*.json"):
            if stale.name not in wanted:
                stale.unlink()
                print(f"\nremoved stale revised copy {stale.name} (not in revisao.json)")
    where = "dry-run, nothing written" if args.dry_run else str(rdir)
    print(f"\n{changed} revised transcript(s) -> {where}")
    if changed and not args.dry_run:
        print("next: pack_transcripts.py (reading view); captions_for_remotion.py / captions_srt.py "
              "use the revised text automatically (--raw opts out)")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
