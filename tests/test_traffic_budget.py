import unittest
from datetime import datetime
from commutebar.sources import TZ
from commutebar.traffic_budget import reservation

class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,9,14,15,30,tzinfo=TZ)
    def test_reserve_before_calls_and_duplicate_blocked(self):
        state=reservation({'used':0,'slots':[]},self.now)
        self.assertEqual(state['used'],3)
        self.assertIsNone(reservation(state,self.now))
    def test_monthly_cap(self):
        self.assertIsNone(reservation({'used':399,'slots':[]},self.now))
        self.assertEqual(reservation({'used':397,'slots':[]},self.now)['used'],400)
    def test_outside_slot_and_invalid_state(self):
        self.assertIsNone(reservation({'used':0,'slots':[]},self.now.replace(minute=31)))
        self.assertIsNone(reservation({'used':0,'slots':[]},self.now.replace(day=13)))
        with self.assertRaises(ValueError):reservation({},self.now)
