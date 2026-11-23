"""Generate a small, fictional research paper PDF used by the tests and the demo.

The content is invented for testing only. It is not a real paper.
Usage: python scripts/make_sample_pdf.py [output.pdf]
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

TITLE = "Sample Paper: Parameter-Efficient Fine-Tuning for Low-Resource Translation"

SECTIONS = [
    ("Abstract", [
        "This sample document is fictional and exists only to test PaperPilot. "
        "We study parameter-efficient fine-tuning for translation into low-resource languages. "
        "Using low-rank adapters, we train fewer than 12 percent of the parameters of the base model "
        "while keeping translation quality within 0.4 BLEU of full fine-tuning.",
    ]),
    ("1 Introduction", [
        "Full fine-tuning of large translation models is expensive for academic labs. "
        "Low-resource languages such as Telugu and Odia have limited parallel data, which makes "
        "overfitting a common problem when every weight is updated.",
        "Our contributions are threefold. First, we compare adapter ranks from 4 to 64. "
        "Second, we report training cost in GPU hours. Third, we release evaluation scripts.",
    ]),
    ("2 Method", [
        "We insert low-rank adapters into the attention projections of every transformer layer. "
        "The adapter rank is set to 16 unless stated otherwise, and the scaling factor alpha is 32. "
        "Only the adapter weights are trained; the base model stays frozen.",
        "Training uses the AdamW optimizer with a learning rate of 2e-4, a batch size of 32 and "
        "a linear warm-up over the first 500 steps.",
    ]),
    ("3 Experiments", [
        "We evaluate on an English to Telugu test set of 2,000 sentences. "
        "The dataset was split 80/10/10 into training, validation and test portions. "
        "All runs were performed on a single GPU with 24 GB of memory.",
    ]),
    ("4 Results", [
        "Rank 16 adapters reached 27.1 BLEU, compared with 27.5 BLEU for full fine-tuning. "
        "Training time fell from 41 GPU hours to 9 GPU hours. "
        "Ranks above 32 gave no further improvement.",
    ]),
    ("5 Limitations", [
        "We evaluated only one language pair and used automatic metrics. "
        "Human evaluation of fluency was not performed and is left for future work.",
    ]),
    ("6 Conclusion", [
        "Low-rank adapters make translation fine-tuning affordable for small labs with little loss in quality.",
    ]),
    ("References", [
        "[1] Example reference one. [2] Example reference two.",
    ]),
]


def build(path: Path) -> Path:
    styles = getSampleStyleSheet()
    story = [Paragraph(TITLE, styles["Title"]), Spacer(1, 12)]
    for heading, paragraphs in SECTIONS:
        if heading == "3 Experiments":
            story.append(PageBreak())  # spread content over two pages to test page tracking
        story.append(Paragraph(heading, styles["Heading2"]))
        for para in paragraphs:
            story.append(Paragraph(para, styles["BodyText"]))
            story.append(Spacer(1, 6))
    doc = SimpleDocTemplate(str(path), pagesize=A4, title=TITLE)
    doc.build(story)
    return path


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "sample_paper.pdf")
    print(build(out))
