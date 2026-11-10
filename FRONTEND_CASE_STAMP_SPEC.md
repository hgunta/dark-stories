# Dark Stories — Case Stamp frontend v1

## Product direction (approved)

- 32-bit-inspired **minimal** retro detective mystery aesthetic; do not recreate the heavy per-case illustrated mockups.
- **Approved emblem: pixel magnifying glass**, in the global header only; no balance scales, wax seals, avatars, or recurring images inside chat.
- **No illustration per mystery** and no third-party JS. Load Google Fonts Press Start 2P (display) and Inter (body), with local/system fallbacks. Existing case metadata drives the library.
- Premium but readable chat, not a fake computer terminal: player questions align right in burgundy bubbles; moderator responses align left in warm paper-colored bubbles.
- Keep the primary play surface to case premise, messages, one text input, Send, Hint, Reveal. Advanced operations are collapsed behind native `details`.

## Tokens

| Role | Value |
| --- | --- |
| Background | `#170c12` |
| Raised surface | `#25121d` |
| Case parchment | `#f1cfa4` |
| Primary burgundy | `#661f32` |
| Burgundy highlight | `#922c46` |
| Gold | `#eab26e` |
| Parchment | `#ffe3ba` |
| Muted copy | `#c9a6a5` |

- Typography: **Press Start 2P for short display titles, wordmark, case IDs and primary CTA only**; **Inter for body, descriptive copy, chat messages, inputs and secondary controls**. Use Google Fonts `display=swap` to avoid invisible text on slow networks. Keep body copy non-pixelated for readability.
- Desktop max-width: 1050px site shell and 790px gameplay chat; case library at most two columns, one column on phones.
- Responsive breakpoint: 650px. Mobile chat takes ~48vh, and composer sits above Hint/Reveal.
- Borders: restrained 1–3px burgundy/pink, 2–4px corner rounding and stepped case-file corners. Occasional squared shadow on primary CTA. Slight pixel geometry, not heavy game overlays.
- Accessibility: semantic buttons and regions, visible focus, live chat role, accessible status messages, reduced-motion support.

## Screen behavior and release scope

1. **Landing:** featured title/difficulty plus Open Case and Browse Cases. No room/API moderation call until user opens a case, except direct room/case deep links.
2. **Library:** text-only case cards from `GET /api/mysteries`; title, ID and difficulty. Selecting card creates the chosen room.
3. **Gameplay:** unchanged `/api/create_room`, `/api/message`, `/api/hint`, `/api/reveal`. Moderator logic and authored mystery data are out of scope.
4. **Advanced options:** private solution check, multiplayer join/invite, shared activity, share case; preserve existing events and endpoints but keep out of main play flow.
5. **End of game:** unchanged solved/reveal processing and optional rating. The magnifying glass is a small brand identity mark, not a replacement for the solution.
6. **Deep links:** `?case=ms-XXX` opens a selected game; `?room=ABCD` joins a shared room.

## Acceptance checks before owner approves the public release

- Desktop/mobile at narrow (320px), mid (375–430px), and desktop (>900px); no horizontal scroll; keyboard input and visible focus.
- Open featured, open another case, random case, join invitation, sharing fallback, question reply/hint/reveal confirmation.
- Private guess and game-end feedback remain available under More options.
- Solve flow disables input and never leaks another player's secret guess.
- Test with `USE_API=false` first; if approved, use a controlled, budgeted AI-moderator check in staging.
- Confirm production Render deployment SHA, environment, auto-deploy setting, rollback and editorial status of the public mystery library.
- **Do not merge or deploy merely because CI passes.** This branch is a draft frontend prototype for owner review.

Related changes: PR #21 (local mystery reviewer) is independent and not changed by this feature.
