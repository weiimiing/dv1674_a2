# Author: David Holmqvist <daae19@student.bth.se>

CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -g -Wall -Wextra -Wpedantic
THREAD_FLAGS := -pthread

.PHONY: all clean

all: pearson pearson_par verify

pearson: vector dataset analysis pearson.cpp 
	$(CXX) $(CXXFLAGS) $(THREAD_FLAGS) pearson.cpp vector.o dataset.o analysis.o -o pearson

pearson_par: vector dataset analysis pearson_par.cpp
	$(CXX) $(CXXFLAGS) $(THREAD_FLAGS) pearson_par.cpp vector.o dataset.o analysis.o -o pearson_par

analysis: vector analysis.hpp analysis.cpp
	$(CXX) $(CXXFLAGS) $(THREAD_FLAGS) -c analysis.cpp -o analysis.o

dataset: vector dataset.hpp dataset.cpp
	$(CXX) $(CXXFLAGS) -c dataset.cpp -o dataset.o

vector: vector.hpp vector.cpp
	$(CXX) $(CXXFLAGS) -c vector.cpp -o vector.o

verify: verify.c
	$(CC) verify.c -o verify

clean:
	rm -rf verify pearson pearson_par *.o *.dSYM 2> /dev/null
	
