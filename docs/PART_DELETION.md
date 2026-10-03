# Delete a project part

Right-click a part in the workbench parts list and choose **Delete part**.
Keyboard users can focus its row and press Shift+F10 or the context-menu key.
Escape dismisses the menu. Deletion shows immediate progress and errors in the
parts list; a successful deletion clears its selection and refreshes inventory.

`DELETE /api/parts/{uuid-or-key-or-alias}` removes the manifest entry, aliases,
source registration, artifact/dependency index, validation records, and assembly
occurrences. Compiled exports of affected assemblies are invalidated rather than
continuing to show the removed component. Unrelated registry records survive.
The operation does not import CAD code or rebuild geometry.

Unshared registered files under `exports/` move into
`.flow/trash/parts/<part-uuid>-<operation-id>/files/`, with their original relative
paths. The same recovery folder contains the pre-delete manifest. Shared files,
explicit surviving artifact dependencies, symlink targets, and frozen reference
inputs remain untouched. Failure rolls back file moves, manifest and database.
An active CAD job must finish or be cancelled before deletion so its publisher
cannot recreate files while they are being removed.

Generator Python source and historical chat, job, annotation and measurement
journals remain intact. Deletion removes their active part registration; it does
not rewrite arbitrary Python, documentation or immutable audit history. A later
explicit reintroduction of the part in the manifest will register it again.
For source-generated assemblies, update their generator before regenerating an
assembly that previously embedded the deleted part.

Recovery is manual: retrieve selected files from the recovery folder and restore
the required part/occurrence entries from its saved manifest, then run `flow sync`.
Do not replace the whole manifest if other edits have happened since deletion.
