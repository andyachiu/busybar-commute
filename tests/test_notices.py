import unittest
from datetime import datetime
from unittest.mock import Mock
from commutebar.notices import advance_notice
from commutebar.device import payload
from commutebar.hosted import tick
from commutebar.sources import TZ

class NoticeTests(unittest.TestCase):
    def setUp(self):
        self.config=dict(advance_notices=True,departure='16:15',earliest_departure='15:15',
                         event_warning_minutes=15,commute_weekdays=[0,1,2,3,4],monitor_start='09:00',deadline='17:00')
        self.now=datetime(2026,9,14,9,tzinfo=TZ)
        self.result=dict(display_priority=50,stale=False,missing=[],level='warning',front_action='TRY 4:00',
            action='Check traffic',target='4:50 PM',fetched_at=self.now.isoformat(),
            events=[dict(kind='baseball',title='Giants vs Dodgers',venue='Oracle Park',conflict=True,
                         start=self.now.replace(hour=18,minute=45).isoformat())])
    def test_event_start_and_provisional_leave_are_shown(self):
        r=advance_notice(self.result,self.config,self.now)
        p=payload(r)
        self.assertEqual(r['display_priority'],10)
        self.assertEqual(p['elements'][0]['text'],'GIANTS GAME')
        self.assertIn('6:45 PM',p['elements'][1]['text'])
        self.assertIn('4:00 PM',p['elements'][1]['text'])
        self.assertIn('Provisional',r['notice_basis'])
    def test_urgent_alert_keeps_go_home(self):
        r=advance_notice({**self.result,'display_priority':100},self.config,self.now.replace(hour=15,minute=45))
        self.assertNotIn('advance_notice',r)
        self.assertEqual(payload(r)['elements'][0]['text'],'GO HOME')
    def test_review_notice_does_not_hide_provisional_plan(self):
        r=advance_notice({**self.result,'missing':['Closure PDF'],
            'sources':[{'status':'review'}]},self.config,self.now)
        self.assertIn('Plan to leave',r['notice_departure'])
    def test_no_old_departure_plan_after_traffic_checks_begin(self):
        r=advance_notice(self.result,self.config,self.now.replace(hour=15,minute=16))
        self.assertNotIn('4:00',r['notice_departure'])
    def test_lunch_still_runs_during_advance_notice_hours(self):
        cache=Mock()
        self.assertEqual(tick(self.config,cache,'',self.now.replace(hour=11,minute=30),dry_run=True)['widget'],'lunch')
        cache.read.assert_not_called()
