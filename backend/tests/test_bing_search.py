from other_public_scraper.pipelines.bing_search import _cite_to_url, _parse_bing_html


def test_cite_to_url():
    assert _cite_to_url("https://www.dns-shop.ru › catalog") == "https://www.dns-shop.ru/catalog"
    assert _cite_to_url("https://www.citilink.ru › catalog › noutbuki") == (
        "https://www.citilink.ru/catalog/noutbuki"
    )


def test_parse_bing_html_extracts_shop_links():
    html = """
    <ol id="b_results">
      <li class="b_algo">
        <h2><a href="https://www.bing.com/ck/a">Ноутбуки DNS</a></h2>
        <cite>https://www.dns-shop.ru › catalog › noutbuki</cite>
        <div class="b_caption"><p>Купить ноутбук</p></div>
      </li>
      <li class="b_algo">
        <h2><a href="https://www.bing.com/ck/a">Ozon</a></h2>
        <cite>https://www.ozon.ru › product</cite>
      </li>
    </ol>
    """
    hits = _parse_bing_html(html, limit=10)
    assert len(hits) == 1
    assert hits[0].source == "bing"
    assert "dns-shop.ru" in hits[0].url
    assert hits[0].title == "Ноутбуки DNS"
