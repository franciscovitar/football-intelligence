from pathlib import Path

PATH = Path("analytics/src/football_intelligence/data_mesh/adapters/wyscout_open.py")
text = PATH.read_text(encoding="utf-8")

old_version = 'SEMANTIC_VERSION = "wyscout-open-v0.4"'
new_version = 'SEMANTIC_VERSION = "wyscout-open-v0.5"'
if text.count(old_version) != 1:
    raise SystemExit(f"expected one v0.4 semantic version line, found {text.count(old_version)}")
text = text.replace(old_version, new_version, 1)

old_scope = '_SPATIAL_V1_2_VALIDATED_SCOPES = frozenset({("ENG_PL", "2017/18")})'
new_scope = '''_SPATIAL_V1_2_VALIDATED_SCOPES = frozenset(
    {
        ("ENG_PL", "2017/18"),
        ("ESP_LL", "2017/18"),
        ("FRA_L1", "2017/18"),
        ("GER_BL1", "2017/18"),
        ("ITA_SA", "2017/18"),
    }
)'''
if text.count(old_scope) != 1:
    raise SystemExit(f"expected one ENG-only spatial scope gate, found {text.count(old_scope)}")
text = text.replace(old_scope, new_scope, 1)

PATH.write_text(text, encoding="utf-8")
print("PATCHED RUNNER CANDIDATE: wyscout-open-v0.5 + five spatial-v1.2 scopes")
