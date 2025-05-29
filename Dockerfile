# ref https://ep2020.europython.eu/media/conference/slides/CeKGczx-best-practices-for-production-ready-docker-packaging.pdf
# ref https://pythonspeed.com/articles/multi-stage-docker-python/

# builder outputs a virtualenv with installed dependencies
FROM python:3.11-slim-buster AS builder

# makes sure system is up-to-date
RUN apt-get update
RUN apt-get install -y --no-install-recommends build-essential git

# use regular user
RUN useradd --create-home app
USER app
WORKDIR /home/app

# creates a venv and install dependencies
RUN python -m venv venv
ENV PATH="./venv/bin:$PATH"
COPY requirements.txt .
COPY requirements.prod.txt .
RUN python -m pip install -U pip==24.0 setuptools wheel
RUN pip install -r requirements.txt
RUN pip install -r requirements.prod.txt

# runner intakes the builder's virtualenv, does various things and define an entrypoint
FROM python:3.11-slim-buster AS runner
ARG GIT_COMMIT
RUN test -n "$GIT_COMMIT"
ENV GIT_COMMIT=$GIT_COMMIT

# use regular user
RUN useradd --create-home app
USER app
WORKDIR /home/app

# intakes the virtualenv from builder
COPY --from=builder /home/app/venv ./venv

# copy in only neccessary files
COPY pillcity/ /home/app/pillcity
COPY app.py .
COPY release.py .
COPY entrypoint-worker.sh .
COPY entrypoint-release.sh .
COPY entrypoint-beat.sh .
COPY swagger.yaml .
COPY uwsgi.ini .

# pre-compile bytecode and enable PYTHONFAULTHANDLER (catches error in c)
ENV PATH="./venv/bin:$PATH"
ENV PYTHONFAULTHANDLER=1
EXPOSE 5000
ENTRYPOINT ["/home/app/venv/bin/uwsgi", "--ini", "uwsgi.ini"]
