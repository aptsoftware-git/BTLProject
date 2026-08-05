# Document Viewer Expansion Plan & Visual Enhancements

## 1. Executive Overview

The **Document Viewer Expansion Plan** establishes the original PDF document as the central focus of the Proofreading workspace. By converting side panels into collapsible drawers and removing fixed 3-column layouts, the viewport canvas expands to occupy **80%–90%+ of the available workspace width** (and up to 100% when drawers are closed).

```
+-------------------------------------------------------------------------------+
|  📄 Original PDF Viewport (Expanded 80-90%+ Width)                           |
|  [ 📄 PDF + Overlay | 📝 Text View ]   [ - 100% + ]   [ ◀ Page 1 of 216 ▶ ]   |
|                                                                               |
|  ===========================================================================  |
|  |                                                                         |  |
|  |   Annual Financial Report - Executive Overview                          |  |
|  |   Full visual fidelity: Vector tables, logos, figures & multi-columns   |  |
|  |                                                                         |  |
|  ===========================================================================  |
+-------------------------------------------------------------------------------+
```

---

## 2. Canvas Expansion & Space Metrics

| Workspace Parameter | Legacy Constrained Layout | Redesigned Expanded Layout | Net Real Estate Expansion |
| :--- | :--- | :--- | :--- |
| **Document Viewport Width** | 680px – 820px | **1450px – 1850px** | **+115% Real Estate Increase** |
| **Viewport Canvas Height** | 550px | **780px – 900px (`calc(100vh - 165px)`)** | **+50% Height Increase** |
| **Card Padding & Margins** | 24px inner / 20px outer | 8px inner / 0px outer | **36px Reclaimed Per Edge** |
| **Need for Horizontal Zoom**| High (Text squished) | Zero (Readable at 100% scale) | **Optimal Ergonomics** |

---

## 3. High-Density Enterprise Reading Controls

1. **Integrated Header Controls**:
   - Document Title & Page Count Badge (`📄 annual_report.pdf • 216 Pages`).
   - Dual Viewport Mode Selector: `📄 Original PDF + Highlights` vs `📝 Layout Text View`.
   - Precision Zoom Engine: `-`, `+`, `Reset Zoom`, Scale Presets ($50\%, 75\%, 100\%, 125\%, 150\%, 200\%$, Fit Page, Fit Width).
   - Page Navigation Controls: `◀ Page X of Y ▶` with jump-to-page input.
2. **Metadata Drawer Trigger**:
   - Prominent header button: `ℹ️ Document Info` opens the collapsible metadata drawer containing pipeline stage details, upload date, file size, and background job telemetry without taking up horizontal screen space.

---

## 4. Product Parity Target

The expanded layout provides an experience comparable to industry-standard document platforms:
- **Adobe Acrobat AI Review**: Primary document canvas with floating review panel and contextual overlays.
- **Microsoft Word Review Mode**: Full-page manuscript view with expandable inline tracking.
- **Enterprise Document Intelligence**: Maximum visual context preservation for 100+ page technical & financial PDF reports.
