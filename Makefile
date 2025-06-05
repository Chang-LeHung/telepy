
PKG_NAME = $(shell python setup.py --name)

build: compile_commands
	@python -m build

build_debug: compile_commands
	@export TELEPY_FLAGS="-g -O0 -DDEBUG" && export CFLAGS="-g -O0" && export CXXFLAGS="-g -O0" && python -m build


clean: uninstall
	make -C src/$(PKG_NAME)/telepysys clean
	rm -rf dist build compile_commands.json src/$(PKG_NAME).egg-info .coverage*

install:
	@pip install .

uninstall:
	pip uninstall $(PKG_NAME)

docs:
	@make -C docs html

clear_docs:
	@make -C docs clean

compile_commands:
	@export TELEPY_FLAGS="-DTELEPY_TEST -g -O0" && bear -- python setup.py build_ext --inplace

coverage:
	coverage run --source=telepy -m unittest discover -s tests
	coverage report
	coverage html

test:
	make -C src/$(PKG_NAME)/telepysys test
	@python -m unittest discover -s tests -v

.PHONY: build clean install uninstall docs
