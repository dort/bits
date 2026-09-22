# Augmented Lagrangian Predictive Coding — presentation package

The presentation is designed for 27 minutes of prepared material and 3 minutes of discussion. Slides 21–26 are optional technical backup.

## Files

- `ALPC_FabricPC_presentation.pptx`: editable widescreen slides with private PowerPoint speaker notes.
- `ALPC_FabricPC_slides.pdf`: audience-facing slides only, including backup slides.
- `ALPC_FabricPC_speaker_guide.pdf`: detailed, separate presenter guide.
- `ALPC_FabricPC_speaker_guide.docx`: editable presenter guide.
- `ALPC_FabricPC_speaker_guide.md`: plain-text source of the presenter guide.
- `slide_contact_sheet.png`: overview for checking the deck.
- `build_presentation.py` and `content.py`: reproducible presentation sources.
- `assets/`: extracted paper figures, equation images, and the independently computed scalar example.

Use PowerPoint's Presenter View to display the private notes on your own screen. Present the slide PDF if you want a format that contains no presenter notes. In the guide, “Talk track” is the material to use during the allotted time; “From first principles / preparation” is additional preparation, not extra text to read aloud. Main slide 20 is the discussion stop; advance beyond it only for backup material.

## Scope and provenance

Primary paper: Jeffrey Seely and Julian Gould, *Augmented Lagrangian Predictive Coding*, arXiv:2605.31022v1, 29 May 2026. The supplied local PDF is the source of the paper analysis and reproduced figures.

ePC: Cédric Goemaere, Gaspard Oliviers, Rafal Bogacz, and Thomas Demeester, *ePC: Fast and Deep Predictive Coding in Digital Simulation*, arXiv:2505.20137. The comparison is grounded primarily in the FabricPC implementation.

FabricPC was inspected at commit `8406e6a838442391fd3089958e1a2c1b44c57eda`, retrieved 22 September 2026 from <https://github.com/trueagi-io/FabricPC>. The clone is in `/tmp/alm-FabricPC-20260922`. No FabricPC source was changed. This package contains an integration proposal, not an implemented solver or a new benchmark of the library.

The scalar example is independently derived and numerically checked. Paper results are labeled as reported results. Proposed experiments and engineering judgments are explicitly identified.

## Rebuild

Requires Python 3.12 with `python-pptx`, `matplotlib`, `numpy`, `pymupdf`, `reportlab`, `python-docx`, and `Pillow`. The temporary build environment is `/tmp/alm-slides-venv`.

```bash
/tmp/alm-slides-venv/bin/python presentation/build_presentation.py
```

The PowerPoint uses editable text and shapes, with rasterized mathematical notation and plots. The PDF is generated from the same positioned content. Slide fonts are Lato; equations use DejaVu Sans math. Installed-font substitution can slightly change PowerPoint rendering on other computers.
