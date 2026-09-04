from __future__ import annotations

from bravia_client.matching import clean_title


def test_clean_title_decodes_html_entities():
    assert clean_title("D\u00e9cor d&apos;int\u00e9rieur") == "D\u00e9cor d'int\u00e9rieur"


def test_clean_title_normalizes_nbsp():
    assert clean_title("Play\u00a0Store") == "Play Store"
