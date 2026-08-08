PYTHON := .venv/bin/python

.PHONY: test test-verbose demo gate clean

## Run the full engine test suite.
test:
	$(PYTHON) -m pytest

test-verbose:
	$(PYTHON) -m pytest -v --durations=10

## Print a worked example to stdout.
demo:
	$(PYTHON) -c "from engine import ProjectInputs, DebtTerms, run_model; \
	s, w, r = run_model(ProjectInputs(), DebtTerms()); \
	print(s.sizing.summary()); \
	print(f'IDC \$${s.construction.idc/1e6:,.1f}m  equity \$${s.equity/1e6:,.1f}m  IRR {r.equity_irr_post_tax:.2%}')"

## Gate: openpyxl must be able to write iterate="1".
gate:
	$(PYTHON) -c "import zipfile, tempfile, os, openpyxl; \
	from openpyxl.workbook.properties import CalcProperties; \
	wb = openpyxl.Workbook(); \
	wb.calculation = CalcProperties(calcId=124519, iterate=True, iterateCount=100, iterateDelta=0.0001, fullCalcOnLoad=True); \
	p = os.path.join(tempfile.mkdtemp(), 'gate.xlsx'); wb.save(p); \
	xml = zipfile.ZipFile(p).read('xl/workbook.xml').decode(); \
	assert 'iterate=\"1\"' in xml, 'GATE FAILED: openpyxl did not write iterate=1'; \
	print('GATE PASSED: openpyxl writes iterate=\"1\" into xl/workbook.xml')"

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
