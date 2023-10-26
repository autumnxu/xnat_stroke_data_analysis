# imports 
import pandas as pd
import json
import os
from pathlib import Path
import glob
import pydicom
import xmltodict
from datetime import datetime
#from pyxnat import Interface # not needed since uploading xml worked
from xnatSession import XnatSession
import requests
import xml.etree.ElementTree as ET # trying to not download xml but deal with the content right there
import time
from collections import defaultdict # to avoid ambiguous {} initiating python dict
import re # to extract version date and analysis date
# global variables
XNAT_HOST = 'https://snipr-dev-test1.nrg.wustl.edu' # 'https://snipr-dev-test1.nrg.wustl.edu'  'https://snipr.wustl.edu'
XNAT_USER = 'autumnxu'
XNAT_PASS = 'abc123'

subject_errors = set()

'''
functionality
    write metadata to csv in the process
inputs 
    URI: /data/experiments/SNIPR_E03517/scans/2
    resource_dir: DICOM or NIFTI or Z axial scan or whatever
return
    full uri to download dicom file or nifti file or ... file
        /data/experiments/SNIPR_E03517/scans/2/resources/69957/files/1.2.840.113654.2.45.6242.41786130236813614531978884608083678057-2-17-l7buaf.dcm
'''
def get_resourcefiles_metadata_as_csv(URI,resource_dir):
    url = (URI+'/resources/' + resource_dir +'/files?format=json')
    print('full url:', url)
    full_uri = url  # defult, this should error out
    xnatSession = XnatSession(username=XNAT_USER, password=XNAT_PASS, host=XNAT_HOST)
    xnatSession.renew_httpsession()
    response = xnatSession.httpsess.get(xnatSession.host + url)
    xnatSession.close_httpsession()
    #print('almost error')
    #print(xnatSession.host + url)
    #json_res = response.json()
    json_res = None
    try:
        json_res = response.json()
    except json.JSONDecodeError as e:
        print("following url does not have resource folder", xnatSession.host+url)
        print(f"JSONDecodeError: {e}")
        return None
    metadata_masks=json_res['ResultSet']['Result']
    jsonStr = json.dumps(metadata_masks)
    if resource_dir == "EDEMA_BIOMARKER":
        print('debugging', url)
        print(json_res['ResultSet'].keys())
    #full_uri = json.loads(jsonStr)[0]['URI']
    #here add checks for variable file type 
    #print('viewing structure')
    #print(metadata_masks)
    if resource_dir == 'NWUCALCULATION':
        uri_temp = [d['URI'] for d in metadata_masks if d['URI'].endswith('.csv')]
        if uri_temp:
            print("ever ever here???")
            full_uri = uri_temp[0]
    if resource_dir == 'EDEMA_BIOMARKER':   
        print('finally here????')     
        uri_temp = [d['URI'] for d in metadata_masks if d['URI'].endswith('columndropped.csv')]
        if uri_temp:
            full_uri = uri_temp[0]
    elif resource_dir == 'DICOM' and metadata_masks[0]:
        full_uri = metadata_masks[0]['URI']
    
    print('json string of metadata masks', url)
    df = pd.read_json(jsonStr)
    df.to_csv(os.path.basename(URI)+'_'+resource_dir+'metadata.csv',index=False)
    return full_uri

# this function would downlaod a file as dicatated by the url, saving to directory
def download_resource_file(url, file_name, directory):
    xnatSession = XnatSession(username=XNAT_USER, password=XNAT_PASS, host=XNAT_HOST)
    xnatSession.renew_httpsession()
    response = xnatSession.httpsess.get(xnatSession.host + url)
    #zipfilename= os.path.basename(url)
    #print('zipfilename of download_resource_file_curr_dir:', zipfilename)
    curr_file=os.path.join(directory, file_name)
    print("need underscore?", directory)
    # file opened for writing in binary mode
    with open(curr_file, "wb") as f:
        for chunk in response.iter_content(chunk_size=512):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
    xnatSession.close_httpsession()
    
'''
functionality: build partial XML based on custom variables
-> collect Stroke_Time, Stroke_Date, Scan_Quality, Cerebral_Edema_Grade
input: the url is specific to subject_id
'''
def view_resources(url, resource_dir):
    xnatSession = XnatSession(username=XNAT_USER, password=XNAT_PASS, host=XNAT_HOST)
    xnatSession.renew_httpsession()
    response = xnatSession.httpsess.get(xnatSession.host + url)
    xnatSession.close_httpsession()
    namespace_dict = {
        'xnat': 'http://nrg.wustl.edu/xnat',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
    }
    custom_variables_dict = {}
    potential_session_ids = []
    if response.status_code == 200:
        xml_content = response.content  # Get the raw XML content
        root = ET.fromstring(xml_content)
        fields_element = root.find('.//xnat:fields', namespaces=namespace_dict)
        if fields_element == None:
            return (None, None)
        stroke_onset_date_element = fields_element.find('.//xnat:field[@name="stroke_onset_date"]', namespaces=namespace_dict)
        stroke_onset_time_element = fields_element.find('.//xnat:field[@name="stroke_onset_time"]', namespaces=namespace_dict)
        long_cerebral_edema_grade = fields_element.find('.//xnat:field[@name="cerebral_edema_grading_for_ischemic_stroke"]', namespaces=namespace_dict)
        scan_quality = None
        # the above three fields need .text to extract value
        for scan_element in root.findall('.//xnat:scan', namespaces=namespace_dict):
            image_session_id = scan_element.findtext('xnat:image_session_ID', namespaces=namespace_dict)
            scan_type = scan_element.get('type')
            if scan_type == 'Z Axial Brain':
                scan_quality = scan_element.findtext('xnat:quality', namespaces=namespace_dict)
                # this is direct string
                potential_session_ids.append(image_session_id)
                break
        if stroke_onset_date_element is not None and stroke_onset_time_element is not None and long_cerebral_edema_grade is not None and scan_quality:
            custom_variables_dict['Stroke_Time'] = stroke_onset_time_element.text
            custom_variables_dict['Stroke_Date'] = stroke_onset_date_element.text
            custom_variables_dict['Cerebral_Edema_Grade'] = long_cerebral_edema_grade.text
            custom_variables_dict['Scan_Quality'] = scan_quality
            
    return (custom_variables_dict, potential_session_ids)
        


