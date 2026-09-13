import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
from commutebar.hosted import app, tick, priority
from commutebar.sources import TZ

CONFIG = dict(departure='16:15', deadline='17:00', arrival_cushion_minutes=10,
              earliest_departure='15:15', event_warning_minutes=15, heads_up_minutes=15,
              commute_weekdays=[0,1,2,3,4], monitor_start='14:30', cache_max_age_minutes=60)


class HostedTests(unittest.TestCase):
    @patch('commutebar.hosted.enrich')
    @patch('commutebar.hosted.request')
    def test_traffic_denied_reservation_never_calls_maps(self, request, enrich):
        now=datetime(2026,9,14,16,tzinfo=TZ)
        cache=Mock();cache.read.return_value=dict(fetched_at=now.isoformat(),events=[],sources=[])
        cache.reserve_traffic.return_value=False
        tick({**CONFIG,'traffic_enabled':True},cache,'dummy',now,traffic_key='dummy')
        enrich.assert_not_called()
        self.assertEqual(request.call_args.args[1]['elements'][0]['text'],'GO HOME')
        cache.reserve_traffic.side_effect=RuntimeError('counter unavailable')
        tick({**CONFIG,'traffic_enabled':True},cache,'dummy',now,traffic_key='dummy')
        enrich.assert_not_called()

    @patch('commutebar.hosted.enrich')
    def test_preview_never_spends_traffic_allowance(self,enrich):
        now=datetime(2026,9,14,16,tzinfo=TZ)
        cache=Mock();cache.read.return_value=dict(fetched_at=now.isoformat(),events=[],sources=[])
        tick({**CONFIG,'traffic_enabled':True},cache,'',now,dry_run=True,traffic_key='dummy')
        cache.reserve_traffic.assert_not_called();enrich.assert_not_called()

    @patch('commutebar.hosted.publish_native_snapshot', side_effect=RuntimeError('upload down'))
    @patch('commutebar.hosted.request')
    def test_native_cache_failure_never_suppresses_commute_alert(self, request, publish):
        now=datetime(2026,9,14,16,tzinfo=TZ)
        cache=Mock();cache.read.return_value=dict(fetched_at=now.isoformat(),events=[],sources=[])
        result=tick({**CONFIG,'native_snapshot_enabled':True},cache,'dummy',now)
        publish.assert_called_once()
        request.assert_called_once()
        self.assertEqual(result['native_snapshot'],'failed')
    def test_outside_hours_does_no_io(self):
        cache = Mock()
        self.assertEqual(tick(CONFIG, cache, '', datetime(2026,9,13,16,tzinfo=TZ))['status'], 'outside_window')
        cache.read.assert_not_called()

    def test_priority_escalates_only_near_departure(self):
        result = dict(active=True, stale=False, events=[dict(conflict=True)])
        self.assertEqual(priority(result, CONFIG, datetime(2026,9,14,14,30,tzinfo=TZ)),50)
        self.assertEqual(priority(result, CONFIG, datetime(2026,9,14,15,45,tzinfo=TZ)),100)
        result['stale'] = True
        self.assertEqual(priority(result, CONFIG, datetime(2026,9,14,16,tzinfo=TZ)),50)

    @patch('commutebar.hosted.request')
    @patch('commutebar.hosted.refresh')
    def test_cache_reused_and_cloud_auth(self, refresh, request):
        now=datetime(2026,9,14,16,tzinfo=TZ)
        snapshot=dict(fetched_at=now.isoformat(), events=[], sources=[])
        cache=Mock(); cache.read.return_value=snapshot
        result=tick(CONFIG,cache,'secret-test-token',now)
        refresh.assert_not_called()
        self.assertEqual(result['status'],'updated')
        self.assertEqual(request.call_args.args[0],'https://api.busy.app/busybar/display/draw')
        self.assertEqual(request.call_args.kwargs['headers'],{'Authorization':'Bearer secret-test-token'})
        self.assertTrue(all(e['timeout']==120 for e in request.call_args.args[1]['elements']))

    @patch('commutebar.hosted.request')
    @patch('commutebar.hosted.refresh')
    def test_dry_run_refreshes_missing_cache_without_draw(self, refresh, request):
        now=datetime(2026,9,14,16,tzinfo=TZ)
        cache=Mock();cache.read.return_value=None
        refresh.return_value=dict(fetched_at=now.isoformat(),events=[],sources=[])
        result=tick(CONFIG,cache,'',now,dry_run=True)
        cache.write.assert_called_once()
        request.assert_not_called()
        self.assertEqual(result['status'],'preview_only')

    def test_get_cannot_trigger_work(self):
        start=Mock()
        self.assertIn(b'not_found',app({'PATH_INFO':'/tick','REQUEST_METHOD':'GET'},start)[0])
        self.assertEqual(start.call_args.args[0],'404 Not Found')

    @patch('commutebar.hosted.Path.read_text',side_effect=RuntimeError('SECRET'))
    @patch.dict('os.environ',{'COMMUTE_CONFIG_FILE':'dummy'})
    def test_errors_do_not_expose_secrets(self, read):
        start=Mock()
        with patch('builtins.print') as log:
            body=app({'PATH_INFO':'/tick','REQUEST_METHOD':'POST'},start)
        self.assertEqual(start.call_args.args[0],'503 Service Unavailable')
        self.assertNotIn('SECRET',str(body)+str(log.call_args))
