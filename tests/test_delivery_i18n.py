from skeptiq.delivery.i18n import t


def test_known_key_en() -> None:
    assert t("en", "long_signal") == "LONG signal"
    assert t("en", "confidence") == "Confidence"
    assert t("en", "stop_loss") == "Stop loss"


def test_known_key_ru() -> None:
    assert t("ru", "long_signal") == "LONG сигнал"
    assert t("ru", "confidence") == "Уверенность"
    assert t("ru", "stop_loss") == "Стоп-лосс"


def test_disclaimer_present_in_both_languages() -> None:
    assert "investment advice" in t("en", "disclaimer")
    assert "инвестиционная" in t("ru", "disclaimer")


def test_alignment_value_translation() -> None:
    assert t("en", "align_confirms") == "confirms"
    assert t("ru", "align_confirms") == "подтверждает"
    assert t("ru", "align_contradicts") == "противоречит"


def test_unknown_key_falls_back_to_english_then_to_key() -> None:
    # Russian doesn't have this -> falls back to English
    # English doesn't have it either -> returns the key as-is.
    assert t("ru", "this_key_does_not_exist") == "this_key_does_not_exist"
