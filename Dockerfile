FROM python:3.12-slim

ARG DEBIAN_FRONTEND=noninteractive
ARG TZ=Etc/UTC

RUN apt update -y
RUN apt install -y curl
RUN pip install -q -U pip poetry

RUN curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin/

WORKDIR /host
ADD pyproject.toml pyproject.toml
ADD poetry.lock poetry.lock
RUN poetry install --no-root

CMD [ "just", "serve" ]
