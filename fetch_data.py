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

# global variables
XNAT_HOST = 'https://snipr-dev-test1.nrg.wustl.edu'
XNAT_USER = 'autumnxu'
XNAT_PASS = 'abc123'


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
    
    #full_uri = json.loads(jsonStr)[0]['URI']
    #here add checks for variable file type 
    #print('viewing structure')
    #print(metadata_masks)
    if resource_dir == 'NWUCALCULATION':
        uri_temp = [d['URI'] for d in metadata_masks if d['URI'].endswith('.csv')]
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
    dicom_dict = grab_dicom_info(sessionId)
    nwu_dict = grab_nwu_info(sessionId)
    if not nwu_dict:
        return (None, None)
    cutom_variables_dict = grab_custom_variables(subject_id, sessionId)
    
    if dicom_dict is None or nwu_dict is None or cutom_variables_dict is None:
        print('information incomplete for', sessionId, subject_id)
        return (None, None)
    full_dict = {**dicom_dict, **nwu_dict, **cutom_variables_dict}

    full_dict["Elapsed_From_Stroke"] = time_diff(full_dict["Scan_Time"], full_dict["Stroke_Time"], full_dict["Scan_Date"], full_dict["Stroke_Date"])
    file_name = write_to_blank_xml(full_dict, sessionId, subject_id)
    print("end of fill_info() -- is it none?", file_name)
    return (full_dict, file_name)


def write_to_blank_xml(full_dict, sessionId, subject_id):
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
    # give unique label and make pyxnat happy
    dict_of_xml[datatype_name]['@ID'] = ''
    dict_of_xml[datatype_name]['@label'] = 'stroke_edema_'+sessionId+'_'+subject_id # later in this format: CT Session: BJH_001_11112019
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
    net_water_uptake_dict['Infarct_Volumn'] = round(dataframe.loc[0, "INFARCT VOLUME"], decimal_place)
    net_water_uptake_dict['Total_Cerebrospinal_Fluid_Volume'] = round(dataframe.loc[0, "TOTAL CSF VOLUME"], decimal_place)
    net_water_uptake_dict['Cerebrospinal_Fluid_Ratio'] = round(dataframe.loc[0, "CSF RATIO"], decimal_place)
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

    dict_of_xml = xmltodict.parse(xml_read)
    list_of_dict = dict_of_xml['xnat:Subject']['xnat:fields']['xnat:field']
    value_of_interest = [dict['#text'] for dict in list_of_dict if dict['@name'] == 'stroke_onset_time']
    padded = value_of_interest[0]+':00'

    cerebral_stroke = [dict['#text'] for dict in list_of_dict if dict['@name'] == 'Cerebral_Edema_Grading_for_Ischemic_Stroke']

    stroke_date = [dict['#text'] for dict in list_of_dict if dict['@name'] == 'stroke_onset_date']
    
    cerebral_stroke = cerebral_stroke[0]
    stroke_date = stroke_date[0]
    # mm/dd/yyyy -> yyyy-mm-dd
    padded_date = stroke_date[6:]+'-'+stroke_date[:2]+'-'+stroke_date[3:5]
    custom_variables_dict['Stroke_Time'] = padded
    custom_variables_dict['Stroke_Date'] = padded_date
    custom_variables_dict['Cerebral_Edema_Grade'] = cerebral_stroke[0]
    usability = [dict['#text'] for dict in list_of_dict if dict['@name'] == 'quality']


    list_of_dict = dict_of_xml['xnat:Subject']['xnat:experiments']['xnat:experiment']
    scan_info = [dict for dict in list_of_dict if dict['@ID'] == session_id]
    tmp = [d for d in scan_info if "xnat:scans" in d]
    tmp = tmp[0]
    tmp = tmp['xnat:scans']['xnat:scan']
    tmp = next((d for d in tmp if d.get("@type") == "Z-Axial-Brain"), None)
    usability = tmp['xnat:quality']

    custom_variables_dict['Scan_Quality'] = usability
    print(custom_variables_dict)
    return custom_variables_dict

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
    acquisition_date = ds[0x0008, 0x0022].value
    acquisition_date= acquisition_date[:4]+'-'+acquisition_date[4:6]+'-'+acquisition_date[6:]
    print(acquisition_date)
    dicom_dict['Scan_Date'] = acquisition_date
    acquisition_time = ds[0x0008, 0x0032].value # needs to be fixed
    acquisition_time = acquisition_time.split('.')[0]
    dicom_dict['Scan_Time']  = acquisition_time[:2] + ':' + acquisition_time[2:4] + ':' + acquisition_time[4:] 

    pixel_spacing = ds[0x0028, 0x0030]
    dicom_dict['Scan_Selected'] = ds[0x0020, 0x0012].value
    # for complete image size
    decimal_place = 2
    dicom_dict['DICOM_pixel_size_x'] = round(pixel_spacing[0], decimal_place)
    dicom_dict['DICOM_pixel_size_y'] = round(pixel_spacing[1], decimal_place)
    dicom_dict['Z_Dimension'] = ds[0x0018, 0x0050].value # argue with Atul for whether this is needed
    # for resolution
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
    session_id = [os.path.basename(entry['URI']) for entry in json_res if entry['project'] == 'BJH']
    # here we need BJH_xxx 
    return session_id