# bug, what if time points cross day(s)
def time_diff(stroke_time, scan_time, stroke_date, scan_date):
    # Convert string to datetime object
    stroke_datetime = datetime.strptime(stroke_date + ' ' + stroke_time, '%Y-%m-%d %H:%M:%S')
    scan_datetime = datetime.strptime(scan_date + ' ' + scan_time, '%Y-%m-%d %H:%M:%S')
    time_difference = stroke_datetime - scan_datetime
    
    # Calculate the time difference in hours
    hours = time_difference.total_seconds() / 3600
    print('elapsed from stroke in hours:', hours)
    return round(hours, 2)

'''
thoughts
functionality: fill xml according to .dcm, .csv and custom variables
if any of the fields can not be read, return None,
since the uploading of xml won't work
'''
def fill_info(sessionId, subject_id):
    dicom_dict = None
    
    dicom_dict = grab_dicom_info(sessionId)
    nwu_dict = grab_nwu_info(sessionId)
    if not nwu_dict:
        return (None, None)
    
    
    (cutom_variables_dict, label_name) = grab_custom_variables(subject_id, sessionId)
    
    if dicom_dict is None or nwu_dict is None or cutom_variables_dict is None:
        print('information incomplete for', sessionId, subject_id)
        return (None, None)
    full_dict = {**dicom_dict, **nwu_dict, **cutom_variables_dict}
    
    if "Scan_Time" in full_dict and "Stroke_Time" in full_dict and "Scan_Date" in full_dict and "Stroke_Date" in full_dict:
        full_dict["Elapsed_From_Stroke"] = time_diff(full_dict["Scan_Time"], full_dict["Stroke_Time"], full_dict["Scan_Date"], full_dict["Stroke_Date"])
    full_dict["Session_Name"] = sessionId
    file_name = write_to_blank_xml(full_dict, sessionId, subject_id, label_name)
    print("end of fill_info() -- is it none?", file_name)
    return (full_dict, file_name)


def write_to_blank_xml(full_dict, sessionId, subject_id, label_name):
    print('entering write_to_blank_xml')
    with open('blank_template.xml', 'r', encoding='utf-8') as file:
        xml_read = file.read()
    # Use xmltodict to parse and convert the XML document
    dict_of_xml = xmltodict.parse(xml_read)
    datatype_name = list(dict_of_xml.keys())[0]
    # subject id: assession number of subject 
    # fill out xnat subject id
    dict_of_xml[datatype_name]['xnat:subject_ID'] = subject_id # this should be subject id, not sessionid
    dict_of_xml[datatype_name]['xnat:date'] = datetime.now().strftime('%Y-%m-%d')
    for key in full_dict:
        xml_workshop_filed = 'workshop:'+key
        dict_of_xml[datatype_name][xml_workshop_filed] = full_dict[key]
    # delete fields that's not there
    dict_of_xml[datatype_name] = {k: v for k, v in dict_of_xml[datatype_name].items() if v}

    # give unique label and make pyxnat happy
    dict_of_xml[datatype_name]['@ID'] = ''
    dict_of_xml[datatype_name]['@label'] = 'stroke_edema_'+label_name+'_'+sessionId+'_'+subject_id # later in this format: CT Session: BJH_001_11112019
    modified_xml = xmltodict.unparse(dict_of_xml, pretty=True)
    # SAVE xml into a file
    print('view filled xml')
    print(modified_xml)
    # this name may mimics format for uploading xml downstream
    now = datetime.now()
    formatted_date = now.strftime("%m_%d_%y_%H_%M_%S")
    file1 = open(formatted_date+'.xml',"w")
    file1.write(modified_xml)
    file1.close()
    print('is this Nonetype????', formatted_date)
    return formatted_date+'.xml'


