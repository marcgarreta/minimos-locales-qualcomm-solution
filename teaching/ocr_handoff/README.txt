OCR AND FIGURE EXTRACTION — TEAM HANDOFF

This bundle prepares the English M3Kang questions for a solver. It includes
1,747 original question records and screenshots, our patched answer-zone OCR,
the 10.9 MB recognition model, and our diagram/choice crop exporter.
It does not run an LLM or produce predicted correct answers.

QUICK START (Python 3.11 or 3.12; tested with Python 3.12 on Linux)

Extract the entire ZIP, then enter the extracted ocr_handoff folder.
Linux/macOS:

    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python run_ocr.py --workers 4

Windows PowerShell:

    py -3.12 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv\Scripts\python.exe run_ocr.py --workers 4

Dependency installation needs internet. Extraction then runs offline on CPU.
Use --workers 1 if memory is limited. Keep all bundle folders together.

WHAT IT READS

    data/problems.jsonl       Original question text and dataset metadata
    data/images/<id>.png      Original English screenshots

The wrapper runs src/extract_answer_zone.py, then src/export_multimodal.py.
The OCR reads answer choices; the question text comes from the supplied JSONL.
This is the existing dataset preparation pipeline, not an adapter for arbitrary
hidden-exam JSON, PDFs, or other page layouts. To change inputs, preserve the
included problems.jsonl schema and supply matching PNGs in data/images.

WHAT TO GIVE YOUR SOLVER

    data/answer_zone_multimodal_all.jsonl
    data/answer_zone_multimodal_train.jsonl
    data/answer_zone_multimodal_val.jsonl
    data/images/
    data/multimodal/

Choose all, train, or val as appropriate; these are alternate manifests, not
three successive processing steps. Image paths are relative to data/.
Do not send only the JSONL if the solver needs figures.

Each row has text, A-E options, requires_vision, and selected image attachments.
Use the images list for separate crops. source_image selects the original page;
image_panel selects a combined panel. For grouped choices, use answer_panel with
the selected diagram. If answer_panel is absent, retain the selected images.
Do not select assets merely because files exist: candidate crops may be unused.
Uncertain separation explicitly falls back to the original page. Picture choices
are represented by images; placeholder option text is not an OCR transcription.

The existing official predict.py can consume text/options. To use the image
fields, the colleague's solver must load and pass those images to a vision model.
Our locally modified official runner supports this, but is not included here.
This package is preprocessing, not a complete challenge submission.

ALSO GENERATED

    data/answer_zone_extractions.jsonl    Raw OCR, boxes, warnings, provenance
    data/answer_zone_all.jsonl            Records with complete text options
    data/answer_zone_train.jsonl          Text-only train inputs without warnings
    data/answer_zone_val.jsonl            Text-only validation without warnings
    data/answer_zone_failures.jsonl       Incomplete text-option extractions
    results/answer_zone_summary.json
    results/answer_zone_multimodal_summary.json

The label field is the dataset's answer key, preserved for evaluation; it is not
predicted by OCR and must not be included in a solver's prompt. Generated files
are not an independently verified answer-key dataset. Warning-free OCR does not
guarantee correct transcription, and crops are not exhaustively reviewed.

Re-running reuses matching OCR cache entries and regenerates the exports/crops.
No LLM-generated image descriptions or per-question answer overrides are used.

PROVENANCE

SOURCES.json records source hashes, upstream revision, and the packaging change.
The copied OCR adapter differs only in how it reads the source revision: a text
file replaces a git command, so the ZIP works without Git or a .git directory.
The OCR, normalization, segmentation and cropping algorithms are unchanged.
The recognition model is PP-OCRv4, documented upstream as Apache-2.0.

This bundle includes research-only M3Kang data: share privately within the
datathon team. Do not upload the archive to a public repository.
