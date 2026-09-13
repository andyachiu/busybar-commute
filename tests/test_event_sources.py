import json
import unittest
from datetime import datetime
from commutebar.chase import parse_chase, fetch_chase, GATEWAY
from commutebar.advisories import parse_advisory, discover, date_envelope
from commutebar.planner import plan
from commutebar.sources import TZ
from test_commutebar import CONFIG, NOW, snapshot


def chase_row(**values):
    row=dict(uid='concert-20260914',eventType='cce',title='Arena concert',location='Chase Center, San Francisco',
             datetime='2026-09-15T01:00:00+0000',home=False,doorsOpenTime='2026-09-15T00:00:00+0000')
    row.update(values);return row


def advisory_html(driving='Driving', region='Financial District', body=None):
    return f'''<h1>Conference Traffic Changes: September 15-17, 2026</h1>
    <div class="field--name-field-transit-type-disrupted">{driving}</div>
    <div class="field--name-field-neighborhoods">{region}</div>
    <div class="field--name-body">{body or '<p>Howard restrictions from September 5 to September 20.</p>'}</div>'''


class Chase(unittest.TestCase):
    def test_local_time_home_filter_and_plaza_filter(self):
        rows=[chase_row(),chase_row(uid='road',eventType='gsw',home=False,location='away'),
              chase_row(uid='home',eventType='gsv',home=True,location='home'),
              chase_row(uid='yoga',eventType='lwn',location='Thrive City')]
        events=parse_chase({'data':rows,'hasMore':False})
        self.assertEqual(len(events),2)
        self.assertEqual(events[0]['date'],'2026-09-14')
        self.assertEqual(events[0]['start'],'2026-09-14T18:00:00-07:00')
    def test_cancelled_hidden_unknown_and_duplicates(self):
        rows=[chase_row(),chase_row(),chase_row(uid='cancelled',topFlagTextOverride='Cancelled'),
              chase_row(uid='hidden',hideFromCalendar=True),chase_row(uid='tbd',hideTime=True)]
        events=parse_chase({'data':rows,'hasMore':False})
        self.assertEqual(len(events),2);self.assertIsNone(events[1]['start'])
    def test_broken_feed_is_not_empty_success(self):
        with self.assertRaises(ValueError):parse_chase({'data':[]})
    def test_pagination_and_public_config_not_stored(self):
        calls=[]
        def loader(url,headers=None):
            calls.append(url)
            if url.endswith('/events/'):return '<script src="/_next/static/chunks/1421-abc.js"></script>'
            if url.endswith('.js'):return 'u2:()=>host,j5:()=>pub;host="'+GATEWAY+'",pub="public-test-value"'
            if 'page=1&' in url:return json.dumps({'data':[chase_row()],'hasMore':True})
            return json.dumps({'data':[chase_row(uid='second')],'hasMore':False})
        events=fetch_chase(NOW,loader)
        self.assertEqual(len(events),2);self.assertEqual(len(calls),4)
        self.assertNotIn('public-test-value',json.dumps(events))
    def test_doors_can_expand_arrival_window(self):
        rows=parse_chase({'data':[chase_row(datetime='2026-09-15T03:00:00+0000',doorsOpenTime='2026-09-14T23:00:00+0000')],'hasMore':False})
        self.assertTrue(plan(snapshot(rows),CONFIG,NOW)['events'][0]['conflict'])


class Advisories(unittest.TestCase):
    def test_closure_starts_before_conference(self):
        event=parse_advisory(advisory_html(), 'https://www.sfmta.com/travel-updates/conference')
        self.assertEqual(event['date'],'2026-09-05')
        self.assertTrue(event['end'].startswith('2026-09-20'))
        self.assertEqual(event['streets'],['Howard'])
        result=plan(snapshot([event]),CONFIG,NOW)
        self.assertEqual(result['front_action'],'CHECK ROUTE')
        self.assertNotIn('4:00 PM',result['action'])
    def test_transit_only_and_unrelated_regions_excluded(self):
        self.assertIsNone(parse_advisory(advisory_html(driving='Muni'), 'https://www.sfmta.com/a'))
        self.assertIsNone(parse_advisory(advisory_html(region='Richmond'), 'https://www.sfmta.com/b'))
    def test_dates_not_inferred_from_current_day(self):
        self.assertIsNone(date_envelope('Ongoing closure','Closure notice'))
        self.assertIsNone(date_envelope('December 31, 2026 to January 2, 2027','2026–2027 closure'))
    def test_index_dedup_and_pagination(self):
        html='<h1>Travel &amp; Transit Updates</h1><h3><a href="/travel-updates/a">A</a></h3><h3><a href="/travel-updates/a">A</a></h3><a title="Go to next page" href="?page=1">Next</a>'
        links,next_page=discover(html)
        self.assertEqual(len(links),1);self.assertTrue(next_page.endswith('?page=1'))
    def test_street_names_use_word_boundaries(self):
        event=parse_advisory(advisory_html(body='Parking changes September 15-17, 2026.'),'https://www.sfmta.com/a')
        self.assertNotIn('King',event['streets'])
    def test_stale_closure_is_not_current_advice(self):
        event=parse_advisory(advisory_html(),'https://www.sfmta.com/a')
        data=snapshot([event]);data['fetched_at']='2026-09-10T10:00:00-07:00'
        result=plan(data,CONFIG,NOW)
        self.assertEqual(result['front_action'],'CHECK DATA')

if __name__=='__main__':unittest.main()

class FailureBehavior(unittest.TestCase):
    def test_fresh_failed_source_does_not_show_no_events(self):
        data=snapshot();data['sources'][0]['status']='error'
        result=plan(data,CONFIG,NOW)
        self.assertEqual(result['front_action'],'CHECK DATA')
        self.assertIn('unavailable',result['title'])

class WatcherControls(unittest.TestCase):
    def test_second_watcher_refuses_and_preserves_owner_pid(self):
        import fcntl, tempfile, subprocess, sys
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'watch.lock'
            with path.open('w+') as owner:
                fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
                owner.write('12345');owner.flush()
                run=subprocess.run([sys.executable,'-m','commutebar','--watch','--data-dir',d],capture_output=True,text=True,timeout=5)
                self.assertEqual(run.returncode,2)
                self.assertIn('already monitoring',run.stderr)
                self.assertEqual(path.read_text(),'12345')
    def test_stop_without_watcher_is_noop(self):
        import tempfile, subprocess, sys
        with tempfile.TemporaryDirectory() as d:
            run=subprocess.run([sys.executable,'-m','commutebar','--stop','--data-dir',d],capture_output=True,text=True,timeout=5)
            self.assertEqual(run.returncode,0);self.assertIn('not running',run.stdout)