'''
functionality
    given the sessoin id, 
    look into the corresponding csv file for NWU calculations
    find values of interest
    return a dictionary 
input
    session id, ie. 'SNIPR_E03517'
return
    a dictionary with fetched field in key, fetched info in value
'''
def grab_nwu_info(sessionId):
    # grab file 
    to_match = './{0}*/*.csv'.format(sessionId)
   # print("session id not matched", sessionId)
    filepaths = glob.glob(to_match, recursive=True)
    #print('net water uptake calculations -- file to fetch info', filepaths[0])    
    if not filepaths:
        print("none from nwu csv files")
        return None
    dataframe = pd.read_csv(filepaths[0])
    print('possible values to fetch:', dataframe.columns)
    # fill in values 
    net_water_uptake_dict = {}
    decimal_place = 2
    net_water_uptake_dict['Net_Water_Uptake'] = round(dataframe.loc[0, "NWU"], decimal_place)
    net_water_uptake_dict['Infarct_Side'] = dataframe.loc[0, "INFARCT SIDE"]
    net_water_uptake_dict['Infarct_Volume'] = round(dataframe.loc[0, "INFARCT VOLUME"], decimal_place)
    net_water_uptake_dict['Total_Cerebrospinal_Fluid_Volume'] = round(dataframe.loc[0, "TOTAL CSF VOLUME"], decimal_place)
    net_water_uptake_dict['Cerebrospinal_Fluid_Ratio'] = round(dataframe.loc[0, "CSF RATIO"], decimal_place)
    file_name = os.path.basename(filepaths[0])

    # Extract analysis date
    analysis_date_match = re.search(r"VersionDate.*?(\d{2})_(\d{2})_(\d{4})columndropped.csv", file_name)
    if analysis_date_match:
        analysis_month = analysis_date_match.group(1)
        analysis_day = analysis_date_match.group(2)
        analysis_year = analysis_date_match.group(3)
        net_water_uptake_dict['Analysis_Date'] = f"{analysis_year}-{analysis_month}-{analysis_day}"
    

    # Extract version date
    version_date_match = re.search(r"VersionDate-(\d{2})(\d{2})(\d{4})", file_name)
    if version_date_match:
        version_month = version_date_match.group(1)
        version_day = version_date_match.group(2)
        version_year = version_date_match.group(3)
        net_water_uptake_dict['Version_Date'] = f"{version_year}-{version_month}-{version_day}"
    else:
        print("Version date not found for session", sessionId)
    print(net_water_uptake_dict)
    return net_water_uptake_dict

'''
functionality
    given the subject_id id, 
    look into the corresponding XML file for custom variables
    find values of interest
    return a dictionary 
input
    session id, ie. 'SNIPR_S01016' 
return
    a dictionary with fetched field in key, fetched info in value
'''
def grab_custom_variables(subject_id, session_id):
    # use the input id to access the proper xml file
    to_match = './{0}*/*xml'.format(subject_id)
    filepaths = glob.glob(to_match, recursive=True)
    with open(filepaths[0], 'r', encoding='utf-8') as file:
        xml_read = file.read()

    custom_variables_dict = {}
    label_name = None
    dict_of_xml = xmltodict.parse(xml_read)
    list_of_dict = None
    try:
        list_of_dict = dict_of_xml['xnat:Subject']['xnat:fields']['xnat:field'] 
        '''
        usability = [
            child['xnat:quality']
            for item in dict_of_xml['xnat:Subject']['xnat:experiments']['xnat:experiment']
            if item['@ID'] == session_id
            for child in item['xnat:scans']['xnat:scan']
            if child['@type'] == "Z-Axial-Brain"
        ]
        '''
        usability = []
        label_name = None
        found = False  # Flag variable to track whether we found the desired item

        for item in dict_of_xml['xnat:Subject']['xnat:experiments']['xnat:experiment']:
            if 'xnat:prearchivePath' in item:
                label_name = os.path.basename(item['xnat:prearchivePath'])
            if item['@ID'] == session_id:
                for child in item['xnat:scans']['xnat:scan']:
                    if child['@type'] == "Z-Axial-Brain" or child['xnat:series_description'] == "Axial Head":
                        custom_variables_dict['Scan_Selected'] = child['@ID']
                        usability.append(child['xnat:quality'])
                        found = True  # Set the flag to True to indicate we found the item
                        break  # Break out of the inner loop
                if found:
                    break  # If we found the item, break out of the outer loop as well
            if found:
                break
        print(found)
        custom_variables_dict['Scan_Quality'] = usability[0]
        # 'cerebral_edema_grading_for_ischemic_stroke' or 'global_cerebral_edema_for_sah' 'cerebral_edema_grade' '
        cerebral_stroke = [dict['#text'] for dict in list_of_dict if dict['@name'] == 'cerebral_edema_grading_for_ischemic_stroke'] # Cerebral_Edema_Grading_for_Ischemic_Stroke -- name in dev
        cerebral_stroke = cerebral_stroke[0]
        custom_variables_dict['Cerebral_Edema_Grade'] = cerebral_stroke[0]
        #value_of_interest = [dict['#text'] for dict in list_of_dict if dict['@name'] == 'stroke_onset_time']
        #padded = value_of_interest[0]+':00'
        
        
        stroke_date = [dict['#text'] for dict in list_of_dict if dict['@name'] == 'stroke_onset_datetime']  # in prod: stroke_onset_datetime; in dev: stroke_onset_date
        stroke_date = stroke_date[0]
        # mm/dd/yyyy -> yyyy-mm-dd
        padded_date = stroke_date[6:]+'-'+stroke_date[:2]+'-'+stroke_date[3:5]
        custom_variables_dict['Stroke_Time'] = '00:00:00'  #padded
        custom_variables_dict['Stroke_Date'] = padded_date
        #return session_id
        print(custom_variables_dict)
    except (KeyError, IndexError):
        print("custom variables incomplete")
        print(custom_variables_dict)
        return (custom_variables_dict, label_name)
    
    match = re.match(r'^([^_]+_[^_]+)_', label_name)
    if match:
        label_name = match.group(1)

    return (custom_variables_dict, label_name)

