import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from commutebar.widgets import lunch_payload
from commutebar.hosted import tick
from commutebar.sources import TZ
from test_hosted import CONFIG


class LunchTests(unittest.TestCase):
    def test_animation_layer_text_clearance_and_matching_expiry(self):
        now=datetime(2026,9,14,11,39,30,tzinfo=TZ)
        body=lunch_payload(now,'lunch-bowl-background.anim')
        self.assertEqual(body['elements'][0]['type'],'animation')
        self.assertTrue(body['elements'][0]['loop'])
        self.assertTrue(all(e['timeout']==30 for e in body['elements']))
        front=[e for e in body['elements'] if e['type']=='text' and e['display']=='front']
        self.assertTrue(all(e['x']==18 and e['width']==53 for e in front))
        self.assertEqual(body['priority'],20)

    @patch('commutebar.hosted.request')
    def test_unverified_animation_is_never_sent(self, request):
        tick(CONFIG,Mock(),'test',datetime(2026,9,14,11,30,tzinfo=TZ))
        self.assertTrue(all(e['type']=='text' for e in request.call_args.args[1]['elements']))

    @patch('commutebar.hosted.request')
    def test_missing_asset_falls_back_to_plain_text(self, request):
        request.side_effect=[HTTPError('https://api.busy.app',404,'missing',None,None),'ok']
        tick(dict(CONFIG,lunch_animation_verified=True),Mock(),'test',datetime(2026,9,14,11,30,tzinfo=TZ))
        self.assertEqual(request.call_count,2)
        self.assertTrue(all(e['type']=='text' for e in request.call_args.args[1]['elements']))

    @patch('commutebar.hosted.request')
    def test_animation_does_not_retry_over_priority_conflict(self, request):
        request.side_effect=HTTPError('https://api.busy.app',409,'busy',None,None)
        with self.assertRaises(HTTPError):
            tick(dict(CONFIG,lunch_animation_verified=True),Mock(),'test',datetime(2026,9,14,11,30,tzinfo=TZ))
        self.assertEqual(request.call_count,1)

    def test_window_weekdays_and_expiry(self):
        for day in range(14,19):
            base=datetime(2026,9,day,11,30,tzinfo=TZ)
            self.assertIsNotNone(lunch_payload(base))
            self.assertIsNone(lunch_payload(base.replace(minute=29)))
            self.assertIsNone(lunch_payload(base.replace(minute=40)))
            self.assertEqual(lunch_payload(base.replace(minute=39,second=30))['elements'][0]['timeout'],30)
        self.assertIsNone(lunch_payload(datetime(2026,9,19,11,30,tzinfo=TZ)))
        self.assertIsNone(lunch_payload(datetime(2026,9,20,11,30,tzinfo=TZ)))

    def test_timezone_tracks_daylight_saving(self):
        for stamp in ('2026-09-14T18:30:00+00:00','2026-12-14T19:30:00+00:00'):
            self.assertIsNotNone(lunch_payload(datetime.fromisoformat(stamp)))

    @patch('commutebar.hosted.request')
    def test_preview_has_no_network_or_cache_access(self, request):
        cache=Mock()
        result=tick(CONFIG,cache,'',datetime(2026,9,14,11,30,tzinfo=TZ),dry_run=True)
        self.assertEqual(result['widget'],'lunch')
        self.assertEqual(result['status'],'preview_only')
        cache.read.assert_not_called();request.assert_not_called()

    @patch('commutebar.hosted.request')
    def test_fixed_message_and_lower_priority(self, request):
        cache=Mock()
        tick(CONFIG,cache,'test',datetime(2026,9,14,11,30,tzinfo=TZ))
        body=request.call_args.args[1]
        self.assertEqual(body['priority'],20)
        self.assertIn("LET'S GO TO LUNCH",[e['text'] for e in body['elements']])
        self.assertTrue(all(e['timeout']<=120 for e in body['elements']))
        cache.read.assert_not_called()

    @patch('commutebar.hosted.request')
    def test_commute_takes_precedence_if_hours_overlap(self, request):
        now=datetime(2026,9,14,11,30,tzinfo=TZ)
        cache=Mock();cache.read.return_value=dict(fetched_at=now.isoformat(),events=[],sources=[])
        result=tick(dict(CONFIG,monitor_start='11:00'),cache,'',now,dry_run=True)
        self.assertNotIn('widget',result)
        self.assertGreater(result['priority'],20)
