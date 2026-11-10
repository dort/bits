import unittest

from tokenizer.model import advance_location


class LocationTests(unittest.TestCase):
    def test_every_piece_boundary_uses_original_right_context(self):
        text = "a\r\nb\rc\nd\t😀"
        positions = [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (3, 1),
                     (3, 2), (4, 1), (4, 2), (4, 3), (4, 4)]
        for start in range(len(text) + 1):
            for end in range(start, len(text) + 1):
                with self.subTest(start=start, end=end):
                    piece = text[start:end]
                    result = advance_location(piece, 0, len(piece), *positions[start],
                                              following=text[end:end + 1])
                    self.assertEqual(result, positions[end])

    def test_lone_cr_and_cr_before_lf_have_different_end_positions(self):
        self.assertEqual(advance_location("\r", 0, 1, 7, 4), (8, 1))
        self.assertEqual(advance_location("\r", 0, 1, 7, 4, following="\n"), (7, 5))
        self.assertEqual(advance_location("\n", 0, 1, 7, 5), (8, 1))
        self.assertEqual(advance_location("\r", 0, 1, 7, 4, following="x"), (8, 1))

    def test_internal_context_takes_precedence_over_following(self):
        self.assertEqual(advance_location("\r\n", 0, 1, 1, 1, following="x"), (1, 2))
        self.assertEqual(advance_location("\rx", 0, 1, 1, 1, following="\n"), (2, 1))
