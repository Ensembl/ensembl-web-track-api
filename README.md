# Track API endpoint.

A Django app for serving the available annotation tracks for Ensembl client.  
Expects: genome ID (URL param)  
Returns: list of track categories and tracks for a given genome (JSON)  
Reference dataset: ./data/track_categories.yaml

## Quick Start

1. Clone the repo:
    - `$ git clone https://gitlab.ebi.ac.uk/ensembl-web/ensembl-track-api.git`
    - `$ cd ensembl-track-api`

2. Build the database:
    - `$ docker-compose run web python manage.py makemigrations`
    - `$ docker-compose run web python manage.py migrate`
    - `$ docker-compose run web python ./utils/import_data.py`

3. Start the endpoint:
    - `$ docker-compose up` #add '-d' to run in background

4. Usage:
    - `http://localhost:8000/track_categories/:genome_id` #e.g. /track_categories/homo_sapiens_GCA_000001405_28
    - `http://2020.ensembl.org/api/tracks/track_categories/:genome_id` #when deployed to production

5. Stop the endpoint:
    - `$ docker-compose down` #or Crtl+C if running in foreground

## CI/CD and Kubernetes deployment

### Configuration

The GitLab CI/CD configuration file and the Kubernetes manifests in `k8s` dir define the deployment accross 2 clusters and 4 namespaces.
For each of the 8 environments, 5 manifest files are applied to deploy the app:

- Applied manually: `configmap.yaml`, `service.yaml`, `db_service.yaml`, `ingress.yaml`
- Applied by CI/CD jobs: `deployment.yaml`; for review apps, also: `review/service.yaml`, `review/ingress.yaml`

### Deployment stages

1. Push updates to a feature branch or `update` branch => review app is deployed. Open PR to `dev` branch.
    - Use feature branch for changes in code (uses external prod database) and `update` branch for changes in both code and track data (uses internal dev database).
2. Review app PR approved => merge to `dev` branch => deployed to staging
3. Merge `dev` branch to `main` => deployed to internal
4. Click run button for `Live` CI/CD job in GitLab => deployed to live

### Data updates

- Track data is served from an external postgres database in both datacenters (defined in `db_service.yaml`).
Since the database user for k8s cluster is read-only, the database build and data import commands are run from a local computer with a read/write database user (specified in `settings.py`), followed by granting data access for the r/o user (`utils/grant_access.sh`).
- Review apps from `update` branch use local database in k8s. Run `python utils/import_data.py` in the review app pod to update the data (data source: `data/track_categories.yaml`)
- Update relevant environment variables (see `settings.py`) before running data update scripts (e.g from a file: `export $(cat .env | xargs)`)
- Use `./manage.py sqlflush` and `./manage.py dbshell` to debug any database-related Django errors.
  - Flush database: run the database command from `sqlflush` (with system tables removed) in `dbshell` terminal
