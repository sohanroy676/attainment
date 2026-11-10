# Engine prototype (validation only, not the product)

Checks that the proposed config-driven engine reproduces the mentor's workbooks.

- `engine.py`: building-block steps (QuestionPass, Denominator, ChoiceSelect, PerStudentAverage, Bands, Combine, CO-to-PO), exact decimals.
- `run.py <course.xlsx> <folder with engine.py>`: runs the Deep Learning workbook under several rule sets. Output: `course-results.txt`.
- `batch2.py <batch.xlsx with charts stripped>`: recomputes the CSE 2021-25 PO roll-up. Output: `batch-results.txt`.

Key results: see section 2 of `../solution-design.md`.
