
set dotenv-load := true
#set dotenv-required := true
#set quiet

_default:
	just --list

# Start the test DB
up:
	sudo docker-compose up -d

# Reset the database
reset:
	poetry run unrest db reset

# Apply any outstanding migrations
apply:
	poetry run unrest db apply

# Run the test suite
test: up reset
	poetry run pytest

# Generate documentation
docs *IGNORED:
	#!/usr/bin/env sh
	# if [ tests/quickstart.py -nt docs/quickstart.md ] || [ README.tmpl -nt README.md ];
	if true; then													 
		awk '!/^#/ { print }									\ 
			  /^#:end/ { sub(/^#:end/, "```\n", $0); print $0 }	 \
			  /^#:/  { sub(/^#:/, "\n```", $0); print $$0 }	 \
			  /^#/ { sub(/^# */, "", $0); print $0 }'		 \
			  tests/quickstart.py > docs/quickstart.md			
		cat README.tmpl > README.md							
		cat docs/quickstart.md >> README.md					 
		git add docs/quickstart.md							   
		git add README.md									 
	fi											

docserve:
	poetry run mkdocs serve

benchmark:
	#!/bin/sh
	echo 'wrk.method = "POST"' > /tmp/script.lua
	wrk -t4 -c200 -d30s -s/tmp/script.lua --latency http://localhost:8080/test/random

