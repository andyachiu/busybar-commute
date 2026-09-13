import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from commutebar.sources import TZ, parse_mlb, parse_moscone, sfmta_health
from commutebar.planner import plan
from commutebar.traffic import enrich
from commutebar.view import render

CONFIG = dict(departure='16:15', deadline='17:00', earliest_departure='15:15',
              arrival_cushion_minutes=10, office_exit_minutes=5, heads_up_minutes=15,
              arrival_buffer_minutes=120, game_duration_minutes=180, exit_buffer_minutes=60,
              event_warning_minutes=15, cache_max_age_minutes=60, commute_weekdays=[0,1,2,3,4],
              origin='office', destination='home')
NOW = datetime(2026,9,14,15,0,tzinfo=TZ)

def game(home=137, state='Scheduled', tbd=False, pk=1):
    return dict(gamePk=pk, venue={'id':2395}, officialDate='2026-09-14',gameDate='2026-09-15T01:45:00Z',
                status=dict(detailedState=state,startTimeTBD=tbd),
                teams=dict(home={'team':{'id':home}},away={'team':{'name':'Opponent'}}))

def mlb(games):
    return {'totalGames':len(games),'dates':[{'games':games}]}

def snapshot(events=None):
    return dict(fetched_at=NOW.isoformat(),events=events or [],sources=[dict(name='Giants',status='ok',detail='Loaded',url='https://www.mlb.com/giants/schedule')])

class Sources(unittest.TestCase):
    def test_home_games_only_cancelled_excluded_doubleheaders_preserved(self):
        result=parse_mlb(mlb([game(home=119),game(state='Cancelled'),game(pk=2),game(pk=3)]))
        self.assertEqual([e['id'] for e in result],['mlb-2','mlb-3'])
    def test_timezone_and_tbd(self):
        events=parse_mlb(mlb([game(),game(tbd=True,pk=2)]))
        self.assertEqual(events[0]['start'],'2026-09-14T18:45:00-07:00')
        self.assertIsNone(events[1]['start'])
    def test_schema_failure(self):
        with self.assertRaises(ValueError): parse_mlb({})
    def test_moscone_local_dates_dedup(self):
        row=dict(nid='1',title='Conference',start='2026-09-14T00:00:00',end='2026-09-16T23:59:59')
        rows=parse_moscone([row,row]);self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['start'].endswith('-07:00'))
    def test_sfmta_age_is_not_success(self):
        result=sfmta_health('<time datetime="2026-07-25T12:00:00Z">',NOW)
        self.assertEqual(result['status'],'review')

class Planning(unittest.TestCase):
    def test_evening_game_warns(self):
        p=plan(snapshot(parse_mlb(mlb([game()]))),CONFIG,NOW)
        self.assertTrue(p['events'][0]['conflict'])
        self.assertIn('4:00 PM',p['action'])
        self.assertIn('precaution',p['action'])
    def test_past_advice_is_not_repeated(self):
        later=NOW.replace(hour=16,minute=5)
        data=snapshot(parse_mlb(mlb([game()])));data['fetched_at']=later.isoformat()
        self.assertNotIn('leaving at 4:00',plan(data,CONFIG,later)['action'])
    def test_stale_and_future_cache(self):
        for stamp in ['2026-09-13T15:00:00-07:00','2026-09-15T15:00:00-07:00']:
            data=snapshot();data['fetched_at']=stamp
            p=plan(data,CONFIG,NOW);self.assertTrue(p['stale']);self.assertIn('Refresh',p['title'])
    def test_weekend_quiet(self):
        sunday=NOW.replace(day=13)
        self.assertFalse(plan(snapshot(),CONFIG,sunday)['active'])
    def test_convention_middle_day(self):
        events=parse_moscone([dict(nid='1',title='Conference',start='2026-09-13T00:00:00',end='2026-09-15T23:59:59')])
        self.assertTrue(plan(snapshot(events),CONFIG,NOW)['events'][0]['conflict'])
    def test_after_deadline_quiet(self):
        self.assertFalse(plan(snapshot(),CONFIG,NOW.replace(hour=17))['active'])
    def test_no_clear_traffic_claim(self):
        self.assertIn('incomplete',plan(snapshot(),CONFIG,NOW)['action'])
    def test_html_escape(self):
        p=plan(snapshot(),CONFIG,NOW);p['action']='<script>alert(1)</script>'
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'index.html';render(p,file);html=file.read_text()
            self.assertNotIn('<script>alert(1)',html);self.assertIn('&lt;script&gt;',html)

class Traffic(unittest.TestCase):
    @patch('commutebar.traffic.request',return_value=json.dumps({'routes':[{'duration':'1800s'}]}))
    def test_exit_and_arrival_cushion(self,mock):
        p=enrich(plan(snapshot(),CONFIG,NOW),CONFIG,NOW,'test')
        self.assertIn('4:15 PM',p['action']);self.assertIn('4:50 PM',p['action'])
        self.assertEqual(mock.call_args.args[1]['travelMode'],'DRIVE')
    @patch('commutebar.traffic.request',return_value=json.dumps({'routes':[{'duration':'7200s'}]}))
    def test_impossible_deadline_warns(self,mock):
        p=enrich(plan(snapshot(),CONFIG,NOW),CONFIG,NOW,'test')
        self.assertEqual(p['title'],'Arrival deadline at risk')
    @patch('commutebar.traffic.request',side_effect=TimeoutError)
    def test_failure_retains_event_warning(self,mock):
        p=plan(snapshot(parse_mlb(mlb([game()]))),CONFIG,NOW)
        action=p['action'];enrich(p,CONFIG,NOW,'test')
        self.assertEqual(p['action'],action);self.assertIn('unavailable',p['mode'])

if __name__=='__main__': unittest.main()

class Device(unittest.TestCase):
    def test_payload_expires_and_is_ascii(self):
        from commutebar.device import payload
        p=plan(snapshot(),CONFIG,NOW)
        p['action']='Check traffic → now 🚗'
        body=payload(p)
        self.assertEqual(body['priority'],10)
        self.assertTrue(all(e['timeout']==120 for e in body['elements']))
        self.assertTrue(all(e['text'].isascii() for e in body['elements']))
    @patch('commutebar.device.request')
    def test_409_preserves_active_app(self,mock):
        from urllib.error import HTTPError
        from commutebar.device import send
        mock.side_effect=HTTPError('http://device',409,'Conflict',None,None)
        self.assertIn('preserved',send(plan(snapshot(),CONFIG,NOW)))
    @patch('commutebar.device.request')
    def test_quiet_hours_no_write(self,mock):
        from commutebar.device import send
        send(plan(snapshot(),CONFIG,NOW.replace(hour=9)))
        mock.assert_not_called()
