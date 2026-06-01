# IEC CDD Candidate Source

This repository is a local IEC CDD cache for property candidates used by the
mapping pipeline.

The authoritative source is IEC CDD:

- Browser entry point: https://cdd.iec.ch
- IEC TC 3 overview: https://tc3.dvl.iec.ch/tc-activity/common-data-dictionary-cdd/
- Legacy direct browser: https://www.electropedia.org/cdd/iec61360/iec61360.nsf/Welcome?OpenPage

IEC CDD is an online database with IRDI identifiers such as
`0112/2///61987#ABA565#009`. The pipeline treats this directory as an import
cache because not every IEC CDD deployment exposes a simple anonymous bulk API.

`iec_cdd_properties.json` is rebuilt by:

```bash
python3 scripts/rebuild_iec_cdd_dictionary.py
```

The rebuild merges curated seed records, every IEC 61360/61987 IRDI referenced
by checked-in IDTA Submodel Templates, and optional official/exported JSON files
placed under `repositories/iec_cdd_dictionary/imports/`.
