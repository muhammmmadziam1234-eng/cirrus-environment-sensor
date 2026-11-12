# Cirrus C-01

Cirrus C-01 is a wall-mounted environmental sensor enclosure developed as an industrial design and assembly project. The editable assembly includes the enclosure, captive hardware, boards, compression gasket, wall cleat, and two studio cameras. The enclosure measures approximately **104 × 109 × 34 mm**, plus 8 mm for the cleat.

![Cirrus C-01 enclosure and exploded assembly](renders/exploded.png)

[Product campaign](https://github.com/muhammmmadziam1234-eng/cirrus-formline-ad-campaigns#cirrus)

## Open and explore

Open `cirrus.blend` in Blender 4.5.4. The file opens assembled. Select **Cirrus | Explode control** in the Outliner, then set **Object Properties → Custom Properties → Explode** from 0 to 1. The five assembly layers travel along the cover-removal axis. The scene includes **Camera · 01 Hero** and **Camera · 02 Exploded**, framed for their respective configurations.

## Engineering decisions

- The red-oxide grille has thirteen through-slots and a stand-off debris screen. The exposed sensing board sits in its own bay so ambient air reaches the sensor without passing over the main electronics. A silicone feedthrough carries the removable flex across the bulkhead.
- The molded rear locates a continuous gasket between two rails. The cover land closes over it with approximately 24% nominal compression. The four recessed screws stay with the cover and seat in brass inserts outside the sealed compartment.
- The cleat uses four slotted wall anchors and two sliding rails. The exploded view spreads the five layers along a shared axis for inspection. During service, the cleat slides vertically and the flex is released before the boards are lifted.
- The source uses centimetres internally, with enclosure dimensions and core clearances grouped near the top. Meshes, edge modifiers, material nodes, drivers, and type remain editable. The design is a geometry study with no ingress, environmental, or manufacturing qualification.

## Rebuild

Run this from the project folder. The script writes outputs beside itself and requires no external assets.

```powershell
blender --background --factory-startup --threads 6 --python-exit-code 1 --python build_cirrus.py
```

Add `-- --build-only` to save the scene without rendering or `-- --preview` for smaller proofs. The default build checks closed part geometry, the vent and fastener bores, board alignment, gasket compression, the explode drivers, and camera framing. Cycles produces a **1320 × 1320** hero and **1400 × 890** exploded view under `renders/`.
