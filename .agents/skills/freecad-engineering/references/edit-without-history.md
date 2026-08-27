# Edit a part without construction history

Use this workflow for imported STEP/IGES/static `Part::Feature` geometry or any
solid whose original parametric feature tree is unavailable.

## Goal

Make the smallest local geometric change that satisfies the request while
preserving all unrelated geometry. Do not reconstruct fake history unless the
user explicitly requests reverse engineering.

## 1. Inspect before editing

Establish a baseline:

- document/object name;
- shape validity;
- solid count, volume, bounding box;
- relevant face/edge types and dimensions;
- local subshape neighborhood around the requested feature.

Use `select_subshapes` for semantic selection and local neighborhood inspection. Do not choose a face
only because it happened to be `Face23` in one inspection response.

Create a local edit contract before mutation:

- requested target feature and the boundary expected to move/disappear/appear;
- exact requested magnitude and direction;
- affected faces/surfaces and their transition chain;
- protected faces, interfaces, feature counts, envelope directions, and solid
  count that must remain invariant;
- direct measurement that will prove the edit;
- maximum plausible changed region/volume for this operation.

When the prompt identifies geometry relationally (for example, “the smaller of
two bores” or “four pockets on +X”), first enumerate all candidates and prove the
chosen subset from axis, size, centroid, adjacency, and count. Do not stop after
finding the first plausible face.

## 2. Capture a before-state checkpoint

Before a direct B-rep change, use `capture_shape_checkpoint` on the target
object. The checkpoint is the reference for proving that the change was local
and of the intended magnitude.

Also save the baseline measurements and selected-feature inventory in the task
record. Topological names may change after surgery; the semantic criteria and
measured invariants are the durable identity.

## 3. Choose the least destructive edit strategy

Prefer the highest-level local operation that matches the request:

- `move_faces` for supported face-offset/translation edits;
- `defeature_faces` for removing local features;
- `extract_feature_material` when a feature must be isolated/reused;
- `group_feature_faces` and `inspect_subshape_neighborhood` to identify feature
  boundaries;
- boolean cut/fuse/common with explicit tool solids for well-defined additions
  or removals;
- `slice_shape`, `section_shape`, `offset_3d`, `shell_object`, `heal_shape`,
  `sew_shell`, or `make_solid` only when the requested topology requires them.

Do not perform broad healing or reconstruction as a default. Global healing can
change face orientation/topology far from the requested edit.
Preserve the exact source B-rep when possible. Do not tessellate an analytic STEP
solid into a faceted proxy merely to perform a local edit.

## 4. Preserve functional interfaces and transitions

Before deciding which boundary to move, identify geometry that should remain an
invariant: mating faces, bearing/seal seats, thread or bore geometry, hole axes,
splines/teeth, datum surfaces, and other interfaces. If the requested dimension
can be achieved by moving either of two boundaries, preserve the more functional
boundary unless the request explicitly targets it.

When moving/removing feature faces, inspect adjacent transition faces:

- fillets/chamfers may belong to the feature and need removal/rebuild;
- wall moves may require neighboring faces to extend/trim;
- a local edit that leaves a visible gap or disconnected sliver is not success;
- a helper strip used only to force a union is a warning that the underlying
  feature geometry/attachment is wrong.

Prefer exact intersection/extension of the intended surfaces over cosmetic
bridges.

After editing, re-run the semantic selection instead of assuming old `FaceN` or
`EdgeN` identities survived. Walk the neighborhood again until the attachment
and transition chain are explicit.

## 5. Validate the delta immediately

After the edit:

1. recompute and validate the shape;
2. compare the object with `compare_shape_checkpoint`;
3. measure the requested dimensional change directly;
4. inspect the changed neighborhood;
5. verify that solid count and unrelated envelope dimensions stayed unchanged
   unless the request says otherwise.

Read the checkpoint comparison as localization evidence, not a universal score.
Confirm that added/removed regions lie on the intended feature and that their
direction/magnitude are plausible. For tangential moves or small edits below the
localization resolution, prove the delta with feature-specific measurements such
as bore axis/center, wall position, or hole inventory.

If the delta is much larger than the intended region, restore/rework instead of
accepting a globally altered solid.

For exported STEP/BREP deliverables, validate the written artifact or re-import
it into a separate verification document. Accept only when the export retains a
valid intended solid and the same direct delta evidence.

## 6. Direct B-rep is not a failure mode here

For a history-less STEP edit, a clean direct solid can be the correct final
representation. `validate_parametric_model` may report the imported/static shape
as non-parametric; interpret that as representation information, not automatic
failure.

Do not create arbitrary sketches, Spreadsheets, or Bodies solely to make the
validator look more parametric.

## Completion checks

- Requested geometry changed by the specified amount and direction.
- The changed region matches the intended feature.
- Unrelated geometry is unchanged within meaningful tolerance.
- The post-edit semantic target was reselected and its neighborhood/transition
  chain inspected rather than trusted by old topology names.
- No gaps, slivers, disconnected solids, or hidden helper bodies were introduced.
- Final shape is valid and checkpoint delta is reviewed.