'''
functionality
    given the sessoin id, 
    look into the corresponding DICOM file 
    find values of interest
    return a dictionary 
input
    session id, ie. 'SNIPR_E03517'
return
    a dictionary with fetched field in key, fetched info in value
'''
def grab_dicom_info(sessionId):
    # find directory with sessionId in its name 
    to_match = './{0}*/*.dcm'.format(sessionId)
    filepaths = glob.glob(to_match, recursive=True)
    if filepaths is None or len(filepaths) == 0:
        return None
    print('dicom file to fetch info', filepaths[0])    
    ds = pydicom.dcmread(filepaths[0])
    # to return 
    dicom_dict = {}
    acquisition_date = ds[0x0008, 0x0020].value # 0x0008, 0x0022 Acquisition Date in dev,prod: (0008, 0020) Study Date 
    acquisition_date= acquisition_date[:4]+'-'+acquisition_date[4:6]+'-'+acquisition_date[6:]
    print(acquisition_date)
    # MINIMUM required data 
    dicom_dict['Scan_Date'] = acquisition_date
    acquisition_time = ds[0x0008, 0x0030].value # 0x0008, 0x0032 Acquisition Time in dev, prod: (0008, 0030) Study Time   
    acquisition_time = acquisition_time.split('.')[0]
    # MINIMUM required data 
    dicom_dict['Scan_Time']  = acquisition_time[:2] + ':' + acquisition_time[2:4] + ':' + acquisition_time[4:] 

    pixel_spacing = ds[0x0028, 0x0030]
    # MINIMUM required data
    dicom_dict['Scan_Selected'] = ds[0x0020, 0x0012].value
    # for complete image size
    decimal_place = 2
    dicom_dict['DICOM_Pixel_Size_X'] = round(pixel_spacing[0], decimal_place)
    dicom_dict['DICOM_Pixel_Size_Y'] = round(pixel_spacing[1], decimal_place)
    dicom_dict['Z_Dimension'] = ds[0x0018, 0x0050].value # argue with Atul for whether this is needed
    # for resolution  -- MINIMUM required data 
    dicom_dict['X_Dimension'] = ds[0x0028, 0x0010].value # row
    dicom_dict['Y_Dimension'] = ds[0x0028, 0x0011].value # column
    #dicom_dict['scan_id'] = ds[0x0020, 0x0011].value # series/aquisition number
    dicom_dict['CT_Scanner'] = ds[0x0008, 0x1090].value
    dicom_dict['Scan_Description'] = ds[0x0008, 0x103e].value
    '''
    number of slices: count the number of files in DICOM folder
        now not needed, since only downloade done dicom file from the subject
    slice_num = len(glob.glob(os.path.dirname(filepath)+'/*.dcm'))
    slice_num=len(filepaths)
    '''
    print(dicom_dict)
    #print(ds[0x0008, 0x0022].value)
    #print(ds[0x0008, 0x0022].keyword)
    print('exiting grab_dicom_info')
    return dicom_dict

# from session.csv grabbed by the curl command
'''
functionality: 
    from the session.csv grabbed by the followng curl command
    curl  -u   $XNAT_USER:$XNAT_PASS  -X GET   $XNAT_HOST/data/experiments/?format=csv  > sessions.csv
return
    a list of session id to populate 
'''
def fetch_sessionid(session_id_url):
    url = (session_id_url+'/?format=json')
    print('fetch_sessionid -- full url:', url)
    xnatSession = XnatSession(username=XNAT_USER, password=XNAT_PASS, host=XNAT_HOST)
    xnatSession.renew_httpsession()
    response = xnatSession.httpsess.get(xnatSession.host + url)
    xnatSession.close_httpsession()
    json_res = response.json()['ResultSet']['Result']
    print('how to link subject id to session id?')
    print(response.json()['ResultSet'])
    accessible_projects = ['BJH', 'COLI', 'WashU']
    session_id = [os.path.basename(entry['URI']) for entry in json_res if entry['project'] in accessible_projects] 
    # here we need BJH_xxx 
    return session_id

