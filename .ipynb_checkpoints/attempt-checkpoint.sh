get_metadata_session_as_csv() {
echo "in bash script -- get_metadata_session_as_csv"
# rm -r /ZIPFILEDIR/*
sessionID=${1}

python3 -c "
import sys
sys.path.append('/software');
from download_with_session_ID import *;
call_get_metadata_session_as_csv()" ${sessionID}   


}

URI='/data/experiments/SNIPR_E03517/scans/2'
resource_dir='DICOM'
get_metadata_scanresources_as_csv ${URI} ${resource_dir}