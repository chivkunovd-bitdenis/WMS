"""Context settings installation must preserve unrelated owner configuration."""
import tomllib

from support_agent.context_config import merge_context_config

SETTINGS = {"model_auto_compact_token_limit": 250000, "model_auto_compact_token_limit_scope": "total"}


def test_context_install_preserves_user_model_permissions_tables_and_comments():
    original = ('# user comment\nmodel="gpt-6.1-sol"\napproval_policy="never"\n'
                "'model_auto_compact_token_limit'=100000\n"
                '[features]\nmemories=true\n[other]\ncustom="keep"\n')
    merged = merge_context_config(original, SETTINGS)
    before, after = tomllib.loads(original), tomllib.loads(merged)
    assert after["model_auto_compact_token_limit"] == 250000
    assert after["model_auto_compact_token_limit_scope"] == "total"
    assert after["model"] == before["model"]
    assert after["approval_policy"] == before["approval_policy"]
    assert after["features"] == before["features"]
    assert after["other"] == before["other"]
    assert merged.startswith('# user comment\nmodel="gpt-6.1-sol"\napproval_policy="never"\n')
    assert merge_context_config(merged, SETTINGS) == merged


def test_new_keys_are_at_root_even_with_existing_table_and_missing_final_newline():
    result = merge_context_config('[features]\nmemories=true', SETTINGS)
    assert tomllib.loads(result) == {**SETTINGS, "features": {"memories": True}}
