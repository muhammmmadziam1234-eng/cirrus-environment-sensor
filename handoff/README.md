# Cirrus C-01 enclosure handoff

Nominal dimensions from the assembled cirrus.blend in assembly-local coordinates. X is width, Y is vertical and Z points out from the wall. The rear surface of the cleat defines the wall datum.

[Section A–A and seal detail](../renders/section.svg) · [Cleat elevation and rail section](../renders/mounting.svg) · [Measurement data](measurements.json)

| Feature | Model value | Datum or interpretation |
| --- | ---: | --- |
| Body envelope | 104 × 109 × 33.6 mm | Cover width × height × rear floor-to-face depth. |
| Mounted projection | 41.3 mm | Cleat back to molded face. The rear floor datum sits 7.7 mm forward of the cleat back. |
| Grille openings | 13 × 2.38 mm wide | 9.8–14 mm long. The individual lengths are in the measurement file. |
| Vent isolation offsets | 2.9 / 7.9 mm | Vertical distance from the upper bulkhead to the lower edge of the cover window / nearest slot tip. |
| Debris screen stand-off | 2.28 mm | From the rear of the grille to the forwardmost evaluated wire. The screen frame is excluded. |
| Feedthrough | 0.57 / 0.24 mm | Silicone slit height / modeled flex height at the feedthrough center. The profile leaves a nominal opening around the flex. |
| Gasket stack | 2.5 / 1.9 mm | Free gasket height / bulkhead seat-to-land distance. Both are measured along the enclosure depth axis. |
| Nominal axial squeeze | 0.6 mm · 24% | Free height minus seat-to-land distance, divided by free height for the percentage. Section D hatches the actual rigid mesh overlap. |
| Gasket rail channel | 2.36 mm | Nominal gap between the inner and outer rails at the upper straight, measured through the rail height. |
| Cleat anchors | 4 slots · 4.7 × 9.3 mm | Slot width × height on 40 × 61.6 mm center pitch. |
| Sliding rails | 58.6 mm pitch | 7.2 mm flange across a 5.8 mm throat, for 0.7 mm lip capture per side. |
| Rail clearances | 0.3 / 0.15 mm | Lateral flange-to-receiver clearance per side / axial flange-to-lip gap. |
| Removal travel | 52.25 mm | Upward shift from the assembled position until the receiver lips clear the fixed flanges, assuming the latch has already been released. Installation overhead needs its own allowance. |

## Measurement basis

Nominal dimensions use the underlying part meshes and Boolean openings. The sheets trace evaluated mesh sections, including bevels, and the screen and flex measurements use evaluated geometry. The section exporter uses a 0.001 mm numerical offset to avoid vertices that lie directly on the cut plane. Normal rays check all grille slots through the grille and cover window, and all four anchor slots through the cleat. The rail travel uses the flange upper end and the receiver lip lower end, measured in the assembled position.

## Study limits

Cirrus is an independent digital design study. The vent offsets describe spatial separation. The gasket calculation uses undeformed geometry, and the feedthrough fit leaves a modeled gap. Ingress protection, airflow, thermal and sensor response, gasket force and deformation, production tolerances, wall fastener selection and loading, latch actuation, and tool or hand access require separate validation.

See the [project README](../README.md#reproduce-and-verify) for rebuild and verification commands.
