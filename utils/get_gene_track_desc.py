"""
A simple script to fetch the analysis descriptions for genes
out of core DBs to feed into the new genome browser (MVP/Beta).

Species scope is determined by appropriate choice of the 'metadata DB'
and the 'release ID'. This latter one must be given by Automation.
E.g. release_id = 3 represents 'beta-3'
The species list can optionally be narrowed down with genome IDs.

WARNING: it contains hardcoded data. Barely tested.
USE AT YOUR OWN RISK!

Author: Stefano Giorgetti
"""

from dataclasses import dataclass
from string import Template
from mysql.connector.connection import MySQLConnection

# CHECK cfg below with Automation!!!
META_HOST = "mysql-ens-production-1"
META_PORT = 4721
META_DB = "ensembl_genome_metadata"

HOST = "mysql-ens-sta-6.ebi.ac.uk"
PORT = 4695

@dataclass
class SrcInfo:
    """Class for keeping track of geneset source info"""

    source_name: str
    source_url: str
    is_ensembl_anno: bool


def get_metadb_connection(username="ensro", password="") -> MySQLConnection:
    return MySQLConnection(
        user=username,
        password=password,
        host=META_HOST,
        port=META_PORT,
        database=META_DB,
    )


def get_connection(username:str, password:str, dbname:str|None=None) -> MySQLConnection:
    if dbname is None:
        return MySQLConnection(
            user=username, password=password, host=HOST, port=PORT
        )
    return MySQLConnection(
        user=username, password=password, host=HOST, port=PORT, database=dbname
    )


def get_ensro_connection(dbname:str|None=None):
    return get_connection(username="ensro", password="", dbname=dbname)


def get_dbs(conx, release=int, genomes: list[str]|None=None) -> list:
    cursor = conx.cursor()
    if genomes is None:
        genomes_str = ""
    else:
        genomes_str = ",".join([f"'{uuid}'" for uuid in genomes])
        genomes_str = f"and g.genome_uuid in ({genomes_str})"
    t = Template(
        """select g.production_name,g.genome_uuid,dss.name from genome g
        join genome_release gr using(genome_id)
        join genome_dataset gd using(genome_id)
        join dataset ds using(dataset_id)
        join dataset_source dss using(dataset_source_id)
        where gr.release_id = $release_id
        and gd.release_id = $release_id
        and ds.dataset_type_id = 2
        $genomes_str
        """
    )
    cursor.execute(t.substitute(release_id=release, genomes_str=genomes_str))
    dbs = cursor.fetchall()
    return dbs


def get_analysis_src_info(conx:MySQLConnection, dbname:str) -> SrcInfo:
    cursor = conx.cursor()

    t = Template(
        """select species_id,
           max(case when meta_key = 'genebuild.annotation_source' then meta_value else null end),
           max(case when meta_key = 'genebuild.provider_name' then meta_value else null end),
           max(case when meta_key = 'genebuild.provider_url' then meta_value else null end)
           from $dbname.meta m
           where m.meta_key in ('genebuild.annotation_source','genebuild.provider_name','genebuild.provider_url')
           group by species_id;
        """
    )

    cursor.execute(t.substitute(dbname=dbname))
    r = cursor.fetchone()
    is_ensembl_anno = str(r[1]).lower() == "ensembl"
    return SrcInfo(source_name=r[2], source_url=r[3], is_ensembl_anno=is_ensembl_anno)


def main(release:int, genomes:list[str]|None=None) -> dict[str, dict]:
    conx = get_metadb_connection()
    dbs = get_dbs(conx, release=release, genomes=genomes)
    conx.close()
    conx = get_ensro_connection()
    descriptions = {}

    print(f"Found {len(dbs)} genomes{f' (out of {len(genomes)} requested)' if genomes else ''} for release {release}.")
    for db in dbs:
        dbname = db[2]
        #print(f"Working on: {dbname}")
        src_info = get_analysis_src_info(conx, dbname)
        ensembl_imported = "Annotated" if src_info.is_ensembl_anno else "Imported"
        descriptions[db[1]] = {
            "source_names": [src_info.source_name],
            "source_urls": [src_info.source_url],
            "description": ensembl_imported,
        }

    conx.close()

    return descriptions
