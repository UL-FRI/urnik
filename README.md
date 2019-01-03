# UL FRI timetabling system

Timetabling system is a web application written in Django. The main entry
point is the application `urnik_fri` which also contains settings module. 

The sample settings are separated into two parts: common and computer 
specific. New deployments should take `settings-example.py` as template and 
customize it.

All the necessary python dependencies are listed inside `requirements_development.txt`
and `requirements_production.txt`. Currently they are basically the same except 
versions are pinned in the `requirements_production.txt`. The current production
image is actually built from `requirements_development.txt` so we recommend to use
that one. 

The system dependencies can be read from the `Dockerfile`.  

## Developers

Timetabling system can be easily run under any linux system. Just install necessary
dependencies (python and system one) and run it as any other python application.

However, in order to ensure that all development environments are the same we recommend to
use Docker.

### Using Docker

In `Dockerfile` there are instructions on how to build a Docker image from this
repository. To run it we recommend running `docker-compose` agains the 
`docker-compose-development.yml` which runs the database and UWSGI server and sets
some environmental variables. 

To run it execute

`docker-compose -f docker-compose-development.yml up`

The command will start two docker containers: one running postgresql database 
and one running uwsgi server serving urnik.

The uwsgi server is by default exposed on the port 8080 on the host and the
current source code is mouted inside folder `/home/timetable/urnik` inside 
UWSGI container. The UWSGI is set to restart on code changes to make 
development easier.

Before system is operational the database and superuser must be
created using standard Django management commands. The easiest way 
to run management commands in it is to attach to the running docker
container using command similar to the one bellow.

`docker exec -it ${DOCKER_CONTAINER_ID} /bin/bash`


