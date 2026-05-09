from __future__ import annotations

from orchestration.evaluate_latex_book import evaluate_latex_book


def test_evaluator_penalizes_pdf_artifacts_for_course_books(tmp_path) -> None:
    tex = tmp_path / "book.tex"
    tex.write_text(
        r"""
\documentclass{scrbook}
\begin{document}
\chapter{Matrices}
\section{Element-wise calculation}
Each element C<sub>ij</sub> is calculated from rows and columns.
There appears to be an error in the previous calculation.
\subsection*{Further Reading}
file:///app/.cache/uploads/private.pdf
\end{document}
""",
        encoding="utf-8",
    )

    evaluation = evaluate_latex_book(tex)

    assert evaluation["totals"]["raw_html_math_tags"] == 2
    assert evaluation["totals"]["private_source_paths"] >= 1
    assert evaluation["totals"]["self_correction_phrases"] == 1
    assert evaluation["quality_score"] < 40
    assert any("raw HTML" in item for item in evaluation["recommendations"])
