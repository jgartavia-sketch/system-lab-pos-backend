"""Pruebas del estreno automático del capítulo 4."""
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.api.routes import stories


def test_chapter_four_release_time_matches_costa_rica():
    assert stories.CHAPTER_FOUR_RELEASE_AT == datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def test_chapter_four_unlocks_exactly_at_release_time():
    release_at = stories.CHAPTER_FOUR_RELEASE_AT
    assert not stories.chapter_four_is_published(release_at - timedelta(microseconds=1))
    assert stories.chapter_four_is_published(release_at)
    assert stories.chapter_four_is_published(release_at + timedelta(days=1))


def test_preview_reader_keeps_early_access(monkeypatch):
    monkeypatch.setattr(stories, "PREVIEW_EMAILS", {"preview@example.com"})
    reader = SimpleNamespace(email="preview@example.com")
    before_release = stories.CHAPTER_FOUR_RELEASE_AT - timedelta(days=1)
    assert stories.has_chapter_four_access(reader, before_release)


def test_regular_reader_waits_until_release(monkeypatch):
    monkeypatch.setattr(stories, "PREVIEW_EMAILS", {"preview@example.com"})
    reader = SimpleNamespace(email="reader@example.com")
    before_release = stories.CHAPTER_FOUR_RELEASE_AT - timedelta(seconds=1)
    assert not stories.has_chapter_four_access(reader, before_release)
    assert stories.has_chapter_four_access(reader, stories.CHAPTER_FOUR_RELEASE_AT)
