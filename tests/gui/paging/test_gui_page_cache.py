from __future__ import annotations

from gui.paging.page.page_cache import PageCache


def test_the_rows_are_kept_by_page() -> None:
    cache = PageCache[str](page_size=2, max_pages=2)

    cache.store(0, ["a", "b"])
    cache.store(1, ["c"])

    assert [cache.get(row) for row in range(4)] == ["a", "b", "c", None]
    assert (cache.page_of(3), cache.row_count) == (1, 3)
    assert not cache.needs(0)
    assert cache.needs(4)


def test_the_least_recently_used_page_is_forgotten() -> None:
    cache = PageCache[str](page_size=1, max_pages=2)
    cache.store(0, ["a"])
    cache.store(1, ["b"])
    cache.get(0)

    cache.store(2, ["c"])

    assert list(cache.pages) == [0, 2]
    assert cache.needs(1)


def test_a_refresh_keeps_the_stale_pages_until_read_again() -> None:
    cache = PageCache[str](page_size=1, max_pages=4)
    cache.store(0, ["a"])
    cache.pending.add(1)

    cache.invalidate()

    assert cache.get(0) == "a"
    assert cache.needs(0)
    assert cache.needs(1)
    cache.clear()
    assert cache.get(0) is None
