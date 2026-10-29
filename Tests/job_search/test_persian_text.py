from agent.job_search.matching import canon, contains_phrase
from agent.utilities.persian_text import html_to_text, normalize_for_search, normalize_persian, tokenize


def test_arabic_letters_and_diacritics_are_unified():
    assert normalize_persian("كارشناس فني") == "کارشناس فنی"
    assert normalize_persian("مُهَندِس") == "مهندس"


def test_search_normalization_digits_zwnj_case_and_punctuation():
    assert normalize_for_search("۳ سال سابقه، Python") == "3 سال سابقه python"
    assert normalize_for_search("مدل‌های زبانی") == "مدل های زبانی"
    assert normalize_for_search("«تهران»؛ کرج") == "تهران کرج"


def test_tokenize_drops_stopwords_and_keeps_technical_terms():
    tokens = tokenize("دنبال کار با C# و Node.js در تهران هستم")
    assert "c#" in tokens and "node.js" in tokens and "تهران" in tokens
    assert "در" not in tokens and "با" not in tokens


def test_phrase_matching_handles_plurals_suffixes_and_boundaries():
    text = canon("توسعه مدل‌های زبانی بزرگ و سیستم‌های RAG")
    assert contains_phrase(text, "مدل زبانی بزرگ")
    assert contains_phrase(text, "rag")
    assert not contains_phrase(canon("storage engineer"), "rag")
    assert contains_phrase(canon("برنامه‌نویسی پایتونی"), "پایتون")
    assert not contains_phrase(canon("مدیریت پروژه"), "مدیر")


def test_html_to_text_keeps_list_items_on_separate_lines():
    html = '<div><p>وظایف:</p><ul><li>نامه&zwnj;نگاری</li><li>Python &amp; SQL</li></ul></div>'
    assert html_to_text(html).splitlines() == ["وظایف:", "• نامه‌نگاری", "• Python & SQL"]


def test_ampersand_and_and_match_persian_va():
    assert contains_phrase(canon("مهارت: HTML و CSS"), "HTML & CSS")
    assert contains_phrase(canon("html and css"), "HTML & CSS")