def fetch_proper_pair():
    url = '/data/subjects/?format=json'
    xnatSession = XnatSession(username=XNAT_USER, password=XNAT_PASS, host=XNAT_HOST)
    xnatSession.renew_httpsession()
    response = xnatSession.httpsess.get(xnatSession.host + url)
    json_res = response.json()['ResultSet']['Result']
    accessible_projects = ['BJH', 'COLI', 'WashU']
    subject_paths = [entry['URI'] for entry in json_res if entry['project'] in accessible_projects] 
    subject_to_sessions = {}
    accepted_types = ['Z Axial Brain', 'Z-Axial-Brain']
    for subject_id in subject_paths:
        if (subject_id == '/data/subjects/SNIPR02_S00103'):
            print('hopeful subject id')
        url_to_session = '{0}/scans/?format=json'.format(subject_id)
        xnatSession.renew_httpsession()
        scans_response =  xnatSession.httpsess.get(xnatSession.host + url_to_session)
        scans = None
        try:
            #this is a list of sessions
            if not scans_response.json()['items'][0] or not scans_response.json()['items'][0]['children']:
                # 	SNIPR02_S00828 for example
                continue
            scans = scans_response.json()['items'][0]['children']
        except json.JSONDecodeError as e:
            subject_errors.add(os.path.basename(subject_id))
            print(f"JSONDecodeError: {e} for subject {subject_id}")
            continue
        '''
        
        session_ids = []
        for children in scans:
                for child in children['items']:
                    for grandchildren in child['children']:
                        for grandchild in grandchildren['items']:
                            if ('data_fields' in grandchild and 'type' in grandchild['data_fields'] and grandchild['data_fields']['type'] in accepted_types):
                                session_ids.append(grandchild['data_fields']['image_session_ID'])
        list comprehension below
        '''
        session_ids = [
            grandchild['data_fields']['image_session_ID']
            for children in scans
            for child in children['items']
            for grandchildren in child['children']
            for grandchild in grandchildren['items']
            if 'data_fields' in grandchild
            and 'type' in grandchild['data_fields']
            and grandchild['data_fields']['type'] in accepted_types
        ]
        if not session_ids:
            continue
        for session_id in session_ids:
            url_to_label = '/data/experiments/{0}/scans/?format=json'.format(session_id)
            xnatSession.renew_httpsession()
            label_response =  xnatSession.httpsess.get(xnatSession.host + url_to_label)
            label_json_response = label_response.json()['ResultSet']['Result']
            scan_ids = [entry['ID'] for entry in label_json_response if entry.get('type')in accepted_types]            
            if not scan_ids:
                continue
            for scan_id in scan_ids:
                url_to_label = '/data/experiments/{0}/scans/{1}/resources/?format=json'.format(session_id, scan_id)
                xnatSession.renew_httpsession()
                resource_format =  xnatSession.httpsess.get(xnatSession.host + url_to_label)
                
                
                tmp_json =  resource_format.json()['ResultSet']['Result']
                edema_biomarker_present = any(d.get('label') == 'EDEMA_BIOMARKER' for d in tmp_json)
                labels = [d['label'] for d in tmp_json if 'label' in d]
                '''
                with open('error_subjects.txt', 'a') as f:
                    if (labels[0] != 'DICOM'):
                        to_write = [subject_id, session_id, scan_ids, labels]
                        f.write(str(to_write)+'\n')
                '''
                if not edema_biomarker_present:
                    continue

                url_to_edema = '/data/experiments/{0}/scans/{1}/resources/EDEMA_BIOMARKER/?format=json'.format(session_id, scan_id)
                xnatSession.renew_httpsession()
                column_dropped = xnatSession.httpsess.get(xnatSession.host + url_to_edema)
                namespace_dict = {
                    'xnat': 'http://nrg.wustl.edu/xnat',
                    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
                    'cat': 'http://nrg.wustl.edu/catalog'
                }
                if column_dropped.status_code == 200:
                    xml_content = column_dropped.content  # Get the raw XML content
                    root = ET.fromstring(xml_content)
                    fields_element = root.find('.//cat:entries', namespaces=namespace_dict)
                    if fields_element == None:
                        continue
                    for entry in root.findall('.//cat:entry', namespaces=namespace_dict):
                        entry_id = entry.get('ID')
                        if "columndropped.csv" in entry_id:
                            #print("Session checked")
                            base_subject_id = os.path.basename(subject_id)
                            if base_subject_id in subject_to_sessions:
                                subject_to_sessions[base_subject_id].append([session_id, scan_id])
                            else:
                                subject_to_sessions[base_subject_id] = [[session_id, scan_id]]
       
    xnatSession.close_httpsession()
    with open('error_subjects.txt', 'a') as f:
        #f.write(subject_id + '\n')
        f.write(str(subject_errors))
    print('about to return subject_to_sessions')
    print(subject_to_sessions)
    return subject_to_sessions


def fetch_subject_paths(xnat_session, accessible_projects):
    url = '/data/subjects/?format=json'
    response = xnat_session.httpsess.get(xnat_session.host + url)
    json_res = response.json()['ResultSet']['Result']
    return [[entry['URI'], entry['project']] for entry in json_res if entry['project'] in accessible_projects]

def get_scans(xnat_session, subject_id):
    url_to_session = '{0}/scans/?format=json'.format(subject_id)
    scans_response = xnat_session.httpsess.get(xnat_session.host + url_to_session)
    try:
        if not scans_response.json()['items'][0] or not scans_response.json()['items'][0]['children']:
            return None
        return scans_response.json()['items'][0]['children']
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError: {e} for subject {subject_id}")
        return None

def get_session_ids(scans, accepted_types):
    session_ids = [
        grandchild['data_fields']['image_session_ID']
        for children in scans
        for child in children['items']
        for grandchildren in child['children']
        for grandchild in grandchildren['items']
        if 'data_fields' in grandchild
        and 'type' in grandchild['data_fields']
        and grandchild['data_fields']['type'] in accepted_types
    ]
    return session_ids

