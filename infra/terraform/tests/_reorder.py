#!/usr/bin/env python3
"""One-shot repair: reorder top-level defs in the negative-control module.

The module was assembled with several out-of-order insertions, which is valid
Python (definitions are resolved at call time) but makes the file hard to read.
This moves helpers above the tests and puts main() last. It is a formatting fix,
not a behaviour change: the same definitions, the same order of execution.
"""
import ast
import re
import sys

p = sys.argv[1]
src = open(p, encoding="utf-8").read()
lines = src.split("\n")

chunks, cur = [], []
for ln in lines:
    starts = re.match(r"^(def |class |@|#!/|[A-Z_][A-Z0-9_]* = )", ln)
    if starts and cur and not cur[-1].startswith((" ", "\t")):
        chunks.append("\n".join(cur).rstrip("\n"))
        cur = [ln]
    else:
        cur.append(ln)
chunks.append("\n".join(cur).rstrip("\n"))
chunks = [c for c in chunks if c.strip()]


def name_of(c):
    m = re.search(r"^(?:def|class) (\w+)", c, re.M)
    return m.group(1) if m else None


def chunk_key(c):
    n = name_of(c)
    if n:
        return n
    m = re.search(r"^([A-Z_][A-Z0-9_]*) = ", c, re.M)
    return m.group(1) if m else None


byname = {chunk_key(c): c for c in chunks if chunk_key(c)}
order = ["_rc", "base_plan", "find", "PASSED", "expect_clean", "expect_failure"]
tests = sorted(n for n in byname if n and n.startswith("test_"))
missing = [n for n in order + tests if n not in byname]
if missing:
    raise SystemExit(f"missing definitions: {missing}")

out = [chunks[0]]
for n in order:
    out.append(byname.pop(n))
for n in tests:
    out.append(byname.pop(n))

TAIL = '''

def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures: list[str] = []
    for t in tests:
        try:
            t()
        except AssertionError as exc:
            failures.append(f"{t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{t.__name__}: raised {exc!r}")
    total = len(tests)
    if failures:
        print(f"NEGATIVE CONTROLS FAILED ({len(failures)}/{total}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"NEGATIVE CONTROLS PASS ({total}/{total} tests, {PASSED} checker assertions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

out.append(TAIL.strip("\n"))
open(p, "w", encoding="utf-8").write("\n\n\n".join(out) + "\n")
ast.parse(open(p, encoding="utf-8").read())
print(f"REORDERED OK; {len(tests)} tests")
