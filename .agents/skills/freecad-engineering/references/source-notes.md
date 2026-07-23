# Source notes

The skill distills the following official documentation and established CAD
principles. These links are references, not runtime dependencies.

## Codex skill placement and loading

- OpenAI, **Build skills**:
  https://developers.openai.com/codex/build-skills
  - repository skills belong under `.agents/skills/<skill-name>/SKILL.md`;
  - Codex initially sees skill name/description/path and loads full instructions
    when selected;
  - concise, front-loaded descriptions improve implicit activation.
- OpenAI, **AGENTS.md**:
  https://developers.openai.com/codex/agent-configuration/agents-md
  - Codex reads repository `AGENTS.md` before work;
  - keep durable routing rules concise and use skills for richer workflows.

## FreeCAD parametric structure

- FreeCAD documentation, **Basic Part Design Tutorial**:
  https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Basic_Part_Design_Tutorial.md
  - PartDesign starts with a Body and builds a solid from sketches and additive/
    subtractive features;
  - sketches are constrained and redundant constraints should be corrected.
- FreeCAD documentation, **Glossary — Body**:
  https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Glossary.md
  - a Body groups sketches, construction geometry, and features to create one
    contiguous solid.
- FreeCAD blog, **Spreadsheets and Parametric Design**:
  https://blog.freecad.org/2025/04/08/tutorialgetting-started-with-spreadsheets-and-parametric-design/
  - Spreadsheet aliases/expressions can centralize reusable design parameters.

## Sheet-metal deformation

- SOLIDWORKS Help, **Bend Allowance and Bend Deduction**:
  https://help.solidworks.com/2013/english/solidworks/sldworks/c_bend_allowance_and_bend_deduction.htm
  - bend allowance is measured along the neutral axis and K-factor participates
    in flat-length calculation.
- Autodesk Inventor Help, **Bend tables for sheet metal materials**:
  https://help.autodesk.com/view/INVNTOR/2023/ENU/?guid=GUID-27FD9757-5B40-4528-B361-D9BDFDB2EA4D
  - bend deductions vary with bend angle and radius.

The sheet-metal guidance therefore rejects a universal "add equal volume on one
side and remove it on the other" rule. That boolean heuristic does not represent
neutral-axis deformation or guarantee a correct developed blank.

## Manufacturing-oriented classification

- Autodesk Fusion Help, **Turning**:
  https://help.autodesk.com/view/fusion360/ENU/?contextId=MFG-TURNING-OVERVIEW
  - turning is centered on a defined rotary axis and is suited to cylindrical,
    conical, bore, groove, shaft, ring, and thread geometry;
  - radius-versus-diameter interpretation must be explicit.
- Autodesk Fusion Help, **Stock tab reference**:
  https://help.autodesk.com/view/fusion360/ENU/?guid=MFG-REF-SETUP-STOCK
  - subtractive setups distinguish box, cylinder, tube, and supplied-solid stock;
  - stock form and work coordinate system are separate from finished geometry.
- FreeCAD documentation, **Basic Attachment Tutorial**:
  https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Basic_Attachment_Tutorial.md
  - origin planes, datum geometry, and stable attachment choices are preferable
    to unnecessary references to generated faces/edges.
- SOLIDWORKS Help, **Sketch Status Conventions / Fully Defined Sketches**:
  https://help.solidworks.com/2026/English/SolidWorks/sldworks/c_Sketch_Status_Conventions.htm
  - fully defined sketches are a deliberate design state; under-defined status
    should be visible and understood rather than silently ignored.

## Additional feature-based CAD guidance

- Autodesk Fusion Help, **Modeling modes in Fusion**:
  https://help.autodesk.com/view/fusion360/ENU/?contextId=ASM-DESIGN-MODELING-MODES
  - parametric mode records sketches, construction geometry, named parameters,
    and feature relationships in an editable timeline;
  - direct modeling does not preserve the same feature relationships.
- SOLIDWORKS Help, **Design Intent**:
  https://help.solidworks.com/2024/English/SolidWorks/sldworks/t_Editing_Features.htm
  - editable feature definitions, sketches, and feature-order history are part of
    maintaining design intent; a static matching shape is not enough.
- SOLIDWORKS Help, **Fillet Overview**:
  https://help.solidworks.com/2025/English/SolidWorks/sldworks/c_FilletXpert_Overview.htm
  - cosmetic fillets are generally saved for late in the history; structural or
    functional fillets may need earlier placement.
- Onshape, **How to Avoid 3 Common CAD Sketching Mistakes**:
  https://www.onshape.com/en/resource-center/tech-tips/how-to-avoid-3-common-cad-sketching-mistakes
  - construction geometry and geometric relationships communicate design intent;
  - oversized sketches increase solver complexity;
  - functional sketch radii and cosmetic model fillets should be distinguished.