def get_scan_ids(xnat_session, session_id, accepted_types):
    url_to_label = '/data/experiments/{0}/scans/?format=json'.format(session_id)
    label_response = xnat_session.httpsess.get(xnat_session.host + url_to_label)
    label_json_response = label_response.json()['ResultSet']['Result']
    return [entry['ID'] for entry in label_json_response if entry.get('type') in accepted_types]

def is_edema_biomarker_present(xnat_session, session_id, scan_id):
    url_to_edema = '/data/experiments/{0}/scans/{1}/resources/EDEMA_BIOMARKER/?format=json'.format(session_id, scan_id)
    column_dropped = xnat_session.httpsess.get(xnat_session.host + url_to_edema)
    namespace_dict = {
        'xnat': 'http://nrg.wustl.edu/xnat',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        'cat': 'http://nrg.wustl.edu/catalog'
    }
    if column_dropped.status_code == 200:
        xml_content = column_dropped.content
        root = ET.fromstring(xml_content)
        fields_element = root.find('.//cat:entries', namespaces=namespace_dict)
        return fields_element is not None
    return False

def fetch_proper_pair_modularized():
    xnatSession = XnatSession(username=XNAT_USER, password=XNAT_PASS, host=XNAT_HOST)
    xnatSession.renew_httpsession()

    accessible_projects = ['BJH', 'COLI', 'WashU']
    subject_paths_projects = fetch_subject_paths(xnatSession, accessible_projects)

    subject_to_sessions = defaultdict(list)
    accepted_types = ['Z Axial Brain', 'Z-Axial-Brain']
    
    for pair in subject_paths_projects:
        subject_path = pair[0]
        project = pair[1]
        scans = get_scans(xnatSession, subject_path)
        if scans is None:
            continue
        
        session_ids = get_session_ids(scans, accepted_types)
        if not session_ids:
            continue
        
        for session_id in session_ids:
            scan_ids = get_scan_ids(xnatSession, session_id, accepted_types)
            
            if not scan_ids:
                continue
            
            for scan_id in scan_ids:
                if is_edema_biomarker_present(xnatSession, session_id, scan_id):
                    subject_to_sessions[(os.path.basename(subject_path), project)].append([session_id, scan_id])
                    
    xnatSession.close_httpsession()
    return subject_to_sessions


# either this is buggy or the above function is buggy
def fetch_subjectid(subject_id_url, just_ids):
    url = (subject_id_url+'/?format=json')
    print('fetch_sessionid -- full url:', url)
    xnatSession = XnatSession(username=XNAT_USER, password=XNAT_PASS, host=XNAT_HOST)
    xnatSession.renew_httpsession()
    response = xnatSession.httpsess.get(xnatSession.host + url)
    xnatSession.close_httpsession()
    json_res = response.json()['ResultSet']['Result']
    #print('how to link subject id to subject id?')
    #print(json_res)
    subject_ids = [os.path.basename(entry['ID']) for entry in json_res if entry['project'] == 'WashU'] # BJH this may be for dev
    if just_ids:
        return subject_ids
    subject_id_to_subject_sessions = {}
    for subject_id in subject_ids:
        session_ids = fetch_sessions_for_subject_id(subject_id)
        subject_id_to_subject_sessions[subject_id] = session_ids
    filtered_data = {k: v for k, v in subject_id_to_subject_sessions.items() if v}

    return filtered_data

def fetch_sessions_for_subject_id(subject_id):
    # "https://snipr-dev-test1.nrg.wustl.edu/data/projects/BJH/subjects/SNIPR_S01015/experiments"
    url = "/data/projects/BJH/subjects/"+subject_id+"/experiments/?format=json"
    xnatSession = XnatSession(username=XNAT_USER, password=XNAT_PASS, host=XNAT_HOST)
    xnatSession.renew_httpsession()
    response = xnatSession.httpsess.get(xnatSession.host + url)
    xnatSession.close_httpsession()
    json_res = response.json()['ResultSet']['Result']
    #print("is it empty for", subject_id)
    session_ids = [d['xnat:subjectassessordata/id'] for d in json_res]
    #print(session_ids)
    return session_ids


def upload_xml(xml):
    url = "/xapi/archive/upload/xml"
    xnatSession = XnatSession(username=XNAT_USER, password=XNAT_PASS, host=XNAT_HOST)
    xnatSession.renew_httpsession()
    #response = xnatSession.httpsess.

    url = "{}/xapi/archive/upload/xml".format(XNAT_HOST)
    print('unpload_xml() -- is it None?', xml)
    xml_file_path = './'+ '10_26_23_13_47_28.xml' # xml   
    with open(xml_file_path, 'rb') as xml_file:
        response = requests.post(url, auth=(XNAT_USER, XNAT_PASS), files={'item': xml_file})
        try:
            response.raise_for_status()
            print("here?")
        except requests.exceptions.HTTPError as err:
            print(f"Probably due to duplicate label, HTTP error occurred: {err}")


'''
functionality: 
    alternative to upload xml
    create experiment and then upload data
inputs:
    central: the central interface
    subject_ids: a list of subject ids
    project: "TEST_ATUL" or "BJH"
'''
def create_experiment(central ,subject_ids, project):
    curr_project = central.select.project('TEST_ATUL')
    if not curr_project.exists():
        print('requested project does not exist')
        return False
    
    #try to wrestle with this
    CTSCAN='BIOSAMPLE2' #os.path.basename(x).split('.nii')[0]
    subject = curr_project.subject(CTSCAN.split('_CT_')[0])
    # print(subject.exists())
    x = 0
