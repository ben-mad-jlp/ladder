"""Error locations that `ladder repair` must recognise (round 8: a .tsx error matched nothing and repair silently
did nothing). Run: python3 -m unittest discover plugins/ladder/tool/tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import regen  # noqa: E402


class ErrorLocations(unittest.TestCase):
    def loc(self, line):
        m = regen.ERR_LOC.search(line)
        return (m.group(1), int(m.group(2))) if m else None

    def test_typescript_and_tsx(self):
        self.assertEqual(self.loc("src/features/alerts/MyAlertsScreen.tsx(43,29): error TS2322: Type ..."),
                         ("src/features/alerts/MyAlertsScreen.tsx", 43))
        self.assertEqual(self.loc("src/a/b.ts(7,1): error TS2554"), ("src/a/b.ts", 7))
        self.assertEqual(self.loc("src/App.jsx:12:5 - error"), ("src/App.jsx", 12))

    def test_csharp_python_go(self):
        self.assertEqual(self.loc("/x/Foo.cs(12,5): error CS0103: ..."), ("/x/Foo.cs", 12))
        self.assertEqual(self.loc('  File "app/main.py", line 7, in <module>'), ("app/main.py", 7))
        self.assertEqual(self.loc("pkg/server.go:31:2: undefined: x"), ("pkg/server.go", 31))

    def test_tsx_is_not_read_as_ts(self):
        # the old pattern stopped at ".ts" and then failed on the "x"
        self.assertEqual(self.loc("C.tsx(1,1): error")[0], "C.tsx")


if __name__ == "__main__":
    unittest.main()
