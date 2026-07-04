---
weekly_send_cap: 5
weekends_free: true
---

# Bring queue — example

A realistic week for a solo builder. Copy the shape, not the content.

## Send the pilot invite to Jordan
kind: send
due: 2026-07-07
link: https://mail.example.com/drafts/abc
note: draft is written; needs the pricing line confirmed

## Decide: sunset the old landing page
kind: decide
id: sunset-landing
note: traffic is 9 visits/mo; decision brief in docs/landing-retro.md

## Ship the CLI v1.0.0 tag
kind: ship
due: 2026-07-10
note: zero code blockers — it's literally `git tag v1.0.0 && git push --tags`

## Close: follow up on the unpaid March invoice
kind: close
due: 2026-07-08