''' failed code below, logic to build upon
thisexperiment = subject.experiment('biosampleCollection_' + "{:03d}".format(x)).create(
    **{
        'experiments': 'workshop:biosampleCollection',
        'ID': "{:03d}".format(x),
        'workshop:biosampleCollection/Scan_Date': '2023-01-01',
        'workshop:biosampleCollection/Scan_Time': '21:21:21',
        'workshop:biosampleCollection/CT_Scanner': 'eemem',
        'workshop:biosampleCollection/Stroke_Time': '21:21:21',
        'workshop:biosampleCollection/Elapsed_From_Stroke': '21.21',
        'workshop:biosampleCollection/DICOM_pixel_size_x': '212.0',
        'workshop:biosampleCollection/DICOM_pixel_size_y': '212.0',
        'workshop:biosampleCollection/X_Dimension': '212',
        'workshop:biosampleCollection/Y_Dimension': '212',
        'workshop:biosampleCollection/Z_Dimension': '212.0',
        'workshop:biosampleCollection/Scan_Quality': 'ememe',
        'workshop:biosampleCollection/Total_Cerebrospinal_Fluid_Volume': '21.21',
        'workshop:biosampleCollection/Cerebrospinal_Fluid_Ratio': '212.12',
        'workshop:biosampleCollection/Net_Water_Uptake': '21.21',
        'workshop:biosampleCollection/Infarct_Volume': '212.212',
        'workshop:biosampleCollection/Infarct_Side': 'ememeee',
        'workshop:biosampleCollection/Analysis_Date': '2022-03-02',
        'workshop:biosampleCollection/Version_Date': '2021-04-03',
        'workshop:biosampleCollection/Cerebral_Edema_Grade': 'ememe'
    }
)
'''
# this needs to be modifed after seeing exactly how the txt file is formatted
def read_dict():
    file_path = 'error_subjects.txt'
    # Read the content from the text file
    with open(file_path, 'r') as file:
        lines = file.readlines()

    # Initialize an empty dictionary
    result_dict = {}

    # Process each line and create the dictionary
    for line in lines:
        line = line.strip()  # Remove leading/trailing whitespace and newline characters
        key_info, value_info = line.split(':')  # Split the line into key and value parts

        # Extract key information
        key_info = key_info.strip('()')  # Remove parentheses
        key_parts = key_info.split(', ')   # Split key parts
        key = key_parts[0], key_parts[1]   # Tuple containing the first two parts as key

        # Extract and process value information
        value_str = value_info.strip()  # Remove leading/trailing whitespace
        value_list = eval(value_str)    # Evaluate the string as a Python expression to get the list

        result_dict[key] = value_list

    # Print the resulting dictionary
    print(result_dict)
    return result_dict
        
    
def find_proper_subject_sessions(full_session_ids, full_dict):
    
    print("executing tasks in find_proper_subject_sessions")
    data = pd.read_csv('sessions_ANALYTICS_20230705132606.csv', usecols=['ID', 'CSV_FILE_NUM'])
    filtered_data = data[data['CSV_FILE_NUM'] > 0]
    # Extract the values from the 'ID' column
    session_ids = filtered_data['ID'].values
    if not full_session_ids:
        full_session_ids = session_ids
    useful_subject_to_session = {}
    if (full_dict is None):
        subject_id_url = '/data/subjects'
        subject_ids = fetch_subjectid(subject_id_url, True)
        
        for subject_id in subject_ids:
            custom_variables_url = '/app/action/XDATActionRouter/xdataction/xml_file/search_element/xnat%3AsubjectData/search_field/xnat%3AsubjectData.ID/search_value/{0}/popup/false/project/WashU'.format(subject_id)
            (partial_xml, potential_session_ids) = view_resources(custom_variables_url, 'BIOMARAKER_EDEMA')
            if potential_session_ids == None:
                continue
            matching_values = list(set(potential_session_ids) & set(full_session_ids[subject_id]))
            if matching_values:
                useful_subject_to_session[subject_id] = matching_values
    else:
        for subject_id_project, session_scan in full_dict.items():
            subject_id = subject_id_project[0].strip("'")
            project = subject_id_project[1].strip("'")
            custom_variables_url = '/app/action/XDATActionRouter/xdataction/xml_file/search_element/xnat%3AsubjectData/search_field/xnat%3AsubjectData.ID/search_value/{0}/popup/false/project/{1}'.format(subject_id, project)
            (partial_xml, potential_session_ids) = view_resources(custom_variables_url, 'BIOMARAKER_EDEMA')
            if potential_session_ids == None:
                continue
            session_ids_from_csv = [item[0] for item in session_scan]
            matching_values = list(set(potential_session_ids) & set(session_ids_from_csv))
            if matching_values:
                useful_subject_to_session[subject_id] = matching_values


    print("useful_subject_to_session")
    print(useful_subject_to_session)
    with open('./useful_subject_to_session.json', "w") as json_file:
        json.dump(useful_subject_to_session, json_file)

    return useful_subject_to_session
    

