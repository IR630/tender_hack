import pytest

from app.query.processor import process_query


@pytest.mark.asyncio
async def test_process_query_expands_short_comp() -> None:
    processed = await process_query("комп")
    assert processed.original == "комп"
    assert processed.corrected == "компьютер"


@pytest.mark.asyncio
async def test_process_query_expands_iphone_misspelling() -> None:
    processed = await process_query("ипхон")
    assert processed.original == "ипхон"
    assert processed.corrected == "айфон"