# either this is buggy or the above function is buggy
def fetch_subjectid(subject_id_url):
    url = (subject_id_url+'/?format=json')
    print('fetch_sessionid -- full url:', url)
    xnatSession = XnatSession(username=XNAT_USER, password=XNAT_PASS, host=XNAT_HOST)
    xnatSession.renew_httpsession()
    response = xnatSession.httpsess.get(xnatSession.host + url)
    xnatSession.close_httpsession()
    json_res = response.json()['ResultSet']['Result']
    #print('how to link subject id to subject id?')
    #print(json_res)
    subject_ids = [os.path.basename(entry['ID']) for entry in json_res if entry['project'] == 'BJH']
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
    xml_file_path = './'+xml
    with open(xml_file_path, 'rb') as xml_file:
        response = requests.post(url, auth=(XNAT_USER, XNAT_PASS), files={'item': xml_file})
        try:
            response.raise_for_status()
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
        'workshop:biosampleCollection/Infarct_Volumn': '212.212',
        'workshop:biosampleCollection/Infarct_Side': 'ememeee',
        'workshop:biosampleCollection/Analysis_Date': '2022-03-02',
        'workshop:biosampleCollection/Version_Date': '2021-04-03',
        'workshop:biosampleCollection/Cerebral_Edema_Grade': 'ememe'
    }
)
'''
    
    

def test_main():
    '''the following code works
    xml = '03_31_23_20_11_46.xml'
    upload_xml(xml)
    '''

    print("executing tasks in main")
    #session_id_url = '/data/experiments'
    #session_ids = fetch_sessionid(session_id_url)
    subject_id_url = '/data/subjects'
    subject_to_sesions = fetch_subjectid(subject_id_url)
    #print("how many subjects?", len(subject_ids))
    print('final dict?')
    print(subject_to_sesions)
    # before automating the session id and subject with the code above, figure out more details below
    partial_execution = 5
    count = 0
    for subject, sessions in subject_to_sesions.items():
        for session_id in sessions:

            URI = '/data/experiments/'+session_id+'/scans/2'
            resource_dir = 'NWUCALCULATION' # 'DICOM' or 'NWUCALCULATION'
            resource_dirs = ['NWUCALCULATION', 'DICOM']
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
            custom_variables_url = '/app/action/XDATActionRouter/xdataction/xml_file/search_element/xnat%3AsubjectData/search_field/xnat%3AsubjectData.ID/search_value/{0}/popup/false/project/WashU'.format(subject)
            file_name = subject+'custom_variable_xml'
            directory = subject+'_xmls'
            Path('./'+directory).mkdir(parents=True, exist_ok=True)
            download_resource_file(custom_variables_url, file_name, directory)
    
            (xml, file_name) = fill_info(session_id, subject)
            '''
            if file_name:
                upload_xml(file_name)
            if xml:
                count = count+1
                if count >= partial_execution:
                    break
            '''
            
        if count >= partial_execution:
                break
    
# parse info here....
def one_sample_test():
    sessionId = 'SNIPR_E03665' #SNIPR_E03517 CT session associated with subject 001
    subject_id = 'SNIPR_S01154' # SNIPR_S01016 this is subject 001, no relevant custom variable uploaded
    URI = '/data/experiments/'+sessionId+'/scans/2'
    resource_dir = 'NWUCALCULATION' # 'DICOM' or 'NWUCALCULATION'
    resource_dirs = ['NWUCALCULATION', 'DICOM']
    for resource_dir in resource_dirs:
        directory = sessionId+'_'+subject_id+'_'+resource_dir
        full_uri = get_resourcefiles_metadata_as_csv(URI, resource_dir)

        print('full uri:', full_uri)
        Path('./'+directory).mkdir(parents=True, exist_ok=True)
        download_resource_file(full_uri, os.path.basename(full_uri), directory)

    custom_variables_url = '/app/action/XDATActionRouter/xdataction/xml_file/search_element/xnat%3AsubjectData/search_field/xnat%3AsubjectData.ID/search_value/{0}/popup/false/project/WashU'.format(subject_id)
    file_name = subject_id+'custom_variable_xml'
    directory = subject_id+'_xmls'
    Path('./'+directory).mkdir(parents=True, exist_ok=True)
    download_resource_file(custom_variables_url, file_name, directory)
    
    (xml, file_name) = fill_info(sessionId, subject_id)

    upload_xml(file_name)
if __name__ == '__main__':
    #test_main()
    one_sample_test()
    