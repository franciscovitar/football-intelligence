# AFA ARG_LPF 2016 `Figuritas de Primera` roster-image feasibility — 2026-08-26

Status: **NO-GO as roster source**; useful only as official contextual/player evidence.

## Source

Official AFA article:

- title: `Figuritas de Primera`
- publication date: `2016-02-08`
- URL: `https://www.afa.com.ar/Sitio/posts/figuritas-de-primera`

The article introduces the 30 Primera División 2016 clubs and states that it reviews the protagonists/players composing them.

## Bounded runtime probe

GitHub Actions run: `33000116734`

Artifact: `afa-arg-2016-roster-image-probe`

Artifact digest: `sha256:574b7e5c97d372b43cf0faf3de0b48e07ba85224160b04f86242e54371f08ee8`

The HTML exposed **28 unique image URLs matching the `Figu*` player-card pattern**. A bounded sample downloaded two official images successfully.

Visual inspection showed that these are **single-player circular "figurita" cards**, not squad sheets or roster tables. Examples from the bounded sample:

- Arsenal image: Ramiro Carrera
- Banfield image: Walter Erviti

The image `alt` fields are empty and do not expose roster text structurally.

## Decision

Do not use this article/image set to reconstruct Primera 2016 club rosters.

It may still be retained as official AFA contextual evidence that a named player was associated with a club around the tournament launch, but that evidence is one-player/club-style editorial content and cannot establish roster completeness, appearances, minutes, or season membership for all players.

No raw AFA images are committed to the repository and no product/database writes were performed.
