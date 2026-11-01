.PHONY: check test-e2e bench lint format typecheck unit property integration ml llm security security-scan frontend coverage

# Windows-совместимо: все цели делегируют единому драйверу tools/run.py
PY := python

check:
	$(PY) tools/run.py check

test-e2e:
	$(PY) tools/run.py test-e2e

test-ml:
	$(PY) tools/run.py ml

bench:
	$(PY) tools/run.py bench

lint:
	$(PY) tools/run.py lint

format:
	$(PY) tools/run.py format

typecheck:
	$(PY) tools/run.py typecheck

unit:
	$(PY) tools/run.py unit

property:
	$(PY) tools/run.py property

integration:
	$(PY) tools/run.py integration

ml:
	$(PY) tools/run.py ml

llm:
	$(PY) tools/run.py llm

security:
	$(PY) tools/run.py security

security-scan:
	$(PY) tools/run.py security-scan

frontend:
	$(PY) tools/run.py frontend

coverage:
	$(PY) tools/run.py coverage
