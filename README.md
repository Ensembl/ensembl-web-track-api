## Track API endpoint.

A Django app for serving the available annotation tracks for Ensembl 2020 client.  
Expects: genome ID (URL param)  
Returns: list of track categories and tracks for a given genome (JSON)  
Reference dataset: ./data/track_categories.yaml

### Quick Start

1. Clone the repo:

- `$ git clone https://gitlab.ebi.ac.uk/ensembl-web/ensembl-track-api.git`
- `$ cd ensembl-track-api`

2. Build the database:

- `$ docker-compose run web python manage.py makemigrations`
- `$ docker-compose run web python manage.py migrate`
- `$ docker-compose run web python ./utils/import_data.py`

3. Start the endpoint:

- `$ docker-compose up` #add '-d' to run in background

3. Usage:

- `http://localhost:8000/track_categories/:genome_id` #e.g. /track_categories/homo_sapiens_GCA_000001405_28
- `http://2020.ensembl.org/api/track/track_categories/:genome_id` #when deployed to production

4. Stop the endpoint:

- `$ docker-compose down` #or Crtl+C if running in foreground

### CI/CD and Kubernetes deployment

_Configuration:_
The GitLab CI/CD configuration file and the Kubernetes manifests in `k8s` dir define the deployment accross 2 clusters and 4 namespaces.
For each of the 8 environments, 5 manifest files are applied to deploy the app:
- Applied manually: `configmap.yaml`, `service.yaml`, `db_service.yaml`, `ingress.yaml`
- Applied by CI/CD jobs: `deployment.yaml`; for review apps, also: `review/service.yaml`, `review/ingress.yaml`

_Deployment stages:_
1. Push updates to feature branch or dev branch => review app is deployed. Use feature branch for changes in code data (review app uses dadtabase in k8s cluster) and dev branch for changes in code only (uses external db). Open PR to main branch.
2. Review app PR approved => merged to main branch => deployed to staging and internal
3. Internal deployment approved => run the deployment button in GitLab => main branch deployed to live

_Data updates:_
- The data is served from an external postgres database in both k8s clusters (defined in `db_service.yaml`).
Since the database user for k8s cluster is read-only, the database build and data import commands are run from a local computer with a read/write database user (specified in `settings.py`), followed by granting data access for the r/o user (`utils/grant_access.sh`).
- Review apps from feature branch use local database in k8s. Run `python utils/import_data.py` in the review app pod to update the data (data source: `data/track_categories.yaml`)
- Use `./manage.py sqlflush` and `./manage.py dbshell` to address any database-related Django errors.