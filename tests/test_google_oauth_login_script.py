"""Script local de consentement OAuth : le jeton est écrit dans .env, jamais affiché ni commité."""
from scripts.google_oauth_login import upsert_env_var


def test_replaces_an_existing_value_and_keeps_crlf_line_endings():
    content = "API_KEY=abc\r\nGOOGLE_OAUTH_REFRESH_TOKEN=old\r\nGEMINI_API_KEY=x\r\n"
    assert upsert_env_var(content, "GOOGLE_OAUTH_REFRESH_TOKEN", "new") == (
        "API_KEY=abc\r\nGOOGLE_OAUTH_REFRESH_TOKEN=new\r\nGEMINI_API_KEY=x\r\n"
    )


def test_matches_the_key_whatever_its_case():
    content = "google_oauth_refresh_token=old\n"
    assert upsert_env_var(content, "GOOGLE_OAUTH_REFRESH_TOKEN", "new") == "GOOGLE_OAUTH_REFRESH_TOKEN=new\n"


def test_appends_the_key_when_absent_even_without_final_newline():
    content = "API_KEY=abc\r\nGEMINI_API_KEY=x"
    assert upsert_env_var(content, "GOOGLE_OAUTH_REFRESH_TOKEN", "tok") == (
        "API_KEY=abc\r\nGEMINI_API_KEY=x\r\nGOOGLE_OAUTH_REFRESH_TOKEN=tok\r\n"
    )


def test_does_not_touch_a_key_that_only_shares_a_prefix():
    content = "GOOGLE_OAUTH_REFRESH_TOKEN_OLD=keep\n"
    assert upsert_env_var(content, "GOOGLE_OAUTH_REFRESH_TOKEN", "tok") == (
        "GOOGLE_OAUTH_REFRESH_TOKEN_OLD=keep\nGOOGLE_OAUTH_REFRESH_TOKEN=tok\n"
    )
