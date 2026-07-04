#!/usr/bin/env python3
"""Unit tests for bring_core.py. Run: python tests/test_bring_core.py"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "plugin", "scripts"))
import bring_core as B  # noqa: E402

TODAY = datetime.date(2026, 7, 1)  # a Wednesday

ACTIONS = """---
weekly_send_cap: 3
weekends_free: true
---

## Send the overdue reply
kind: send
due: 2026-07-02

## Decide: renew the lease
kind: decide
id: lease
due: 2026-06-30

## Ship the docs site
kind: ship
"""


def e(date, kind, id_=""):
    return {"date": date, "kind": kind, "id": id_}


class TestParse(unittest.TestCase):
    def test_frontmatter_and_actions(self):
        config, actions = B.parse_actions(ACTIONS)
        self.assertEqual(config["weekly_send_cap"], 3)
        self.assertTrue(config["weekends_free"])
        self.assertEqual(len(actions), 3)
        self.assertEqual(actions[0]["id"], "send-the-overdue-reply")  # slug default
        self.assertEqual(actions[1]["id"], "lease")                    # explicit id wins
        self.assertIsNone(actions[2]["due_date"])

    def test_garbage_is_tolerated(self):
        config, actions = B.parse_actions("no headings\njust: noise\n")
        self.assertEqual(actions, [])
        self.assertEqual(config["weekly_send_cap"], B.DEFAULT_SEND_CAP)


class TestQueue(unittest.TestCase):
    def setUp(self):
        _, self.actions = B.parse_actions(ACTIONS)

    def test_terminal_outcome_removes_action(self):
        opn = B.open_actions(self.actions, [e("2026-06-30", "decided", "lease")], TODAY)
        self.assertNotIn("lease", [a["id"] for a in opn])

    def test_skip_suppresses_today_only(self):
        skip = [e(TODAY.isoformat(), "skipped", "lease")]
        self.assertNotIn("lease", [a["id"] for a in B.open_actions(self.actions, skip, TODAY)])
        tomorrow = TODAY + datetime.timedelta(days=1)
        self.assertIn("lease", [a["id"] for a in B.open_actions(self.actions, skip, tomorrow)])

    def test_pick_orders_due_then_file_order(self):
        top, deck = B.pick(B.open_actions(self.actions, [], TODAY))
        self.assertEqual(top["id"], "lease")                 # due 6/30 beats 7/02
        self.assertEqual([d["id"] for d in deck],
                         ["send-the-overdue-reply", "ship-the-docs-site"])  # undated last


class TestScoring(unittest.TestCase):
    def test_week_counts_separate_streams(self):
        entries = [e("2026-06-29", "sent"), e("2026-06-30", "skipped"), e("2026-06-21", "sent")]
        c = B.week_counts(entries, TODAY)
        self.assertEqual((c["sent"], c["skipped"]), (1, 1))  # prior week excluded

    def test_streak_weekend_walk_and_skips_dont_count(self):
        entries = [e("2026-06-26", "sent"), e("2026-06-29", "sent"), e("2026-06-30", "shipped")]
        self.assertEqual(B.streak(entries, TODAY), 3)        # Fri + Mon + Tue, Wed open
        entries.append(e(TODAY.isoformat(), "skipped"))
        self.assertEqual(B.streak(entries, TODAY), 3)


class TestSurfaceParity(unittest.TestCase):
    def test_scoreboard_deterministic(self):
        config, actions = B.parse_actions(ACTIONS)
        entries = [e("2026-06-30", "sent", "x")]
        s1 = B.scoreboard_text(config, actions, entries, TODAY)
        s2 = B.scoreboard_text(config, actions, entries, TODAY)
        self.assertEqual(s1, s2)
        self.assertIn("Streak:", s1)
        self.assertIn("lease", s1)


if __name__ == "__main__":
    unittest.main()
