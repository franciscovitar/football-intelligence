"""Source-specific normalization: provider payload -> NormalizedObservation.

Provider payloads are treated as untrusted and defensively type-checked, the
same way `normalization/api_football.py` treats API-Football payloads.
"""