def test_main(subject_project_to_sesions_scans):
    '''the following code works
    xml = '03_31_23_20_11_46.xml'
    upload_xml(xml)
    '''

    print("executing tasks in main")
    '''
    
    #session_id_url = '/data/experiments'
    #session_ids = fetch_sessionid(session_id_url)
    subject_id_url = '/data/subjects'
    subject_to_sesions = fetch_subjectid(subject_id_url)
    #print("how many subjects?", len(subject_ids))
    print('final dict?')
    print(subject_to_sesions)
    '''
    # before automating the session id and subject with the code above, figure out more details below
    partial_execution = 5
    count = 0
    for subject_project, sessions_scans in subject_project_to_sesions_scans.items():
        subject = subject_project[0]
        project = subject_project[1]
        for session_scan in sessions_scans:
            session_id = session_scan[0]
            scan_id = session_scan[1]
            URI = '/data/experiments/'+session_id+'/scans/'+scan_id
            resource_dir = 'NWUCALCULATION' # 'DICOM' or 'NWUCALCULATION'
            resource_dirs = ['EDEMA_BIOMARKER', 'DICOM'] # EDEMA_BIOMARKER for main
            for resource_dir in resource_dirs:
                directory =subject+'_'+session_id+'_'+resource_dir
                full_uri = get_resourcefiles_metadata_as_csv(URI, resource_dir)
                if full_uri is None or full_uri == URI:
                    break
                #filename = os.path.basename(full_uri)
                #dir_path = './'+directory
                print('full uri:', full_uri)
                Path('./'+directory).mkdir(parents=True, exist_ok=True)
                download_resource_file(full_uri, os.path.basename(full_uri), directory)
    
            # not every subject id has custom variables
            custom_variables_url = '/app/action/XDATActionRouter/xdataction/xml_file/search_element/xnat%3AsubjectData/search_field/xnat%3AsubjectData.ID/search_value/{0}/popup/false/project/{1}'.format(subject, project)
            file_name = subject+'custom_variable_xml'
            directory = subject+'_xmls'
            Path('./'+directory).mkdir(parents=True, exist_ok=True)
            download_resource_file(custom_variables_url, file_name, directory)
    
            (xml, file_name, label_name) = fill_info(session_id, subject)
            
            if file_name:
                upload_xml(file_name)
            if xml:
                count = count+1
                if count >= partial_execution:
                    break
            
            
        if count >= partial_execution:
                break
    
# parse info here....
def one_sample_test():
    sessionId = 'SNIPR_E03244' # final value used for dev: SNIPR_E03665; SNIPR_E03517 CT session associated with subject 001
    subject_id = 'SNIPR_S00917' # final value used for dev: SNIPR_S01154; SNIPR_S01016 this is subject 001, no relevant custom variable uploaded
    URI = '/data/experiments/'+sessionId+'/scans/1-CT1'
    #resource_dir = 'EDEMA_BIOMARKER' # 'DICOM' or 'NWUCALCULATION'
    resource_dirs = ['EDEMA_BIOMARKER', 'DICOM'] # EDEMA_BIOMARKER in prod, NWUCALCULATION in dev environment
    
    for resource_dir in resource_dirs:
        directory = sessionId+'_'+subject_id+'_'+resource_dir
        full_uri = get_resourcefiles_metadata_as_csv(URI, resource_dir)

        print('full uri:', full_uri)
        Path('./'+directory).mkdir(parents=True, exist_ok=True)
        download_resource_file(full_uri, os.path.basename(full_uri), directory)
    
    custom_variables_url = '/app/action/XDATActionRouter/xdataction/xml_file/search_element/xnat%3AsubjectData/search_field/xnat%3AsubjectData.ID/search_value/{0}/popup/false/project/WashU'.format(subject_id)

    # https://snipr.wustl.edu/app/action/XDATActionRouter/xdataction/xml/search_element/xnat%3AsubjectData/search_field/xnat%3AsubjectData.ID/search_value/SNIPR_S00917/popup/true/project/BJH
    file_name = subject_id+'custom_variable_xml'
    directory = subject_id+'_xmls'
    Path('./'+directory).mkdir(parents=True, exist_ok=True)
    download_resource_file(custom_variables_url, file_name, directory)
    
    (xml, file_name) = fill_info(sessionId, subject_id)

    upload_xml(file_name)

if __name__ == '__main__':
    upload_xml(None)
    
    #one_sample_test()
    '''
    #below for full test
    start = time.time()
    subject_to_sessions = fetch_proper_pair_modularized()
    #with open('useful_subject_to_session.json', "w") as json_file:
    #    json.dump(subject_to_sessions, json_file, indent=2)
    with open('error_subjects.txt', "w") as file:
        for key, value in subject_to_sessions.items():
            file.write(f"{key}: {value}\n")
    end = time.time()
    print('fetch_proper_pair_modularized -- time elapsed in seconds: ', end - start) # ~30 min to execute
    
    start = time.time()
    subject_to_sessions = read_dict()
    all_sessions_scans = list(subject_to_sessions.values())
    

    useful_subject_to_session = find_proper_subject_sessions(all_sessions_scans, subject_to_sessions) # 12 min to execute 
    end = time.time()
    print('find_proper_subject_sessions -- time elapsed in seconds: ', end - start)
    test_main(useful_subject_to_session)
    '''

    