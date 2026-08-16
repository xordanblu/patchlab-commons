.PHONY: install install-dev test compile coverage demo attack-demo demos doctor schema checks quality build release-assets verify clean

install:
	python -I -m pip install --no-deps .

install-dev:
	python -I -m pip install -r requirements-dev.txt -e .

test:
	python -m unittest discover -s tests -v

compile:
	python -I -m compileall -q src tests scripts

coverage:
	coverage run --branch -m unittest discover -s tests -v
	coverage report --show-missing --fail-under=90

demo:
	python -I scripts/run_demo.py --output .patchlab/demo
	patchlab verify-passport .patchlab/demo/patchlab-passport.tar.gz

attack-demo:
	python -I scripts/run_attack_demo.py --output .patchlab/blocked-demo
	patchlab verify-passport .patchlab/blocked-demo/patchlab-passport.tar.gz

demos: demo attack-demo

doctor:
	patchlab doctor --repo . --config patchlab.toml

schema:
	patchlab schema --kind report --output docs/report.schema.json
	patchlab schema --kind passport --output docs/passport.schema.json

checks:
	python -I scripts/check_action_pins.py
	python -I scripts/check_release.py
	python -I -m json.tool docs/report.schema.json >/dev/null
	python -I -m json.tool docs/passport.schema.json >/dev/null
	git diff --check

quality:
	ruff check .
	ruff format --check .
	mypy
	bandit -r src scripts -ll
	actionlint -shellcheck="$$(command -v shellcheck)"
	shellcheck --version
	pip-audit --requirement requirements-runtime.txt

build:
	python -I -m build

test-release:
	twine check dist/*

release-assets:
	python -I scripts/build_release_assets.py --dist release

verify: compile test coverage demos checks

clean:
	rm -rf build dist release .patchlab src/*.egg-info src/patchlab_commons.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
