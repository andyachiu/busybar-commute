import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from commutebar.hosted import tick
from commutebar.details import event_details
from commutebar.sources import parse_mlb
from commutebar.device import payload
from commutebar.planner import plan
from test_commutebar import game, mlb, CONFIG, NOW, snapshot


class DetailsTests(unittest.TestCase):
    @patch('commutebar.hosted.request')
    def test_missing_animation_falls_back_but_priority_does_not(self, request):
        cache=Mock();cache.read.return_value=snapshot([self.parsed()])
        config={**CONFIG,'baseball_animation_verified':True}
        request.side_effect=[HTTPError('device',404,'missing',{},None), '{}']
        tick(config,cache,'dummy',NOW)
        self.assertEqual(request.call_count,2)
        self.assertEqual(request.call_args_list[0].args[1]['elements'][0]['type'],'animation')
        self.assertEqual(request.call_args_list[1].args[1]['elements'][0]['type'],'text')
        request.reset_mock();request.side_effect=HTTPError('device',409,'busy',{},None)
        with self.assertRaises(HTTPError):tick(config,cache,'dummy',NOW)
        self.assertEqual(request.call_count,1)
    def test_animation_keeps_text_and_matching_expiry(self):
        result=plan(snapshot([self.parsed()]),CONFIG,NOW)
        elements=payload(result,animation_path='baseball-background.anim')['elements']
        self.assertEqual(elements[0]['type'],'animation')
        self.assertTrue(all(e['timeout']==120 for e in elements))
        self.assertTrue(all(e['x']==18 for e in elements if e['type']=='text' and e['display']=='front'))
        self.assertTrue(any(e.get('text')=='GIANTS GAME' for e in elements))
    def parsed(self,state='Live',away=0,home=0):
        row=game(state='In Progress' if state=='Live' else state)
        row['status']['abstractGameState']=state
        row['teams']['away']['score']=away
        row['teams']['home']['score']=home
        row['linescore']={'currentInning':5,'inningState':'Top'}
        return parse_mlb(mlb([row]))[0]

    def test_zero_zero_live_is_real_score_but_pregame_is_not(self):
        self.assertEqual(self.parsed()['score'],dict(away=0,home=0))
        self.assertNotIn('score',self.parsed('Preview'))
        self.assertNotIn('score',self.parsed(away=None))

    def test_snapshot_time_inning_and_final(self):
        event=self.parsed(home=3,away=2)
        rows=event_details(event,NOW.isoformat())
        self.assertIn('Top 5',rows)
        self.assertIn('Score snapshot: Opponent 2 - Giants 3',rows)
        self.assertIn('Score checked 3:00 PM',rows)
        final=self.parsed('Final',2,3)
        self.assertNotIn('inning',final)
        self.assertIn('Final: Opponent 2 - Giants 3',event_details(final,NOW.isoformat()))

    def test_optional_and_stale_scores_never_show_numbers(self):
        event=self.parsed(home=12)
        for kwargs in ({'stale':True},{'show_scores':False}):
            self.assertNotIn('Giants 12',' '.join(event_details(event,NOW.isoformat(),**kwargs)))

    def test_device_explains_game_without_losing_action_or_expiry(self):
        event=self.parsed(home=3,away=2)
        result=plan(snapshot([event]),CONFIG,NOW)
        elements=payload(result)['elements']
        self.assertEqual(elements[1]['text'],'GIANTS GAME')
        back=[e['text'] for e in elements if e['display']=='back']
        self.assertEqual(len(back),8)
        self.assertIn(result['action'],back)
        self.assertTrue(any('First pitch' in t for t in back))
        self.assertTrue(any('Score checked' in t for t in back))
        self.assertTrue(all(e['timeout']==120 for e in elements))

    def test_score_cannot_change_departure_advice(self):
        first=plan(snapshot([self.parsed(home=0)]),CONFIG,NOW)
        second=plan(snapshot([self.parsed(home=12)]),CONFIG,NOW)
        self.assertEqual(first['action'],second['action'])
        self.assertEqual(first['front_action'],second['front_action'])
