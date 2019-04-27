#!/bin/bash

# run this from the root of the project

find . -regex '^.*\(__pycache__\|\.py[co]\)$' | rg -v 'venv'

# if you are happy with the files listed add the following
# | _ xargs rm -rf
