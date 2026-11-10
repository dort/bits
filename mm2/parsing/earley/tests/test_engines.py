"""Engine tests against real MORK for the two MM2 Earley engines.

Every test runs the actual release binary on real fixture facts and reads the
dumped space. Recognition results are only trusted when the budget marker ran
(the base class enforces it) and, for any claim of non-acceptance, when the
semantic projection is stable across a doubled budget.
"""

from tests.support import (EngineCase, FOREST, RECOGNITION, fixture,
                           projection, render, run_engine, select)

X12 = ("demo", "s0")
GEXP_KEY = ("demo", "s0", "gexp")


class RecognitionTests(EngineCase):
    def test_expression_demo_accepts_with_thirteen_items(self):
        facts = self.converged(RECOGNITION,
                               [fixture("grammar_expr_demo.mm2"),
                                fixture("tokens_x_plus_12.mm2"),
                                "(parse demo s0 gexp)"],
                               16, [GEXP_KEY], self.RECOGNITION_HEADS)
        self.assertEqual(select(facts, "accepted"), {("accepted", "demo", "s0", "gexp")})
        self.assertEqual(len(select(facts, "item", "demo", "s0", "gexp")), 13)
        self.assertIn(("grm-spec", "gexp", "sha256",
                       "h8711aca694c020c03214bd2105a00212",
                       "h1864f95c644556d81121422f9281851d"), facts)

    def test_wrong_truncated_and_empty_streams_reject_after_closure(self):
        pieces = [fixture("grammar_expr_demo.mm2"), fixture("tokens_bad.mm2"),
                  "(parse bad w0 gexp)", "(parse bad tr gexp)", "(parse bad e0 gexp)"]
        keys = [("bad", stream, "gexp") for stream in ("w0", "tr", "e0")]
        facts = self.converged(RECOGNITION, pieces, 16, keys, self.RECOGNITION_HEADS)
        self.assertEqual(select(facts, "accepted"), set())

    def test_unproductive_recursion_is_stable_nonacceptance(self):
        pieces = [fixture("grammar_alternatives.mm2"), fixture("tokens_ints.mm2"),
                  "(parse ints n1 gbad)"]
        facts = self.converged(RECOGNITION, pieces, 8,
                               [("ints", "n1", "gbad")], self.RECOGNITION_HEADS)
        self.assertEqual(select(facts, "accepted"), set())
        self.assertEqual(select(facts, "item", "ints", "n1", "gbad"),
                         {("item", "ints", "n1", "gbad", "0", "self", "0", "0")})

    def test_unit_chain_budget_exhaustion_is_not_rejection(self):
        pieces = [fixture("grammar_chain31.mm2"), fixture("tokens_ints.mm2"),
                  "(parse ints n1 gchn)"]
        key = ("ints", "n1", "gchn")
        heads = self.RECOGNITION_HEADS
        at12 = self.run_complete(RECOGNITION, pieces, 12)
        at24 = self.run_complete(RECOGNITION, pieces, 24)
        self.assertEqual(select(at12, "accepted"), set())
        self.assertEqual(select(at24, "accepted"), set())
        self.assertNotEqual(projection(at12, *key, heads), projection(at24, *key, heads),
                            "still growing: exhaustion must be distinguishable "
                            "from stable non-acceptance")
        converged = self.converged(RECOGNITION, pieces, 64, [key], heads)
        self.assertEqual(select(converged, "accepted"), {("accepted", "ints", "n1", "gchn")})
        self.assertEqual(len(select(converged, "item", "ints", "n1", "gchn")), 62)

    def test_two_streams_and_two_grammars_stay_isolated(self):
        pieces = [fixture("grammar_expr_demo.mm2"), fixture("grammar_term_only.mm2"),
                  fixture("tokens_x_plus_12.mm2"), fixture("tokens_ints.mm2"),
                  "(parse demo s0 gexp)", "(parse demo s0 gterm)",
                  "(parse ints n1 gterm)"]
        keys = [GEXP_KEY, ("demo", "s0", "gterm"), ("ints", "n1", "gterm")]
        facts = self.converged(RECOGNITION, pieces, 16, keys, self.RECOGNITION_HEADS)
        self.assertEqual(select(facts, "accepted"),
                         {("accepted", "demo", "s0", "gexp"),
                          ("accepted", "ints", "n1", "gterm")})
        for item in select(facts, "item", "demo", "s0", "gterm"):
            self.assertIn(item[5], {"lifb", "numb"},
                          f"foreign production inside grammar gterm items: {item}")

    def test_short_step_limit_cannot_satisfy_the_marker(self):
        pieces = [fixture("grammar_expr_demo.mm2"), fixture("tokens_x_plus_12.mm2"),
                  "(parse demo s0 gexp)"]
        facts = run_engine(RECOGNITION, pieces, 16, steps=5)
        self.assertEqual(select(facts, "swept"), set(),
                         "a cut-short run must not carry the completion marker")
        complete = run_engine(RECOGNITION, pieces, 16)
        self.assertEqual(select(complete, "swept"), {("swept", "b016")})


