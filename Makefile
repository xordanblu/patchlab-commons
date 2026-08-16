.PHONY: install test compile demo attack-demo doctor schema clean build coverage

install:
	python -m pip install -e .

test:
	python -m unittest discover -s tests -v

compile:
	python -m compileall -q src tests scripts

demo:
	python scripts/run_demo.py

attack-demo:
	python scripts/run_attack_demo.py

coverage:
	coverage run -m unittest discover -s tests -v
	coverage report --show-missing

doctor:
	patchlab doctor --repo . --config patchlab.toml

schema:
	patchlab schema --kind report --output docs/report.schema.json
	patchlab schema --kind passport --output docs/passport.schema.json

build:
	python -m build

clean:
	rm -rf build dist .patchlab src/*.egg-info src/patchlab_commons.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
