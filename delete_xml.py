import os
import glob
import shutil # add functionality to delete folders no longer in need

# Get a list of all .xml files in the current directory
xml_files = glob.glob("*.xml")

# If there are no .xml files, exit the script
if len(xml_files) == 0:
    print("No .xml files found in current directory")
    exit()

# Remove the template.xml file from the list of files to delete
xml_files.remove("blank_template.xml")

# Sort the remaining .xml files by modification time
xml_files.sort(key=os.path.getmtime)

# If there is more than one file (excluding template.xml), delete all but the most recent one
if len(xml_files) > 1:
    files_to_delete = xml_files[:-1]
    for file in files_to_delete:
        os.remove(file)


# delete all folderes that start with "SNIPR_"
for root, dirs, files in os.walk("."):
    for d in dirs:
        if d.startswith("SNIPR_"):
            path = os.path.join(root, d)
            if os.path.isdir(path) and os.listdir(path):
                os.system("rm -r '{}'".format(path))



# define the root directory where the search should begin
root_dir = './'

# loop through all directories and files in the root directory
for root, dirs, files in os.walk(root_dir, topdown=False):
    
    # loop through all subdirectories
    for dir_name in dirs:
        
        # check if the directory name contains "SNIPR_"
        if "SNIPR02_" in dir_name:
            
            # join the root directory with the directory name to create the full path
            dir_path = os.path.join(root, dir_name)
            
            # delete the directory and all its contents
            print(f"Deleting {dir_path}")
            shutil.rmtree(dir_path)
