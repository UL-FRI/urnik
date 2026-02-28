# vim:set ft=dockerfile:
FROM debian:stable
LABEL maintainer="Gregor Jerše <gregor@jerse.info>"

ENV URNIK_GIT_LOCATION=https://github.com/ul-fri/urnik.git
ENV URNIK_GIT_BRANCH=master

# Secret key is only here to make collectstatic work.
# It is overrided from settings in docker-compose.
ENV SECRET_KEY=very_secret_key

# Add timetable user and group first to make sure their IDs get assigned consistently
RUN groupadd -r timetable \
  && useradd -r -g timetable -m -d /home/timetable timetable \
  && mkdir -p /home/timetable \
  && chown -R timetable:timetable /home/timetable
    
ENV LANG sl_SI.UTF-8
ENV LC_ALL sl_SI.UTF-8 

# Install required packages
RUN apt update \
  && apt-get install -y \
  python3 \
  python3-pip \
  git \
  postgresql-server-dev-all \
  libpython3-dev \
  libsasl2-dev \
  libldap2-dev \
  unixodbc-dev \
  libmariadb-dev \
  libpq-dev gcc \
  pwgen \
  fish \
  gettext \
  vim \
  nano \
  && rm -rf /var/lib/apt/lists/*


  
RUN pip3 install uv --break-system-packages 

WORKDIR /home/timetable
USER timetable
# When inside urnik repository just copy everything into 
# the appropriate subfolder.
COPY --chown=timetable:timetable . urnik/
COPY --chown=timetable:timetable wait-for-it.sh /


WORKDIR /home/timetable/urnik

RUN ls && uv sync

# Collect Django static files
RUN uv run python3 manage.py collectstatic --noinput --settings=urnik_fri.settings_example
RUN uv pip install uwsgi

# Chown everything to the user timetable
RUN chown -R timetable:timetable /home/timetable

# Make wait-for-it.sh as executable. It is used by testing image to wait
# for the database container to be online before the tests are ran.
RUN chmod +x /wait-for-it.sh

# Install jupyterlab for interactive work with the system.
# Make sure to not expose it to the public
RUN uv pip install jupyterlab jupyter_collaboration 


# Set JupyterLab password using jupyter_server.auth.security.set_password
#RUN uv run python3 -c "from jupyter_server.auth.security import set_password; set_password('$(pwgen 32 1)');"

RUN uv run --with jupyter jupyter lab --help



# UWSGI options are read from environmental variables.
# They are specified in docker-compose file.
CMD ["uv", "run", "uwsgi"]
