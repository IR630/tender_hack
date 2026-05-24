from other_public_scraper.domain_strategies import (
    DOMAIN_STRATEGIES,
    listing_domain_key,
    strategy_for_url,
)


def test_e2e4_regional_hosts_share_listing_key():
    assert (
        listing_domain_key("https://moscow.e2e4online.ru/catalog/myshi-18/")
        == "e2e4online.ru"
    )
    assert (
        listing_domain_key("https://novosibirsk.e2e4online.ru/catalog/myshi-18/")
        == "e2e4online.ru"
    )


def test_mvideo_strategy_declares_api_search():
    strategy = strategy_for_url("https://www.mvideo.ru/komputernye-aksessuary-24/myshi-183")

    assert strategy is not None
    assert strategy.name == "mvideo"
    assert strategy.api_search is not None
    assert strategy.supports_category("orgtech")


def test_priority_categories_have_registered_strategies():
    categories = {
        category
        for strategy in DOMAIN_STRATEGIES
        for category in strategy.categories
    }

    assert {"orgtech", "tires", "clothes"}.issubset(categories)
