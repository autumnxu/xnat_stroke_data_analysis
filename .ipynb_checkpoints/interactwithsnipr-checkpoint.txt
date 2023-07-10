# #!/bin/bash

### Introduction to the SNIPR webpage:
### Required software/programming language for uploading the files:

    ###linux,bash,curl,python

    ### list projects:

    # curl  -u   $XNAT_USER:$XNAT_PASS  -X GET   $XNAT_HOST/data/projects/?format=csv  > project.csv

    # # libreoffice project.csv

    # ## list subjects :

    # curl  -u   $XNAT_USER:$XNAT_PASS  -X GET   $XNAT_HOST/data/subjects/?format=csv  > subject.csv

    # # libreoffice subject.csv

    # ## list subjects of one project:

    # projectname="BJH"

    # curl  -u   $XNAT_USER:$XNAT_PASS  -X GET   $XNAT_HOST/data/projects/${projectname}/subjects/?format=csv  > ${projectname}subject.csv

    # # libreoffice project.csv

    # ## list sessions :

    # curl  -u   $XNAT_USER:$XNAT_PASS  -X GET   $XNAT_HOST/data/experiments/?format=csv  > sessions.csv

    # # libreoffice sessions.csv

    # ## list sessions of a subject:

    # subjectname="SNIPR_S01015"

    # curl  -u   $XNAT_USER:$XNAT_PASS  -X GET   $XNAT_HOST/data/projects/${projectname}/subjects/${subjectname}/experiments/?format=csv  > ${subjectname}sessions.csv

    # # libreoffice sessions.csv

    # ## list scans :

    # sessionID="SNIPR_E03517"

    # curl  -u   $XNAT_USER:$XNAT_PASS  -X GET   $XNAT_HOST/data/experiments/$sessionID/scans/?format=csv  > "${sessionID}scans.csv"

    # # libreoffice ${sessionID}scans.csv


    # ## download files from resources:

    # scanID=2

    # rm -r ${sessionID}_${scnaID}*

    # curl  -u   $XNAT_USER:$XNAT_PASS  -X GET   $XNAT_HOST/data/experiments/${sessionID}/scans/${scanID}/resources/DICOM/files?format=zip > ${sessionID}_${scnaID}.zip

    # ## unzip 

    # rm -r unzipfolder

    # mkdir unzipfolder

    # unzip ${sessionID}_${scanID} -d unzipfolder

    # for x in unzipfolder/* ;

    # do 

    # foldername=$(basename $x)_${scanID}

    # dcm2niix -o $(realpath unzipfolder) -f $foldername -m 1 ${x} 

    # done

    ## upload files from local computer: 

    # sessionID="SNIPR_E03517"

    # scanID=2

    # curl  -L -k -u   $XNAT_USER:$XNAT_PASS  -X POST   $XNAT_HOST/data/experiments/${sessionID}/scans/${scanID}/resources/TEST/files/  -F item=@./scans.csv

    ### where to upload the xml file:

    # curl -L -k -u $XNAT_USER:$XNAT_PASS -X POST $XNAT_HOST/xapi/archive/upload/xml -F item=@./stroke_edema_template_ATUL.xml

    ### What we have not done yet?

    ## Required software/programming language:

    # java plugin with gradle

    # firefox https://wiki.xnat.org/documentation &

    # firefox https://wiki.xnat.org/display/XAPI/Data+Type+Schema+API  &

    # firefox https://wiki.xnat.org/documentation/xnat-developer-documentation/working-with-xnat-plugins/developing-xnat-plugins/xnat-data-type-development &

