#!/usr/bin/env python
#
#  See the NOTICE file distributed with this work for additional information
#  regarding copyright ownership.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
Populate Source table and link to Specifications.
Run from project root: python src/ensembl/production/tracks/populate_sources.py
"""

import os
import sys
import django
from pathlib import Path

# Setup Django
project_root = os.getenv('DJANGO_PROJECT_ROOT', os.getcwd())
sys.path.insert(0, project_root)

env_file = Path(project_root) / '.env'
if env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(env_file)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ensembl_track_api.settings')
django.setup()

from tracks.models import Source, Specifications

# Source data: (name, url, [specification_names])
SOURCES_DATA = [
    ("GERP", "http://mendel.stanford.edu/SidowLab/downloads/gerp/",
     ["gerp-elements", "gerp-scores"]),

    ("Ensembl Regulation", "https://regulation.ensembl.org",
     ["regulatory-features"]),

    ("Genome Reference Consortium", "https://genomereference.org",
     ["repeats.centromere_repeat"]),

    ("Dust", "https://bmcbioinformatics.biomedcentral.com/articles/10.1186/s12859-015-0654-5",
     ["repeats.dust"]),

    ("ENA", "https://www.ebi.ac.uk/ena",
     ["repeats.ena_repeat"]),

    ("PomBase", "https://www.pombase.org",
     ["repeats.long_terminal_repeat", "repeats.low_complexity_region",
      "repeats.ltr_retrotransposon", "repeats.regional_centromere_inner_repeat_region"]),

    ("RED", "https://bmcbioinformatics.biomedcentral.com/articles/10.1186/s12859-015-0654-5",
     ["repeats.repeatdetector", "repeats.repeatdetector_annotated"]),

    ("RepeatMasker", "https://www.repeatmasker.org",
     ["repeats.repeatmask", "repeats.repeatmask_customlib", "repeats.repeatmask_nrplants",
      "repeats.repeatmask_redat", "repeats.repeatmask_repbase", "repeats.repeatmask_repbase_human",
      "repeats.repeatmask_repbase_human_low", "repeats.repeatmaskagi"]),

    ("REdat", "https://mips.helmholtz-muenchen.de/plant/recat",
     ["repeats.repeatmask_nrplants", "repeats.repeatmask_redat"]),

    ("TREP", "https://trep-db.uzh.ch",
     ["repeats.repeatmask_nrplants"]),

    ("RepetDB", "https://urgi.versailles.inra.fr/repetdb/begin.do",
     ["repeats.repeatmask_nrplants"]),

    ("Human Pangenome Reference Consortium", "https://humanpangenome.org/",
     ["repeats.segdups"]),

    ("Tandem Repeats Finder", "https://tandem.bu.edu/trf/trf.html",
     ["repeats.trf"]),

    ("newcpgreport", "https://emboss.sourceforge.net/apps/cvs/emboss/apps/newcpgreport.html",
     ["simple-features-cpg"]),

    ("Eponine-TSS", "https://www.sanger.ac.uk/tool/eponine",
     ["simple-features-tssp"]),

    ("dbSNP", "https://www.ncbi.nlm.nih.gov/snp",
     ["variant-dbsnp"]),

    ("Ensembl", "https://www.ensembl.org/index.html",
     ["variant-ensembl"]),

    ("EVA", "https://www.ebi.ac.uk/eva",
     ["variant-eva"]),
    ("Ensembl", "https://rapid.ensembl.org/info/genome/genebuild/full_genebuild.html",
    ["transcripts-gene-pc-fwd", "transcripts-gene-pc-rev",
    "transcripts-gene-other-fwd", "transcripts-gene-other-rev"]),
]


def populate_sources():
    """Populate Source table and link to Specifications."""

    created_count = 0
    linked_count = 0
    missing_specs = set()

    for name, url, spec_names in SOURCES_DATA:
        # Get or create Source
        source, created = Source.objects.get_or_create(
            name=name,
            url=url
        )

        if created:
            created_count += 1
            print(f"Created source: {name}")
        else:
            print(f"Source already exists: {name}")

        # Link to specifications
        for spec_name in spec_names:
            try:
                spec = Specifications.objects.get(name=spec_name)
                source.specification.add(spec)
                linked_count += 1
                print(f"  Linked to specification: {spec_name}")
            except Specifications.DoesNotExist:
                missing_specs.add(spec_name)
                print(f"  WARNING: Specification not found: {spec_name}")

    print("\n" + "=" * 60)
    print(f"Summary:")
    print(f"  Sources created: {created_count}")
    print(f"  Links created: {linked_count}")

    if missing_specs:
        print(f"\nMissing specifications ({len(missing_specs)}):")
        for spec in sorted(missing_specs):
            print(f"  - {spec}")
    else:
        print("\nAll specifications found!")

    return created_count, linked_count


if __name__ == "__main__":
    created, linked = populate_sources()
    print("\nDone!")