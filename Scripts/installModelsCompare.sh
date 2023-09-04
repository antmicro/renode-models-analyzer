#!/usr/bin/env bash

# install ModelsCompare as a Python package, with runnable script

cd ModelsCompare/
rm -r build dist *.egg-info src/*.egg-info 2> /dev/null || true
pip3 install --user .
