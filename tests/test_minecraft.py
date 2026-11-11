"""Minecraft outcomes and permanent negative-only totem protection."""
import json
import unittest
from unittest.mock import patch

from test_horserace import PKG, ROOT, Settings, deal, event_main, make_race

PACK = json.loads((ROOT / "events" / "Minecraft.json").read_text(encoding="utf-8"))


class MinecraftTests(unittest.TestCase):
    def setUp(self):
        self.race = make_race(Settings(base_move_min=1, base_move_max=1, event_rate=0))
        self.race.round_add()
        self.horse = self.race.player[0]

    def trigger(self, index):
        return event_main(self.race, 0, deal(PACK[index]))

    def grant_totem(self):
        self.trigger(1)

    def test_enderman_win_probability_and_three_extra_steps(self):
        for draw in (0, 49):
            with self.subTest(draw=draw), patch(f"{PKG}.events_main.random.randint", return_value=draw) as rng:
                self.horse.location_add_move = 0
                result = self.trigger(0)
                rng.assert_called_once_with(0, 99)
            self.assertIn("末影珍珠", result)
            self.assertEqual(self.horse.location_add_move, 3)
        self.race.move()
        self.assertEqual(self.horse.location, 4)  # one base step plus three pearl steps

    def test_enderman_loss_stops_exactly_one_round(self):
        for draw in (50, 99):
            r = make_race(Settings(base_move_min=1, base_move_max=1))
            r.round_add()
            with patch(f"{PKG}.events_main.random.randint", return_value=draw):
                text = event_main(r, 0, deal(PACK[0]))
            self.assertIn("休整", text)
            r.move()
            self.assertEqual(r.player[0].location, 1)
            r.round_add()
            r.del_buff_overtime()
            r.move()
            self.assertEqual(r.player[0].location, 1)
            r.round_add()
            r.del_buff_overtime()
            r.move()
            self.assertEqual(r.player[0].location, 2)

    def test_girl_event_stops_exactly_one_round(self):
        self.trigger(3)
        self.race.move()
        self.race.round_add()
        self.race.del_buff_overtime()
        before = self.horse.location
        self.race.move()
        self.assertEqual(self.horse.location, before)
        self.race.round_add()
        self.race.del_buff_overtime()
        self.race.move()
        self.assertEqual(self.horse.location, before + 1)

    def test_raid_dies_immediately_and_leaves_next_round(self):
        self.horse.location = 19
        self.horse.location_add_move = 3
        self.trigger(2)
        self.assertTrue(self.horse.is_die())
        self.assertFalse(self.horse.is_away())
        self.race.move()
        self.assertEqual(self.horse.location, 19)
        self.assertNotIn("alice", self.race.is_win_all())
        self.assertEqual(self.trigger(0), "")
        self.race.round_add()
        self.assertTrue(self.horse.is_away())

    def test_away_always_starts_next_round_even_with_immediate_flag(self):
        event_main(self.race, 0, deal({"target": 0, "away": 1, "immediate": 1}))
        self.assertFalse(self.horse.is_away())
        self.race.move()
        self.assertEqual(self.horse.location, 1)
        self.race.round_add()
        self.assertTrue(self.horse.is_away())
        self.race.move()
        self.assertEqual(self.horse.location, 1)

    def test_totem_blocks_raid_and_stun(self):
        self.grant_totem()
        self.assertIn("抵挡", self.trigger(2))
        self.assertIn("抵挡", self.trigger(3))
        self.assertFalse(self.horse.is_die())
        self.assertFalse(self.horse.is_away())
        self.race.round_add()
        self.race.move()
        self.assertEqual(self.horse.location, 1)
        self.horse.fullname()
        self.assertIn("不死图腾", self.horse.horse_fullname)

    def test_totem_blocks_nested_loss_but_keeps_pearl_reward(self):
        self.grant_totem()
        with patch(f"{PKG}.events_main.random.randint", return_value=99):
            self.assertIn("抵挡", self.trigger(0))
        self.assertFalse(self.horse.find_buff("locate_lock"))
        with patch(f"{PKG}.events_main.random.randint", return_value=0):
            self.assertIn("末影珍珠", self.trigger(0))
        self.assertEqual(self.horse.location_add_move, 3)

    def test_totem_blocks_old_pack_negative_effects_but_keeps_rewards(self):
        self.grant_totem()
        self.horse.location = 10
        for effect in ({"die": 1}, {"away": 1}, {"move": -3}, {"track_to_location": 0}, {"rounds": 2, "vertigo": 1}, {"rounds": 2, "move_min": -3, "move_max": -1}):
            with self.subTest(effect=effect):
                text = event_main(self.race, 0, deal({"target": 0, **effect}))
                self.assertIn("抵挡", text)
        self.assertEqual(self.horse.location_add_move, 0)
        event_main(self.race, 0, deal({"target": 0, "move": 2, "rounds": 2, "move_min": 3, "move_max": 3}))
        self.race.round_add()
        self.race.move()
        # Pending event move belongs to the previous turn and is reset by round_add.
        self.assertEqual(self.horse.location, 14)

    def test_mixed_positive_and_negative_effects_keep_positive_parts(self):
        self.grant_totem()
        event_main(self.race, 0, deal({"target": 0, "die": 1, "move": 3, "rounds": 2, "move_min": 2, "move_max": 2, "locate_lock": 1}))
        self.assertEqual(self.horse.location_add_move, 3)
        self.assertFalse(self.horse.find_buff("locate_lock"))
        self.race.round_add()
        self.race.move()
        self.assertEqual(self.horse.location, 3)

    def test_acquisition_purifies_negative_buffs_and_preserves_positive(self):
        self.horse.add_buff("fast", 0, 20, [], 2, 2)
        self.horse.add_buff("stun", 0, 20, ["locate_lock"])
        self.horse.add_buff("mixed", 0, 20, ["vertigo"], 1, 3)
        # A delayed reward may arrive even while the recipient is stunned.
        event_main(self.race, 0, deal(PACK[1]), 1)
        self.assertEqual([b[0] for b in self.horse.buff], ["fast", "mixed"])
        self.assertFalse(self.horse.find_buff("vertigo"))
        self.assertEqual(self.trigger(1), "")  # do not repeatedly acquire the same totem

    def test_totem_protects_positive_buff_deletion_and_shortening(self):
        self.horse.add_buff("fast", 0, 20, ["good"], 2, 2)
        self.grant_totem()
        event_main(self.race, 0, deal({"target": 0, "del_buff": ["good"], "buff_time_add": -10}))
        self.assertEqual(self.horse.buff[0][2], 20)
        event_main(self.race, 0, deal({"target": 0, "buff_time_add": 5}))
        self.assertEqual(self.horse.buff[0][2], 25)

    def test_totem_blocks_backward_random_teleport_keeps_forward(self):
        self.grant_totem()
        self.horse.location = 5
        with patch(f"{PKG}.events_main.random.randint", return_value=2):
            event_main(self.race, 0, deal({"target": 0, "track_random_location": 1}))
        self.assertEqual(self.horse.location_add_move, 0)
        with patch(f"{PKG}.events_main.random.randint", return_value=9):
            event_main(self.race, 0, deal({"target": 0, "track_random_location": 1}))
        self.assertEqual(self.horse.location_add_move, 4)

    def test_swap_is_atomic_if_protected_horse_would_move_backwards(self):
        self.grant_totem()
        self.horse.location = 10
        self.race.player[1].location = 2
        text = event_main(self.race, 0, deal({"target": 1, "track_exchange_location": 1}))
        self.assertIn("抵挡", text)
        self.assertEqual([h.location_add_move for h in self.race.player], [0, 0])

    def test_group_attack_still_affects_unprotected_horse(self):
        self.grant_totem()
        event_main(self.race, 0, deal({"target": 2, "die": 1, "immediate": 1}))
        self.assertFalse(self.horse.is_die())
        self.assertTrue(self.race.player[1].is_die())

    def test_delayed_negative_event_is_blocked_at_execution(self):
        event_main(self.race, 0, deal({"target": 0, "delay_event": [2, {"target": 0, "die": 1}]}))
        self.grant_totem()
        self.race.round_add()
        self.race.round_add()
        text = self.race.event_start([])
        self.assertIn("抵挡", text)
        self.assertFalse(self.horse.find_buff("die"))

    def test_totem_survives_replacement_attempt_and_new_race_is_unprotected(self):
        self.grant_totem()
        text = event_main(self.race, 0, deal({"target": 0, "replace_horse": {"horsename": "other", "owner": "other"}}))
        self.assertIn("抵挡", text)
        self.assertTrue(self.horse.negative_immunity)
        self.assertEqual(self.horse.horse, "a")
        self.assertFalse(make_race().player[0].negative_immunity)


if __name__ == "__main__":
    unittest.main()
