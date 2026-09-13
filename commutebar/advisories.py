"""SFMTA advisory discovery and conservative date/street extraction.

Dates represent the outer advisory envelope, not an assertion that every
listed street is closed continuously. Exact closure hours stay at the source.
"""
from datetime import datetime, timedelta
from html.parser import HTMLParser
import re
from urllib.parse import urljoin
from .sources import request, TZ

INDEX = 'https://www.sfmta.com/travel-transit-updates'
STREETS = ('Spear','Embarcadero','King','3rd','4th','Howard','Folsom','Mission','Minna','2nd','16th','7th','Townsend','Brannan','Harrison','Hawthorne','Terry A Francois','Warriors Way')
REGIONS = ('South of Market','Financial District','Mission Bay','Potrero Hill','Embarcadero')
MONTHS = {name:i for i,name in enumerate(('January','February','March','April','May','June','July','August','September','October','November','December'),1)}


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag,self.attrs,self.children = tag,dict(attrs),[]
    def text(self):
        return ' '.join(x.text() if isinstance(x,Node) else x for x in self.children)
    def find(self, predicate):
        result = [self] if predicate(self) else []
        for child in self.children:
            if isinstance(child,Node): result.extend(child.find(predicate))
        return result


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root=Node();self.stack=[self.root];self.feed(html)
    def handle_starttag(self,tag,attrs):
        node=Node(tag,attrs);self.stack[-1].children.append(node)
        if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):
            self.stack.append(node)
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:
                self.stack=self.stack[:i];break
    def handle_data(self,data):
        self.stack[-1].children.append(data)


def field(root, name):
    found=root.find(lambda n:name in n.attrs.get('class','').split())
    return found[0] if found else Node()


def discover(html):
    root=Document(html).root
    if not root.find(lambda n:n.tag=='h1' and 'Travel & Transit Updates' in n.text()):
        raise ValueError('SFMTA index markup changed')
    links={}
    for h in root.find(lambda n:n.tag=='h3'):
        for a in h.find(lambda n:n.tag=='a' and n.attrs.get('href','').startswith('/travel-updates/')):
            links[urljoin(INDEX,a.attrs['href'])]=' '.join(a.text().split())
    nexts=root.find(lambda n:n.tag=='a' and 'next' in n.attrs.get('rel','').split())
    # Drupal uses title="Go to next page" in the observed index.
    if not nexts:
        nexts=root.find(lambda n:n.tag=='a' and n.attrs.get('title')=='Go to next page')
    return links, urljoin(INDEX,nexts[0].attrs['href']) if nexts else None


def date_envelope(text, title):
    years=re.findall(r'\b20\d{2}\b',title)
    if not years or len(set(years))!=1:
        return None
    year=int(years[0]);dates=[]
    expression=r'\b('+'|'.join(MONTHS)+r')\s+(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?(?:,?\s+(20\d{2}))?'
    for match in re.finditer(expression,text,re.I):
        month=MONTHS[match[1].title()];y=int(match[4] or year)
        for value in (match[2],match[3]):
            if value:
                dates.append(datetime(y,month,int(value),tzinfo=TZ))
    if not dates:
        return None
    # Ambiguous cross-year and long-running notices stay in manual review.
    if (max(dates)-min(dates)).days>62:
        return None
    return min(dates),max(dates)+timedelta(days=1)-timedelta(seconds=1)


def parse_advisory(html, url):
    root=Document(html).root
    titles=root.find(lambda n:n.tag=='h1')
    if not titles: raise ValueError('SFMTA advisory title missing')
    title=' '.join(titles[0].text().split())
    affected=' '.join(field(root,'field--name-field-transit-type-disrupted').text().split())
    regions=' '.join(field(root,'field--name-field-neighborhoods').text().split())
    if 'Driving' not in affected or not any(r.lower() in regions.lower() for r in REGIONS):
        return None
    cancelled=field(root,'field--name-field-cancelled').text().strip().lower()
    if cancelled in ('yes','cancelled','canceled','1'):
        return None
    body=field(root,'field--name-body')
    text=' '.join(body.text().split())
    if not text:raise ValueError('SFMTA advisory body missing')
    dates=date_envelope(text+' '+title,title)
    if dates is None:raise ValueError('Advisory dates need manual review')
    start,end=dates
    roads=[road for road in STREETS if re.search(r'\b'+re.escape(road)+r'\b',text,re.I)]
    return dict(id='sfmta-'+url.rstrip('/').split('/')[-1],title=title,venue='Downtown streets',source='SFMTA advisories',
                date=start.date().isoformat(),start=start.isoformat(),end=end.isoformat(),kind='advisory',
                status='Published advisory; individual closure hours vary',url=url,streets=roads,
                regions=[r for r in REGIONS if r.lower() in regions.lower()],
                timing_basis='Outer dates mentioned in advisory; check source for specific closure hours')


def fetch_advisories(now, loader=request):
    from concurrent.futures import ThreadPoolExecutor
    links={};page=INDEX;visited=set();problems=[]
    for _ in range(3):
        if not page or page in visited:break
        if not page.startswith(INDEX):raise ValueError('Unexpected SFMTA pagination target')
        visited.add(page);found,page=discover(loader(page));links.update(found)
    if page and page not in visited: problems.append('More index pages exist')
    def fetch(url):
        try:return parse_advisory(loader(url),url),None
        except Exception as exc:return None,dict(url=url,reason=type(exc).__name__)
    events=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for event,error in pool.map(fetch,links):
            if event:events.append(event)
            if error:problems.append(error)
    return events,problems
