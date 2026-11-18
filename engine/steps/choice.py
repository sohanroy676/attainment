"""ChoiceSelect: keep the best N questions (and best K parts of a question) per student.

Ranking is by question total, highest first; a tie goes to the lower question number (the one
that comes first on the paper). Dropped answers become State.DROPPED and are logged. A student
who answered fewer than N questions loses nothing. Only entered marks count as answered.
"""

from decimal import Decimal

from ..model import AssessmentInput, Cell, Part, State
from ..schema import ChoiceRule
from ..trace import Trace
from .normalise import Cells


def choice_select(
    assessment: AssessmentInput, cells: Cells, rules: dict[str, ChoiceRule], trace: Trace
) -> Cells:
    """Apply each choice group's rule to every student. `cells` is modified and returned."""
    for group, rule in rules.items():
        questions = _questions_in_group(assessment.parts, group)
        for student in sorted(cells):
            _select_for_student(assessment.tool, student, cells[student], questions, rule, trace)
    return cells


def _select_for_student(
    tool: str,
    student: str,
    row: dict[str, Cell],
    questions: dict[str, list[Part]],
    rule: ChoiceRule,
    trace: Trace,
) -> None:
    totals: dict[str, Decimal] = {}
    for question, parts in questions.items():
        answered = [p for p in parts if _answered(row.get(p.id))]
        if not answered:
            continue
        keep = rule.best_k_parts.get(question)
        if keep is not None and len(answered) > keep:
            # best K parts by mark; equal marks keep the earlier part
            ranked = sorted(enumerate(answered), key=lambda x: (-_mark(row[x[1].id]), x[0]))
            kept_ids = {answered[i].id for i, _ in ranked[:keep]}
            for part in answered:
                if part.id not in kept_ids:
                    row[part.id] = Cell(State.DROPPED, row[part.id].value)
                    trace.add(
                        "ChoiceSelect",
                        f"{tool}/{student}/{part.id}",
                        f"Q{question} part {part.id} dropped (best {keep} parts kept)",
                    )
            answered = [p for p in answered if p.id in kept_ids]
        totals[question] = sum((_mark(row[p.id]) for p in answered), Decimal(0))

    paper_order = {question: i for i, question in enumerate(questions)}
    ranking = sorted(totals, key=lambda q: (-totals[q], paper_order[q]))
    for question in ranking[rule.best_n :]:
        for part in questions[question]:
            if _answered(row.get(part.id)):
                row[part.id] = Cell(State.DROPPED, row[part.id].value)
        trace.add(
            "ChoiceSelect",
            f"{tool}/{student}/Q{question}",
            f"Q{question} (total {totals[question]}) dropped: best {rule.best_n} kept",
        )


def _questions_in_group(parts: tuple[Part, ...], group: str) -> dict[str, list[Part]]:
    questions: dict[str, list[Part]] = {}
    for part in parts:
        if part.choice_group == group:
            questions.setdefault(part.question, []).append(part)
    return questions


def _answered(cell: Cell | None) -> bool:
    return cell is not None and cell.state is State.ENTERED and cell.value is not None


def _mark(cell: Cell) -> Decimal:
    return cell.value if cell.value is not None else Decimal(0)
