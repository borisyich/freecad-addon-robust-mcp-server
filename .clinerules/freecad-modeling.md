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
6. Immediately before the final user-facing response after any geometry change,
   call `validate_parametric_model` and summarize significant findings.
