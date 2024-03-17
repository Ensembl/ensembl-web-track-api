
- Review of previous meeting
Production will create CSV => data loading script
- Review of Track API payload
For the next update afper MVP
- Data loading/backup  plan
We will deploy a dedicated production RW Track API service in our cluster for Marc that is only available for a internal instance/auth token?
Deployed by Marc? => give docker image path/registry user/pswd, db params (new tag => creates image; test against stage) => action: ticket to next sprint
Versioning

Marc has script to update/regenerate token for GH/GL integration

Guvicorn env params (feature for TrackAPI): https://github.com/Ensembl/ensembl-production-services/blob/main/gunicorn.conf.py
Track payload creation for MVP: https://www.ebi.ac.uk/panda/jira/browse/ENSPROD-9401
Track API instance for data loading: https://www.ebi.ac.uk/panda/jira/browse/ENSPROD-9416

