# vim:set ft=dockerfile:
FROM debian:stable
LABEL maintainer="Gregor Jerše <gregor@jerse.info>"

ENV URNIK_GIT_LOCATION=https://github.com/ul-fri/urnik.git
ENV URNIK_GIT_BRANCH=master

# Secret key is only here to make collectstatic work.
# It is overrided from settings in docker-compose.
ENV SECRET_KEY=very_secret_key

# Add timetable user and group first to make sure their IDs get assigned consistently
RUN groupadd -r timetable && useradd -r -g timetable timetable

# Change locale to sl_SI.UTF-8
RUN apt update && DEBIAN_FRONTEND=noninteractive apt install -y locales

RUN sed -i -e 's/# sl_SI.UTF-8 UTF-8/sl_SI.UTF-8 UTF-8/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales && \
    update-locale LANG=sl_SI.UTF-8
    
ENV LANG sl_SI.UTF-8
ENV LC_ALL sl_SI.UTF-8 

# Install required packages
RUN apt update \
  && apt-get install -y \
  uwsgi \
  uwsgi-plugin-python3 \
  python3 \
  python3-pip \
  git \
  postgresql-server-dev-all \
  libpython3-dev \
  libsasl2-dev \
  libldap2-dev \
  unixodbc-dev \
  libmariadb-dev \
  && rm -rf /var/lib/apt/lists/*


WORKDIR /home/timetable

# Pull tomo source into current working directory
# RUN git clone -b ${URNIK_GIT_BRANCH} ${URNIK_GIT_LOCATION}

# When inside urnik repository just copy everything into 
# the appropriate subfolder.
COPY --chown=timetable:timetable . urnik/
COPY --chown=timetable:timetable wait-for-it.sh /

# Install dependencies
RUN pip3 install -r urnik/requirements_production.txt --break-system-packages
RUN pip3 install --upgrade --force-reinstall  pyldap --break-system-packages

# Collect Django static files
RUN python3 urnik/manage.py collectstatic --noinput --settings=urnik_fri.settings_example

# Chown everything to the user timetable
RUN chown timetable.timetable -R /home/timetable

# Make wait-for-it.sh as executable. It is used by testing image to wait
# for the database container to be online before the tests are ran.
RUN chmod +x /wait-for-it.sh

# UWSGI options are read from environmental variables.
# They are specified in docker-compose file.
CMD ["uwsgi"]
