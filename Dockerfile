FROM python:3
RUN pip3 install Flask requests
RUN mkdir -p /usr/src/Site
WORKDIR /usr/src/Site

COPY . /usr/src/Site
ENTRYPOINT ["python3", "-m", "PugHelpBot"]
