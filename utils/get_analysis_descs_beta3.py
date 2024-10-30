"""
A simple script to fetch the analysis descriptions for genes
out of core DBs to feed into the new genome browser (MVP/Beta).

Species scope is determined by appropriate choice of the 'metadata DB'
and the RELEASE ID. This latter one must be given by Production.
E.g. RELEASE_ID = 2 represents 'beta-2'

WARNING: it contains hardcoded data. Barely tested.
USE AT YOUR OWN RISK!
"""
from dataclasses import dataclass
from string import Template
import csv
from mysql.connector import connection

# CHECK cfg below with Production!!!
META_HOST = 'mysql-ens-production-1'
META_PORT = 4721
META_DB   = 'ensembl_genome_metadata'
RELEASE_ID = 2 # this is a magic number known by Production

HOST = 'mysql-ens-sta-6.ebi.ac.uk'
PORT = 4695
CSV_DELIMITER = '\t'
OUTFILENAME = 'protodesc_beta2.txt'

@dataclass
class SrcInfo:
    """Class for keeping track of geneset source info"""
    source_name: str
    source_url: str
    is_ensembl_anno: bool

def get_metadb_connection(username='ensro', password=''):
    return connection.MySQLConnection(user=username, password=password,
                                 host=META_HOST, port=META_PORT,
                                 database=META_DB)

def get_connection(username, password, dbname=None):
    if dbname is None:
        return connection.MySQLConnection(user=username, password=password,
                                 host=HOST, port=PORT)
    return connection.MySQLConnection(user=username, password=password,
                                 host=HOST, port=PORT,
                                 database=dbname)

def get_ensro_connection(dbname=None):
    return get_connection(username='ensro', password='', dbname=dbname)

def get_dbs(conx):
    cursor = conx.cursor()
    t = Template(
        """select g.production_name,g.genome_uuid,dss.name from genome g
        join genome_release gr using(genome_id)
        join genome_dataset gd using(genome_id)
        join dataset ds using(dataset_id)
        join dataset_source dss using(dataset_source_id)
        where gr.release_id = $release_id
        and gd.release_id = $release_id
        and ds.dataset_type_id = 2
        """)
    cursor.execute(t.substitute(release_id=RELEASE_ID))
    dbs = cursor.fetchall()
    return dbs

def get_analysis_src_info(conx, dbname) -> SrcInfo:
    cursor = conx.cursor()

    t = Template(
        """select species_id,
           max(case when meta_key = 'genebuild.annotation_source' then meta_value else null end),
           max(case when meta_key = 'genebuild.provider_name' then meta_value else null end),
           max(case when meta_key = 'genebuild.provider_url' then meta_value else null end)
           from $dbname.meta m
           where m.meta_key in ('genebuild.annotation_source','genebuild.provider_name','genebuild.provider_url')
           group by species_id;
        """)

    cursor.execute(t.substitute(dbname=dbname))
    r = cursor.fetchone()
    is_ensembl_anno = str(r[1]).lower() == 'ensembl'
    return SrcInfo(source_name=r[2], source_url=r[3], is_ensembl_anno=is_ensembl_anno)

def dump_data(data: list[dict[str,str]], filename: str = OUTFILENAME) -> None:
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Species', 'Genome_UUID', 'DB_name', 'Source_name', 'Source_URL','Annotated_imported']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames,
                                delimiter=CSV_DELIMITER, quoting=csv.QUOTE_MINIMAL, dialect='unix')
        writer.writeheader()
        for item in data:
            writer.writerow(item)

def main():
    conx = get_metadb_connection()
    dbs = get_dbs(conx)
    conx.close()

    conx = get_ensro_connection()

    descriptions = []

    for db in dbs:
        dbname = db[2]
        print(f"Working on: {dbname}")
        src_info = get_analysis_src_info(conx, dbname)
        ensembl_imported = 'Annotated' if src_info.is_ensembl_anno else 'Imported'
        descriptions.append({'Species': db[0],
                             'Genome_UUID': db[1],
                             'DB_name': dbname,
                             'Source_name': src_info.source_name,
                             'Source_URL': src_info.source_url,
                             'Annotated_imported': ensembl_imported})

    conx.close()

    dump_data(descriptions)

if __name__ == "__main__":
    main()