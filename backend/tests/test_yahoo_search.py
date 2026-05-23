from other_public_scraper.pipelines.yahoo_search import _cite_to_url, _parse_yahoo_html


def test_cite_to_url_yahoo_format():
    assert _cite_to_url("spb.koleso.ruhttps://spb.koleso.ru › catalog › tyres") == (
        "https://spb.koleso.ru/catalog/tyres"
    )
    assert _cite_to_url("kolesa812.ruhttps://kolesa812.ru › shiny") == (
        "https://kolesa812.ru/shiny"
    )


def test_parse_yahoo_html_extracts_shop_links():
    html = """
    <div class="algo">
      <h3 class="title"><a href="https://r.search.yahoo.com/x">Шины</a></h3>
      <span class="fc-falcon">kolesa812.ruhttps://kolesa812.ru › shiny</span>
      <div class="compText"><p>Купить шины</p></div>
    </div>
    <div class="algo">
      <h3 class="title"><a href="https://r.search.yahoo.com/y">Ozon</a></h3>
      <span class="fc-falcon">ozon.ruhttps://www.ozon.ru › product</span>
    </div>
    """
    hits = _parse_yahoo_html(html, limit=10)
    assert len(hits) == 1
    assert hits[0].source == "yahoo"
    assert "kolesa812.ru" in hits[0].url
