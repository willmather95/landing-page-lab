PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: install demo test test-fast calibrate preview clean

$(BIN)/lpl:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q -e ".[dev]"

install: $(BIN)/lpl

demo: install            ## brief -> 3 variants -> 21 simulated days -> readout + hero chart + screenshots
	$(BIN)/lpl demo --brief examples/brief.yaml --out out/demo --docs docs
	@echo; sed -n '1,4p' out/demo/readout.md

test: install
	$(BIN)/pytest -q

test-fast: install       ## skip the many-seed simulation tests
	$(BIN)/pytest -q -m "not slow"

calibrate: install
	$(BIN)/lpl calibrate --seeds 300 --out docs/calibration.md

preview: install
	$(BIN)/lpl preview out/demo/dist

clean:
	rm -rf out dist .pytest_cache
