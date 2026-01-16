
set dotenv-load := true
#set dotenv-required := true
#set quiet

_default:
	just --list

logs:
    #!/bin/sh
    # docker compose logs --no-log-prefix --tail=100 -f quickstart | grep '^{' | jq '.'
    docker compose logs --no-log-prefix --tail=100 -f quickstart | jq '.'

# Reset the database
reset:
	poetry run unrest db reset

# Apply any outstanding migrations
apply:
	poetry run unrest db apply

# Run the test suite
test: reset
	poetry run pytest -o log_cli=true

# Generate documentation
tutorial:
	#!/usr/bin/env sh
	# watch -d -t -g ls -l tests/quickstart.py
	while true; do
		if [ tests/quickstart.py -nt docs/tutorial.md ]; then 
			awk '!/^#/ { print }									\
				/^#:end/ { sub(/^#:end/, "```\n", $0); print $0 }	 \
				/^#:/  { sub(/^#:/, "\n```", $0); print $$0 }	 \
				/^#/ { sub(/^# */, "", $0); print $0 }'		 \
				tests/quickstart.py > docs/tutorial.md										 
		fi
		sleep 1
	done											

docs:
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


