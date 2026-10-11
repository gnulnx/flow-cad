# Viewer presentation

The header's **Hide chat / Show chat** control reclaims the chat column without
unmounting the conversation. Drafts and running streams remain intact. Asking
about viewport markup opens chat automatically. The **Showroom** viewport toggle
switches between the inspection grid and a studio setup: warm key, cool fill/rim,
local reflection cards and a shadow-catching floor fitted below visible bounds.
Both preferences are remembered in this browser using local storage, with a
session-only fallback when storage is unavailable.

The showroom is presentation only. It does not enter selection, measurement,
model bounds or exports. Original component colors are retained. One shadow map
and a small, locally generated environment map avoid external HDR downloads.
The renderer remains on demand. Switching off removes the environment and floor.

## Proposed appearance editor (discussion, not implemented)

Start with an Appearance section in the inspector: color swatch/hex input,
finish presets (matte plastic, satin paint, rubber, metal), live preview, Undo
and Reset to source. Offer explicit scope: selected occurrence, all occurrences
of this part, or a named project appearance group. B3 can declare groups such as
shell, trim and wheels; the reusable runtime should not infer these from colors.
Save named palettes for comparing alternatives.

Keep appearance distinct from the manufacturing material field used by the
inventory and print intent. A visual finish does not change a BOM or qualify a
material for fabrication. Commit project palettes and assignments as a versioned
project document, served by a generic runtime API; transient browser previews
should not silently rewrite CAD source or export appearance.

Currently parseDisplay retains GLB base color and opacity, while AssemblyModel
uses the same roughness (.58) and metalness (.08) for all components. Extend the
owned display contract with source appearance, then layer per-occurrence
appearance overrides when creating mesh materials. Never mutate cached geometry
or shared source materials. Preserve selection highlights as a separate layer.

Persist against stable part/occurrence/component identities. Current component
selection keys contain artifact revision and positional indices; they are not
safe durable appearance keys across rebuilds. Ambiguous or missing targets must
be shown as unresolved after a rebuild rather than coloring an unrelated part.
