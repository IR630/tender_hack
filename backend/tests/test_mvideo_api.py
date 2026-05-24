from other_public_scraper.pipelines.mvideo_api import _price_map


def test_mvideo_price_map_prefers_sale_price():
    payload = {
        "body": {
            "materialPrices": [
                {
                    "productId": "50173433",
                    "price": {"basePrice": 2399, "salePrice": 1699},
                }
            ]
        }
    }

    assert _price_map(payload) == {"50173433": 1699}
