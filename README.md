# UL FRI timetabling system

Timetabling system is a web application written in Django.  

## Developers

### Using Docker

Install docker-compose and run

`docker-compose -f docker-compose-development.yml up`

in order to build and run the timetabling system. The command
starts two docker containers: one running postgresql database 
and one running uwsgi server serving urnik.

The uwsgi server is by default exposed on the port 8080 on host. 
Before system is operational the database and superuser must be
created using standard Django management commands. 

The Django application itself is installed in the 
subdirectory `/home/timetable/urnik`. The easiest way to run management
commands in it is to attach to the running docker container using
command similar to the one bellow.

`docker exec -it ${DOCKER_CONTAINER_ID} /bin/bash`


