#!/bin/sh

for b in $(git tag); do
    git checkout "$b"
    git checkout -b "perf/$b"
    git checkout master -- tests/performance/ Makefile
    make perf

    git stash
    git stash drop

    git checkout master
    git branch -D "perf/$b"
done
