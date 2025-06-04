

CXX ?= $(if $(shell which g++),g++)
CXXFLAGS = -Wall -Wextra -std=c++11 -DTELEPY_TEST

TEST_SRC = tree.cc

TEST_TARGET = tree_test

.PHONY: all clean test

all: $(TEST_TARGET)

$(TEST_TARGET): $(TEST_SRC)
	$(CXX) $(CXXFLAGS) $< -o $@

test: $(TEST_TARGET)
	./$(TEST_TARGET)

clean:
	rm -f $(TEST_TARGET)