# Part browsing

The inventory opens on **Parts to make**, with Purchased, Hardware, Views,
References and All tabs. These filter the inventory list independently of
selection, visibility and loaded geometry. Search uses every word across names,
keys, aliases, roles, lifecycle, sections, categories and material. A material
filter includes an explicit Unspecified choice. Changing category resets the
material filter, and matching text reveals collapsed sections.

Projects can author two optional public manifest fields:

```yaml
category: make  # make | purchased | hardware | view | reference
display_name: Removable access panel
material: PETG
```

`PartCategory` is exported by `flow_cad.sdk`. Category is independent of lifecycle
and print readiness: an inspection part can be a custom fabrication concept.
Display names never replace stable keys or UUIDs. The full key remains available
in the row tooltip. Names, category and material flow through `flow sync`, the
SQLite inventory and `/api/parts`; geometry is not imported for these operations.
Run `flow sync` after metadata changes. Index schema 3 rebuilds an older disposable
index even when the manifest hash is unchanged.

For manifests without category metadata, printable roles appear in Parts to make
and reference/legacy roles in References. Other uncategorized parts remain
available under All. No file extension, part-name heuristic or product-specific
rule determines whether a component is manufactured or purchased.

Counts describe indexed entries, not BOM quantities. In particular, occurrences
in several alternative assemblies must not be summed into a purchasing quantity.
The row shows lifecycle and material, while its eye controls visibility. Existing
click/Ctrl-click behavior is retained. Tab navigation supports arrows and
Home/End keys.
