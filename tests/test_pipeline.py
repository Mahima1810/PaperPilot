import pytest

from app.answerer import NOT_FOUND, answer_question, extractive_answer, verify_citations
from app.chunker import chunk_document
from app.llm import LLMError
from app.pdf_parser import PDFParseError, parse_pdf
from app.retriever import HybridRetriever


class FakeClient:
    """Stands in for the LLM so tests are deterministic and offline."""

    def __init__(self, reply: str | None = None, fail: bool = False):
        self.reply, self.fail = reply, fail

    def complete(self, system: str, user: str) -> str:
        if self.fail:
            raise LLMError("connection refused")
        return self.reply


@pytest.fixture(scope="module")
def retriever(sample_pdf_bytes):
    return HybridRetriever(chunk_document(parse_pdf(sample_pdf_bytes)))


def test_parser_finds_sections_and_pages(sample_pdf_bytes):
    doc = parse_pdf(sample_pdf_bytes)
    titles = [s.title for s in doc.sections]
    assert "Abstract" in titles
    assert "2 Method" in titles
    assert "4 Results" in titles
    assert doc.num_pages == 2
    experiments = next(s for s in doc.sections if s.title == "3 Experiments")
    assert experiments.page_start == 2


def test_references_are_not_chunked(sample_pdf_bytes):
    chunks = chunk_document(parse_pdf(sample_pdf_bytes))
    assert chunks
    assert all(c.section != "References" for c in chunks)


def test_invalid_pdf_raises():
    with pytest.raises(PDFParseError):
        parse_pdf(b"%PDF-1.4 not really a pdf")


@pytest.mark.parametrize(
    "question, expected_section",
    [
        ("What learning rate and optimizer were used?", "2 Method"),
        ("How many BLEU points did rank 16 adapters reach?", "4 Results"),
        ("What are the limitations of the study?", "5 Limitations"),
    ],
)
def test_retrieval_ranks_right_section_first(retriever, question, expected_section):
    hits = retriever.search(question, k=3)
    assert hits[0].chunk.section == expected_section


def test_extractive_answer_cites_real_passage(retriever):
    hits = retriever.search("What learning rate was used?", k=3)
    ans = extractive_answer("What learning rate was used?", hits)
    assert ans.mode == "extractive"
    assert "2e-4" in ans.answer
    assert ans.citations and ans.citations[0].section == "2 Method"


def test_unrelated_question_is_not_answered(retriever):
    hits = retriever.search("zebra migration patterns savanna", k=3)
    ans = answer_question("zebra migration patterns savanna", hits, client=None)
    assert ans.answer == NOT_FOUND


def test_verify_citations_drops_out_of_range():
    text, valid = verify_citations("Rank 16 works best [1, 7]. It is fast [9].", n_passages=3)
    assert valid == {1}
    assert "[7]" not in text and "[9]" not in text
    assert "[1]" in text


def test_llm_answer_with_valid_citation_is_kept(retriever):
    hits = retriever.search("How many GPU hours did training take?", k=3)
    ans = answer_question("q", hits, FakeClient("Training took 9 GPU hours [1]."))
    assert ans.mode == "llm"
    assert ans.citations[0].n == 1


def test_llm_answer_without_citations_falls_back(retriever):
    q = "How many GPU hours did training take?"
    hits = retriever.search(q, k=3)
    ans = answer_question(q, hits, FakeClient("It took about a week."))
    assert ans.mode == "extractive"
    assert ans.warning


def test_llm_failure_falls_back(retriever):
    q = "What batch size was used?"
    ans = answer_question(q, retriever.search(q, k=3), FakeClient(fail=True))
    assert ans.mode == "extractive"
    assert "LLM unavailable" in ans.warning


def test_extractive_answer_skips_overlapping_duplicates():
    from app.chunker import Chunk
    from app.retriever import Hit

    full = "The key difference is that adapters add latency at inference time."
    cut = "key difference is that adapters add latency at inference time."
    hits = [
        Hit(Chunk("c0", "Intro", 1, 1, full), 0.03, 1.0, 0.5),
        Hit(Chunk("c1", "Intro", 1, 1, cut), 0.02, 1.0, 0.5),
    ]
    ans = extractive_answer("What adds latency at inference?", hits)
    assert ans.answer.count("adapters add latency") == 1


def test_paper_reference_numbers_are_not_citations():
    from app.answerer import neutralize_refs

    assert neutralize_refs("We used Adam [20] and dropout [3, 4].") == "We used Adam (ref. 20) and dropout (ref. 3, 4)."


@pytest.mark.parametrize(
    "question, expected_section",
    [("What are the main results?", "Results"), ("What are the limitations?", "Limitations")],
)
def test_section_heading_counts_as_a_match(retriever, question, expected_section):
    # Body sentences in "4 Results" never say "results"; the heading alone must be enough to answer.
    answer = answer_question(question, retriever.search(question, k=5), None)
    assert answer.mode == "extractive"
    assert expected_section in answer.citations[0].section


def test_plural_question_matches_singular_text(retriever):
    answer = answer_question("What datasets were used?", retriever.search("What datasets were used?", k=5), None)
    assert any("Experiments" in c.section for c in answer.citations)