class ForestTests(EngineCase):
    def expected_precedence_parts(self):
        completed = [
            "(part remy e0 gpre int 1 0 0 1 (t INT))",
            "(part remy e0 gpre int 1 2 2 3 (t INT))",
            "(part remy e0 gpre int 1 4 4 5 (t INT))",
            "(part remy e0 gpre int 1 6 6 7 (t INT))",
            "(part remy e0 gpre lifa 1 0 0 1 (nt atom int))",
            "(part remy e0 gpre lifa 1 2 2 3 (nt atom int))",
            "(part remy e0 gpre lifa 1 6 6 7 (nt atom int))",
            "(part remy e0 gpre lift 1 0 0 1 (nt term lifa))",
            "(part remy e0 gpre mul 3 2 4 5 (nt atom int))",
            "(part remy e0 gpre sum 3 0 2 3 (nt term lifa))",
            "(part remy e0 gpre sum 3 0 2 5 (nt term mul))",
            "(part remy e0 gpre sum 3 0 6 7 (nt term lifa))",
        ]
        return set(completed)

    def test_remy_expression_has_the_precedence_derivation(self):
        pieces = [fixture("grammar_precedence.mm2"),
                  fixture("tokens_remy_expression.mm2"), "(parse remy e0 gpre)"]
        key = ("remy", "e0", "gpre")
        facts = self.converged(FOREST, pieces, 32, [key], self.FOREST_HEADS)
        self.assertEqual(select(facts, "accepted"), {("accepted", "remy", "e0", "gpre")})
        self.assertEqual(len(select(facts, "item", *key)), 35)
        self.assertEqual(len(select(facts, "node", *key)), 12)
        self.assertEqual(len(select(facts, "part", *key)), 23)
        self.assertIn(("node", "remy", "e0", "gpre", "expr", "0", "7"), facts)
        lengths = {"sum": "3", "lift": "1", "mul": "3", "lifa": "1", "int": "1"}
        completed = {render(part) for part in select(facts, "part", *key)
                     if part[5] == lengths[part[4]]}
        # The unique derivation of "4 + 57 * 6 + 7": expr(0,7) = expr(0,5) +
        # term(6,7); expr(0,5) = expr(0,1) + term(2,5); term(2,5) =
        # term(2,3) * atom(4,5) -- the oracle (+ (+ 4 (* 57 6)) 7).
        self.assertEqual(completed, self.expected_precedence_parts())

    def test_concatenation_part_counts_match_boundary_triples(self):
        for stream, tokens in (("n3", 3), ("n8", 8)):
            with self.subTest(stream=stream):
                pieces = [fixture("grammar_concat.mm2"), fixture("tokens_ints.mm2"),
                          f"(parse ints {stream} gcat)"]
                key = ("ints", stream, "gcat")
                facts = self.converged(FOREST, pieces, 32, [key], self.FOREST_HEADS)
                self.assertEqual(select(facts, "accepted"),
                                 {("accepted", "ints", stream, "gcat")})
                boundaries = tokens + 1
                triples = (boundaries * (boundaries - 1) * (boundaries - 2)) // 6
                dot2 = select(facts, "part", "ints", stream, "gcat", "cat", "2")
                self.assertEqual(len(dot2), triples)

    def test_unit_cycles_stay_finite_and_explicit(self):
        pieces = [fixture("grammar_cycles.mm2"), fixture("tokens_ints.mm2"),
                  "(parse ints n1 gcyd)", "(parse ints n1 gcyi)"]
        keys = [("ints", "n1", "gcyd"), ("ints", "n1", "gcyi")]
        facts = self.converged(FOREST, pieces, 16, keys, self.FOREST_HEADS)
        self.assertEqual(select(facts, "accepted"),
                         {("accepted", "ints", "n1", "gcyd"),
                          ("accepted", "ints", "n1", "gcyi")})
        direct = select(facts, "part", "ints", "n1", "gcyd", "loop")
        self.assertEqual(direct, {
            ("part", "ints", "n1", "gcyd", "loop", "1", "0", "0", "1",
             ("nt", "expr", "inte")),
            ("part", "ints", "n1", "gcyd", "loop", "1", "0", "0", "1",
             ("nt", "expr", "loop")),
        })
        self.assertIn(("part", "ints", "n1", "gcyi", "fwd", "1", "0", "0", "1",
                       ("nt", "bbb", "bwd")), facts)
        self.assertIn(("part", "ints", "n1", "gcyi", "bwd", "1", "0", "0", "1",
                       ("nt", "aaa", "fwd")), facts)

    def test_alternative_identity_and_merged_start_root(self):
        pieces = [fixture("grammar_alternatives.mm2"), fixture("tokens_ints.mm2"),
                  "(parse ints n1 gsib)", "(parse ints n2 gpar)",
                  "(parse ints n1 gsta)"]
        keys = [("ints", "n1", "gsib"), ("ints", "n2", "gpar"), ("ints", "n1", "gsta")]
        facts = self.converged(FOREST, pieces, 16, keys, self.FOREST_HEADS)
        # Identically shaped siblings: two parts sharing all five positional
        # coordinates, kept apart only by the child descriptor.
        self.assertEqual(select(facts, "part", "ints", "n1", "gsib", "root"), {
            ("part", "ints", "n1", "gsib", "root", "1", "0", "0", "1",
             ("nt", "atom", "aone")),
            ("part", "ints", "n1", "gsib", "root", "1", "0", "0", "1",
             ("nt", "atom", "atwo")),
        })
        # Two independently ambiguous child positions: two alternatives at
        # each dot of the pair production, four parent parts in all.
        pair = select(facts, "part", "ints", "n2", "gpar", "pair")
        self.assertEqual(len(pair), 4)
        for dot, m, p in (("1", "0", "1"), ("2", "1", "2")):
            alternatives = {part for part in pair if part[5] == dot}
            self.assertEqual(alternatives, {
                ("part", "ints", "n2", "gpar", "pair", dot, "0", m, p,
                 ("nt", "atom", "pone")),
                ("part", "ints", "n2", "gpar", "pair", dot, "0", m, p,
                 ("nt", "atom", "ptwo")),
            })
        # Two accepting start productions: one root node, two alternatives.
        self.assertEqual(select(facts, "node", "ints", "n1", "gsta"),
                         {("node", "ints", "n1", "gsta", "tts", "0", "1")})
        self.assertEqual(select(facts, "part", "ints", "n1", "gsta"), {
            ("part", "ints", "n1", "gsta", "frst", "1", "0", "0", "1", ("t", "INT")),
            ("part", "ints", "n1", "gsta", "scnd", "1", "0", "0", "1", ("t", "INT")),
        })


