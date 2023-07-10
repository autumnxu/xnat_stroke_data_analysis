# imports 
import pandas as pd
import json
import os
from pathlib import Path
import glob
import pydicom
import xmltodict
import pprint

from xnatSession import XnatSession


# global variables
XNAT_HOST = 'https://snipr-dev-test1.nrg.wustl.edu'
XNAT_USER = 'autumnxu'
XNAT_PASS = 'abc123'
'''
TODO
    custom variables  
    upload xml
'''


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
    json_res = response.json()
    metadata_masks=json_res['ResultSet']['Result']
    jsonStr = json.dumps(metadata_masks)
    
    #full_uri = json.loads(jsonStr)[0]['URI']
    #here add checks for variable file type 
    #print('viewing structure')
    #print(metadata_masks)
    if resource_dir == 'NWUCALCULATION':
        uri_temp = [d['URI'] for d in metadata_masks if d['URI'].endswith('.csv')]
        full_uri = uri_temp[0]
    elif resource_dir == 'DICOM':
        full_uri = metadata_masks[0]['URI']
    
    print('json string of metadata masks', url)
    df = pd.read_json(jsonStr)
    df.to_csv(os.path.basename(URI)+'_'+resource_dir+'metadata.csv',index=False)
    return full_uri

# this function would downlaod a file as dicatated by the url, saving to dir_to_save
def downloadresourcefilewithuri_name_py(url,name,dir_to_save):
    xnatSession = XnatSession(username=XNAT_USER, password=XNAT_PASS, host=XNAT_HOST)
    xnatSession.renew_httpsession()
    response = xnatSession.httpsess.get(xnatSession.host + url)
    zipfilename=os.path.join(dir_to_save,name) #sessionId+scanId+'.zip'
    print(zipfilename)
    # file opened for writing in binary mode
    with open(zipfilename, "wb") as f:
        for chunk in response.iter_content(chunk_size=512):
            if chunk:  # filter out keep-alive new chunks
                print('ever here?????')  # here 
                f.write(chunk)
    xnatSession.close_httpsession()

'''
thoughts
'''
def fill_info(sessionId):
    
    dicom_dict = grab_dicom_info(sessionId)
    nwu_dict = grab_nwu_info(sessionId)
    # functionality to add 
    # cutom_variables_dict = grab_custom_variables(sessionId)
    full_dict = {**dicom_dict, **nwu_dict}
    # print('full dict:', full_dict)  this work 
    write_to_blank_xml(full_dict, sessionId)

def write_to_blank_xml(full_dict, sessionId):
    print('entering write_to_blank_xml')
    with open('blank_template.xml', 'r', encoding='utf-8') as file:
        xml_read = file.read()
    # Use xmltodict to parse and convert the XML document
    dict_of_xml = xmltodict.parse(xml_read)
    datatype_name = list(dict_of_xml.keys())[0]
    ''' for testing -- this part works now
    # Print the dictionary
    #print('dict_of_xml', dict_of_xml)

    for key in dict_of_xml:
        print('each key of dict_of_xml', key)
   
    #datatype_name = datatype_names
    print('one level in -- dict_of_xml:', type(datatype_name))
    '''
    
    # subject id: assession number of subject 
    # fill out xnat subject id
    dict_of_xml[datatype_name]['xnat:subject_ID'] = sessionId
    for key in full_dict:
        xml_workshop_filed = 'workshop:'+key
        dict_of_xml[datatype_name][xml_workshop_filed] = full_dict[key]

    ''' for testing ... xml now filled
     for key in dict_of_xml[datatype_name]:
        print(key, dict_of_xml[datatype_name][key])
    '''

    modified_xml = xmltodict.unparse(dict_of_xml, pretty=True)
    # SAVE xml into a file
    print('view filled xml')
    print(modified_xml)
    # this name may cause error for uploading xml downstream
    file1 = open("12_28_22_04_09_43.xml","w")
    file1.write(modified_xml)
    file1.close()


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
    filepaths = glob.glob(to_match, recursive=True)
    print('net water uptake calculations -- file to fetch info', filepaths[0])    
    dataframe = pd.read_csv(filepaths[0])
    print('possible values to fetch:', dataframe.columns)
    # fill in values 
    net_water_uptake_dict = {}
    net_water_uptake_dict['net_water_uptake'] = dataframe.loc[0, "NWU"]
    net_water_uptake_dict['total_csf_volumn'] = dataframe.loc[0, "TOTAL CSF VOLUME"]
    net_water_uptake_dict['csf_ratio'] =  dataframe.loc[0, "CSF RATIO"]
    print(net_water_uptake_dict)
    return net_water_uptake_dict

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
    print('dicom file to fetch info', filepaths[0])    
    ds = pydicom.dcmread(filepaths[0])
    # to return 
    dicom_dict = {}
    acquisition_date = ds[0x0008, 0x0022].value
    acquisition_date= acquisition_date[:4]+'-'+acquisition_date[4:6]+'-'+acquisition_date[6:]
    print(acquisition_date)
    dicom_dict['Scan_Date'] = acquisition_date
    dicom_dict['Scan_Timing'] =  ds[0x0008, 0x0032].value
    pixel_spacing = ds[0x0028, 0x0030]
    dicom_dict['selected_scan_number'] = ds[0x0020, 0x0012].value
    # for complete image size
    dicom_dict['DICOM_Pixel_Size_X'] = pixel_spacing[0]
    dicom_dict['DICOM_Pixel_Size_Y'] = pixel_spacing[1]
    dicom_dict['slice_thickness'] = ds[0x0018, 0x0050].value
    # for resolution
    dicom_dict['X_Dimension'] = ds[0x0028, 0x0010].value # row
    dicom_dict['Y_Dimension'] = ds[0x0028, 0x0011].value # column
    dicom_dict['scan_id'] = ds[0x0020, 0x0011].value # series/aquisition number
    dicom_dict['CT_Scanner'] = ds[0x0008, 0x1090].value
    '''
    number of slices: count the number of files in DICOM folder
        now not needed, since only downloade done dicom file from the subject
    slice_num = len(glob.glob(os.path.dirname(filepath)+'/*.dcm'))
    slice_num=len(filepaths)
    '''
    print(dicom_dict)
    print(ds[0x0008, 0x0022].value)
    print(ds[0x0008, 0x0022].keyword)
    print('exiting grab_dicom_info')
    return dicom_dict

if __name__ == '__main__':
    print("executing tasks in main")
    URI = '/data/experiments/SNIPR_E03517/scans/2' # further code needed to automate the fetching of this uri
    resource_dir='NWUCALCULATION'
    sessionId = 'SNIPR_E03517'
    directory = sessionId+'2'+resource_dir
    full_uri = get_resourcefiles_metadata_as_csv(URI, resource_dir)
    #filename = os.path.basename(full_uri)
    #dir_path = './'+directory
    print('full uri:', full_uri)
    Path('./'+directory).mkdir(parents=True, exist_ok=True)
    downloadresourcefilewithuri_name_py(full_uri, os.path.basename(full_uri), directory)
    fill_info(sessionId)