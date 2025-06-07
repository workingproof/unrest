FROM python:3.12-slim

ARG DEBIAN_FRONTEND=noninteractive
ARG TZ=Etc/UTC

RUN apt update -y
RUN apt install -y curl libpq-dev gcc
RUN pip install -q -U pip poetry

WORKDIR /host
ADD pyproject.toml pyproject.toml
ADD poetry.lock poetry.lock
RUN poetry install --no-root