class EngineParityTests(EngineCase):
    CASES = [
        ("expression", [fixture("grammar_expr_demo.mm2"),
                        fixture("tokens_x_plus_12.mm2"), "(parse demo s0 gexp)"],
         16, GEXP_KEY),
        ("concatenation", [fixture("grammar_concat.mm2"), fixture("tokens_ints.mm2"),
                           "(parse ints n3 gcat)"], 16, ("ints", "n3", "gcat")),
        ("precedence", [fixture("grammar_precedence.mm2"),
                        fixture("tokens_remy_expression.mm2"),
                        "(parse remy e0 gpre)"], 32, ("remy", "e0", "gpre")),
    ]

    def test_engines_agree_on_items_and_acceptance(self):
        for name, pieces, rounds, key in self.CASES:
            with self.subTest(case=name):
                plain = self.converged(RECOGNITION, pieces, rounds, [key],
                                       self.RECOGNITION_HEADS)
                forest = self.converged(FOREST, pieces, rounds, [key],
                                        self.FOREST_HEADS)
                self.assertEqual(projection(plain, *key, self.RECOGNITION_HEADS),
                                 projection(forest, *key, self.RECOGNITION_HEADS))
                self.assertEqual(select(plain, "node"), set())
                self.assertEqual(select(plain, "part"), set())
