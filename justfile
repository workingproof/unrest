
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

get url:
	curl -v -H"Accept: application/json" -H"Authorization: Bearer secretapikey456" {{url}}

benchmark:
	#!/bin/sh
	#echo 'wrk.method = "POST"' > /tmp/script.lua
	# wrk -t4 -c200 -d30s -s/tmp/script.lua --latency http://localhost:8080/random
	# echo 'wrk.headers["Accept"] = "application/json"' > /tmp/script.lua
	# echo 'wrk.headers["Authorization"] = "Bearer secretapikey456"' >> /tmp/script.lua
	echo "UNREST"
	echo "------------------------------------------------------------"
	wrk -t5 -c10 -d30s -H"Accept: application/json" -H"Authorization: Bearer secretapikey456" --latency http://localhost:8080/random
	echo
	echo "FASTAPI"
	echo "------------------------------------------------------------"
	wrk -t5 -c10 -d30s -H"Accept: application/json" -H"Authorization: Bearer secretapikey456" --latency http://localhost:8081/random


