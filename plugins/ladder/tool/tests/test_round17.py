"""Round 17 fix (fabshop permutations trial). Run: python3 -m unittest discover plugins/ladder/tool/tests
- a schema reference resolves an entity's own name before table names; a bare table name shared by several entities
  in one schema is reported as ambiguous instead of resolving to the first."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ladder_schema as S  # noqa: E402


def ent(name, table, schema, props):
    e = S.Entity(name=name, full_name=name, table=table, db_schema=schema, keys=[])
    for p in props:
        e.props[p] = S.Prop(name=p) if hasattr(S, "Prop") else p
    return e


class EntityResolution(unittest.TestCase):
    def setUp(self):
        self.schemas = {"qbs": {
            "Fabshop_BuilderDebugSaw": ent("Fabshop_BuilderDebugSaw", "Saw", "Fabshop.Builder.Debug", ["AssignedDivision"]),
            "Saw": ent("Saw", "Saw", "Station", ["Division", "Name"]),
            "Other_A": ent("Other_A", "Thing", "A", ["X"]),
            "Other_B": ent("Other_B", "Thing", "B", ["X"]),
        }}

    def resolve(self, text):
        ref = S.Ref(text, None, text.split(".")[0], text.split(".")[1] if "." in text else None, "mention")
        return S.resolve(ref, self.schemas)

    def test_entity_name_wins_over_a_table_name(self):
        _, e, member, problem = self.resolve("Saw.Division")
        self.assertIsNone(problem)
        self.assertEqual(e.name, "Saw")

    def test_ambiguous_bare_table_name_is_reported(self):
        _, e, _, problem = self.resolve("Thing.X")
        self.assertIsNone(e)
        self.assertIn("belongs to", problem)


if __name__ == "__main__":
    unittest.main()
