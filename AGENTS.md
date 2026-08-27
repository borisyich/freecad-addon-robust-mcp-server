# FreeCAD engineering-agent router

These repository instructions apply to every task that creates, reconstructs,
modifies, repairs, or validates a mechanical model in FreeCAD.

1. Activate and follow the `freecad-engineering` Skill before calling modeling tools.
2. The canonical policy is `.agents/skills/freecad-engineering/SKILL.md`; do not
   maintain a second copy of the modeling workflow in this file.
3. For clients without native Skills support, read that file directly or load
   `freecad://skills/freecad-engineering`.
4. Keep `execute_python`, `safe_execute`, and `run_macro` available; using them
   does not waive the Skill's parametric/editability requirements.
5. Handle drawing ambiguity autonomously as defined by the Skill; do not stop
   merely to ask the user for a missing or unclear noncritical value.
6. Use `multi_transform_pattern` instead of chaining one PartDesign Pattern directly onto another.
7. For drawing/sketch input, inventory every source view/detail/section and
   every explicit dimension before modeling; drafting markers do not make a
   dimension optional. Dimensions end as driving/verification, or exceptional
   `source_issue` with concrete source evidence; never use unresolved as a
   terminal manifest role. Pass all driving
   IDs to final validation and measure every driving/verification dimension
   between the same semantic elements in its reproduced source-view context.
   Compare feature-relevant views during modeling and every source-view manifest
   record one-to-one before final acceptance.
8. Use `select_subshapes` instead of manual Face/Edge enumeration when
   choosing sketch support or topology-sensitive feature references.
9. Bind Spreadsheet-driven sketch dimensions through constraint expressions and
   verify the resulting paths with `get_sketch_info`.
10. Immediately before the final user-facing response after any geometry change,
   call `validate_parametric_model` and summarize significant findings.
