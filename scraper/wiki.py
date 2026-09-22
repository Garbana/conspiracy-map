"""Bendri pagalbiniai HTTP įrankiai (tik standartinė biblioteka)."""
import json
import time
import urllib.parse
import urllib.error
import urllib.request

try:  # naudoti Windows sertifikatų saugyklą (Python'o saugykla pasenusi)
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

UA = "ConspiracyMapBot/0.1 (https://github.com/Garbana/conspiracy-map; aanndriuss@gmail.com) python-urllib"
WP_API = "https://en.wikipedia.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"


MIN_INTERVAL = 1.0  # s tarp užklausų (mandagus tempas)
_last = [0.0]


def get_json(url, params=None, retries=8):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        gap = time.time() - _last[0]
        if gap < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - gap)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            ra = e.headers.get("Retry-After")
            wait = int(ra) if ra and ra.isdigit() else min(60, 5 * 2 ** attempt)
            print(f"  ! HTTP {e.code}, laukiu {wait}s")
            time.sleep(wait)
        except Exception as e:
            wait = min(60, 2 ** attempt)
            print(f"  ! klaida ({e}), bandau po {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Nepavyko: {url[:200]}")


def wp_query(params, api=None):
    """MediaWiki API užklausa su automatiniu 'continue' puslapiavimu.

    api – kitos kalbos Vikipedijos adresas (pvz. https://lt.wikipedia.org/w/api.php);
    nenurodžius kreipiamasi į anglišką.
    """
    base = {"action": "query", "format": "json", "formatversion": "2", "maxlag": "5"}
    base.update(params)
    cont = {}
    while True:
        data = get_json(api or WP_API, {**base, **cont})
        yield data
        if "continue" not in data:
            break
        cont = data["continue"]


def sparql(query, retries=8):
    return get_json(SPARQL, {"query": query, "format": "json"}, retries=retries)["results"]["bindings"]
