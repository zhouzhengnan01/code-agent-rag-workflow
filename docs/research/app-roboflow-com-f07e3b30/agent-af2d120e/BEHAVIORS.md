# Agent navigation behaviors

- Source expanded class: `navbarV2 ... isExpanded`.
- Source collapsed outer width: `60px`.
- Source expanded outer width: `155px`.
- Source rail background: `rgb(12, 15, 26)` (`#0c0f1a`).
- Source rail padding: `12px 20px 12px 8px`.
- Source rail gap: `8px`.
- Source divider: `0.8px solid rgba(255,255,255,.08)`.
- Source width transition: `width 0.2s cubic-bezier(0,0,0.2,1)`.
- Requested adaptation: pointer hover or keyboard focus expands from 60px to 155px; leaving collapses unless pinned.
- Buttons use a 150ms color transition. Active items retain the Codezzn purple identity while using Roboflow geometry.
- Under 700px the existing drawer interaction is preserved; hover expansion is disabled.

