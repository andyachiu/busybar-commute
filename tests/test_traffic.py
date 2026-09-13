import unittest
from datetime import datetime
from unittest.mock import patch
from commutebar.traffic import enrich
from commutebar.hosted import priority
from commutebar.sources import TZ

CONFIG = dict(origin='Office', destination='Home', deadline='17:00', departure='16:15',
              earliest_departure='15:15', arrival_cushion_minutes=10,
              office_exit_minutes=5, heads_up_minutes=15, event_warning_minutes=15)

class TrafficTests(unittest.TestCase):
    @patch('commutebar.traffic.request', return_value='{"routes":[{"duration":"1200s"}]}')
    def test_bounded_requests_and_office_buffer(self, request):
        now=datetime(2026,9,14,15,30,tzinfo=TZ)
        result=enrich(dict(active=True,events=[],stale=False),CONFIG,now,'dummy')
        self.assertLessEqual(request.call_count,3)
        self.assertIn('4:40 PM',result['action'])
        self.assertEqual(result['traffic_departure'],now.replace(hour=16,minute=15).isoformat())

    @patch('commutebar.traffic.request', side_effect=TimeoutError())
    def test_failure_preserves_event_advice(self, request):
        result=enrich(dict(active=True,events=[],action='Leave early',front_action='GO 4:00'),
                      CONFIG,datetime(2026,9,14,16,tzinfo=TZ),'dummy')
        self.assertEqual(result['action'],'Leave early')
        self.assertNotIn('traffic_departure',result)

    def test_fresh_traffic_can_warn_without_an_event(self):
        now=datetime(2026,9,14,16,tzinfo=TZ)
        result=dict(active=True,events=[],stale=True,traffic_checked_at=now.isoformat(),
                    traffic_departure=now.replace(minute=10).isoformat())
        self.assertEqual(priority(result,CONFIG,now),100)
        self.assertEqual(priority(result,CONFIG,now.replace(minute=3)),50)
