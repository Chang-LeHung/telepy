
PKG_NAME = $(shell python setup.py --name)

build: compile_commands
	python -m build

clean: uninstall
	rm -rf dist build compile_commands.json src/$(PKG_NAME).egg-info .coverage*

install:
	pip install .

docs:
	make -C docs html

clear_docs:
	make -C docs clean

compile_commands:
	bear -- python setup.py build_ext --inplace

coverage:
	coverage run --source=telepy -m unittest discover -s tests
	coverage report
	coverage html

uninstall:
	pip uninstall -y $(PKG_NAME)

test:
	python -m unittest discover -s tests

.PHONY: build clean install uninstall docs
