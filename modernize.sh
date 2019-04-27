#!/bin/bash


# usage 
#   ./modernize.sh <fixername>

# Instructions
# run at the root of the project
# relies on silversearcher/ag 
# look at https://portingguide.readthedocs.io/en/latest/tools.html for order of 
# fixers to apply

# stop on errors
set -e

# read the fix 
if [ $# -eq 0 ]; then
    read -p "Please enter the fix: " fix 
    echo 
else
    fix=$1
fi

ag --python -g . | xargs python-modernize -wnf "$fix" 

ag -s "todo"
