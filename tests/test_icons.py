import unittest
from commutebar.icons import event_icon,animation_for

class IconTests(unittest.TestCase):
    def test_event_types(self):
        for event,expected in [(None,'car'),({'kind':'baseball'},'baseball'),
            ({'kind':'arena','event_type':'basketball'},'basketball'),
            ({'kind':'arena','title':'Warriors vs Lakers'},'basketball'),
            ({'kind':'arena','title':'Concert'},'event'),({'kind':'advisory'},'detour'),
            ({'kind':'convention'},'convention')]:
            self.assertEqual(event_icon(event),expected)
    def test_verified_only_and_primary_event(self):
        result={'events':[{'kind':'advisory','conflict':True},{'kind':'baseball','conflict':True}]}
        self.assertIsNone(animation_for(result,{}))
        self.assertEqual(animation_for(result,{'event_icons_verified':['detour']}),'detour-background.anim')
