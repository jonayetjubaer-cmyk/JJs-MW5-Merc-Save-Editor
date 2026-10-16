"""Saved roster ordering for issue #42 preserves records and player slots."""
import unittest

from test_pilot_import import PilotHarness, _pilot_element
from ue_property import Writer, write_property_list


def roster(names="ABCDE", protected=(0, 2)):
    return PilotHarness([
        _pilot_element(name,
                       "EMechWarriorPlayerSlot::Player1" if i in protected
                       else "EMechWarriorPlayerSlot::None",
                       bytes([i + 1]) * 16)
        for i, name in enumerate(names)
    ])


def payload(element):
    writer = Writer()
    write_property_list(writer, element)
    return writer.bytes()


class PilotOrderTests(unittest.TestCase):
    def test_moves_skip_protected_slots_and_keep_every_record(self):
        save = roster()
        before = {p.persona_id: payload(p.element) for p in save.pilots()}
        self.assertEqual(save.move_pilot(4, -1), 3)
        self.assertEqual([p.callsign for p in save.pilots()], list("ABCED"))
        self.assertEqual(save.move_pilot(3, -1), 1)
        self.assertEqual([p.callsign for p in save.pilots()], list("AECBD"))
        self.assertEqual(save.roster.count, 5)
        self.assertEqual({p.persona_id: payload(p.element) for p in save.pilots()}, before)

    def test_top_bottom_and_boundaries(self):
        save = roster()
        self.assertEqual(save.move_pilot(4, -100), 1)
        self.assertEqual([p.callsign for p in save.pilots()], list("AECBD"))
        self.assertEqual(save.move_pilot(1, -1), 1)
        self.assertEqual(save.move_pilot(1, 100), 4)
        self.assertEqual([p.callsign for p in save.pilots()], list("ABCDE"))
        self.assertEqual(save.move_pilot(4, 1), 4)

    def test_protected_and_single_pilot_do_not_move(self):
        save = roster()
        self.assertEqual(save.move_pilot(0, 100), 0)
        self.assertEqual(save.move_pilot(2, -100), 2)
        self.assertEqual([p.callsign for p in save.pilots()], list("ABCDE"))
        self.assertEqual(roster("A", protected=()).move_pilot(0, 1), 0)
        self.assertEqual(roster("A").move_pilot(0, -1), 0)

    def test_invalid_permutations_leave_the_roster_unchanged(self):
        save = roster()
        elements = list(save.roster.elements)
        for order in ([0, 1], [0, 1, 2, 3, 3], [0, 1, 2, 3, 5],
                      [0, 1, 2, 3, -1], [0, True, 2, 3, 4],
                      [0, 1, 2, 3, 4.0], [1, 0, 2, 3, 4],
                      [0, 1, 3, 2, 4]):
            with self.subTest(order=order), self.assertRaises(ValueError):
                save.reorder_pilots(order)
            self.assertEqual(save.roster.elements, elements)

    def test_invalid_moves_and_empty_roster(self):
        save = roster()
        for index, offset in ((-1, 1), (5, -1), (True, 1), (1, 1.5)):
            with self.subTest(index=index, offset=offset), self.assertRaises(ValueError):
                save.move_pilot(index, offset)
        empty = roster("")
        empty.reorder_pilots([])
        self.assertEqual(empty.pilots(), [])
        with self.assertRaises(ValueError):
            empty.move_pilot(0, 1)


if __name__ == "__main__":
    unittest.main()
