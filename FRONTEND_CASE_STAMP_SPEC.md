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

- Current typography: **Press Start 2P for the wordmark and homepage hero heading only**; Inter for all other headings, case titles, case IDs, buttons, metadata, and chat. Three size tiers (20px title, 16px body, 13px small). Google Fonts loads with `display=swap`.
- Desktop max-width: 1050px site shell and 790px gameplay chat; case library at most two columns, one column on phones.
- Responsive breakpoint: 650px. Mobile chat takes ~48vh, and composer sits above Hint/Reveal.
- Borders: minimal 1px, soft 3–4px corners, no decorative border layers or drop shadows. The magnifying-glass mark and wordmark provide the pixel-art identity.
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

## Simplification pass — 2026-11-10

Following product-owner feedback that the screen had too many font sizes, fonts and competing elements:
- **Pixel font for the Dark Stories wordmark and the single homepage hero heading.** All case titles, other headings, buttons, descriptions and chat use Inter.
- **Three type tiers:** 20px titles, 16px main text and controls, 13px muted metadata (brand scales down on smaller devices).
- **One featured parchment case panel**, flat color instead of layered borders, gradients, stepped decorations, or heavy shadows.
- **One magnifying-glass brand mark** at the top; no additional icons on case cards.
- Remove redundant eyebrow text, tagline under the logo, second "no spoilers" badge, decorative star in feedback, and "Open case" repeated on every library card.
- Maintain all gameplay, sharing, private-solution and feedback capabilities; only the presentation is simplified.

## Homepage heading refinement

The product owner approved reintroducing **Press Start 2P on the main homepage hero heading only**, in addition to the established pixelated wordmark. Keep all remaining UI in Inter and retain minimal case-file styling. The hero font scales gently from 12px on narrow mobile layouts to 17px on desktop; no other pixel-text treatments.
