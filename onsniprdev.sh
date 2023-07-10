#!/bin/bash
sessionID=SNIPR_E03517
XNAT_USER=autumnxu
XNAT_HOST='https://snipr-dev-test1.nrg.wustl.edu'
XNAT_PASS=abc123
sessionID=SNIPR_E03517
scanID=2
# curl  -u   $XNAT_USER:$XNAT_PASS  -X GET   $XNAT_HOST/data/experiments/$sessionID/scans/?format=csv  > "${sessionID}scans.csv"
# curl  -u   $XNAT_USER:$XNAT_PASS  -X GET   $XNAT_HOST/data/experiments/?format=csv  > "sessions.csv"
curl  -u   $XNAT_USER:$XNAT_PASS  -X GET   {$XNAT_HOST}'/data/experiments/'${sessionID}'/scans/'${scanID}'/resources/NWUCALCULATION/scans/2-Z_Axial_Brain/resouces/NWUCALCULATION/files?format=zip' > "${sessionID}_${scanID}_NWU.zip"