
PKG_NAME = $(shell python setup.py --name)

build: compile_commands
	@python -m build

build_debug: compile_commands
	@export TELEPY_FLAGS="-g -O0 -DDEBUG" && export CFLAGS="-g -O0" && export CXXFLAGS="-g -O0" && python -m build


clean: uninstall
	make -C src/$(PKG_NAME)/telepysys clean
	rm -rf dist build compile_commands.json src/$(PKG_NAME).egg-info .coverage\.* *.svg *.folded

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

TEST_DIR := tests
TEST_FILES := $(shell find $(TEST_DIR) -maxdepth 1 -name 'test_*.py')

coverage:
	@start=$$(date +%s.%N); \
	for file in $(TEST_FILES); do \
		echo "Running $$file"; \
		TELEPY_SUPPRESS_OUTPUT=1 coverage run --parallel-mode --source=telepy -m unittest $$file || exit 1; \
	done; \
	coverage combine; \
	coverage report; \
	coverage html; \
	end=$$(date +%s.%N); \
	elapsed=$$(echo "$$end - $$start" | bc); \
	printf "COVERAGE TIME: %.3f seconds\n" $$elapsed

test:
	@start=$$(date +%s.%N); \
	make -C src/$(PKG_NAME)/telepysys test || exit 1; \
	for file in $(TEST_FILES); do \
		echo "Running $$file"; \
		TELEPY_SUPPRESS_OUTPUT=1 python -m unittest $$file || exit 1; \
	done; \
	end=$$(date +%s.%N); \
	elapsed=$$(echo "$$end - $$start" | bc); \
	printf "TEST TIME: %.3f seconds\n" $$elapsed

.PHONY: build clean install uninstall docs coverage
