# IEC CDD Candidate Source

This repository is a local seed for IEC CDD property candidates used by the
mapping pipeline.

The authoritative source is IEC CDD:

- Browser entry point: https://cdd.iec.ch
- IEC TC 3 overview: https://tc3.dvl.iec.ch/tc-activity/common-data-dictionary-cdd/
- Legacy direct browser: https://www.electropedia.org/cdd/iec61360/iec61360.nsf/Welcome?OpenPage

IEC CDD is an online database with IRDI identifiers such as
`0112/2///61987#ABA565#009`. The pipeline treats this directory as an import
cache because not every IEC CDD deployment exposes a simple anonymous bulk API.

The current seed focuses on Digital Nameplate / IEC 61987 concepts that are
already referenced by IDTA templates. Add exported IEC CDD records to
`iec_cdd_properties.json` when a target domain needs more coverage.
