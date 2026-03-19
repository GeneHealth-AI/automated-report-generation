import os
import re
from pipeline.ProteinCalculation import ProteinScoreCalculation
from openai import OpenAI
import boto3


client = None
s3 = boto3.client('s3')

def _get_openai_client():
    global client
    if client is None:
        client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
    return client
def get_file_from_bucket(file_name,bucket_name):
    '''Gets the file imn the specified buckets and returns it as a list split by line'''
    response = s3.get_object(Bucket=bucket_name, Key=file_name)
    file_content = response['Body'].read().decode('utf-8')
    lines = file_content.split('\n')
    return lines 

def extract_rsIDs_mutations(file_name,bucket_name):
    '''For a given VCF, returns a list of tupules of rsID, allele'''
    idandallele = []
    vcffile = get_file_from_bucket(file_name,bucket_name)
    for line in vcffile:
        if not line.startswith('#'):
            line = line.split("\t")
            idandallele.append((line[2],line[4])) # verify this is the actua
    return idandallele
def current_master_rsid(file_name,bucket_name):
    '''returns all the current had rsIDs and their positions'''
    currentrsids = set()
    cmf = get_file_from_bucket(file_name,bucket_name) # gets current masterfile
    for line in cmf:
        line = line.split("\t")
        if line[0] != '': #handles end of file 
            tup = eval(line[0])
            currentrsids.add(tup[0]) # Adds rsID
    return currentrsids
def current_master_positions(file_name,bucket_name):
    '''returns all the current had rsIDs and their positions'''
    currentpos = set()
    cmf = get_file_from_bucket(file_name,bucket_name) # gets current masterfile
    for line in cmf:
        line = line.split("\t")
        if line[0] != '': #handles end of file 
            tup = eval(line[0])
            currentpos.add(line[-1]) # adds chromsome and position of form chr#:position
    return currentpos

def extract_positions(vcffile):
    '''Returns all the nucleotide positions and rsIDs (if there are any) in a given VCF file'''
    positions = set()
    rsids = set()
    vf = get_file_from_bucket(vcffile,'exomeinputbucket')
    for line in vf:
        if not line.startswith('#') and line:
            line = line.split('\t')
            chromsome = line[0].split(".")[-1]
            position = line[1]
            rsid = line[2]
            if 'rs' in rsid:
                rsids.add(rsid.strip())
            else:
                positions.add(f"{chromsome}:{position}".strip())
    return positions, rsids
def create_s3_file(file_name,bucket_name, old_entries,new_entries=[]):
    old_entries.extend(new_entries)
    
    #join the modified lines back into a single string
    updated_content = '\n'.join(old_entries)
    #write updated content back to the S3 bucket
    s3.put_object(Bucket=bucket_name, Key=file_name, Body=updated_content.encode('utf-8'))
    
def update_s3_file(file_name,bucket_name,new_content):
    old = get_file_from_bucket(file_name,bucket_name)
    create_s3_file(file_name,bucket_name,old,new_content)
    print(f"{file_name} in {bucket_name} updated. ")
    
def create_s3_folder(bucket_name, folder_name):
    response = s3.put_object(Bucket=bucket_name, Key=folder_name + '/')
    return response

def get_rsID_report(ram,patientorphysician=True):
    MODEL="gpt-4o"
    client = _get_openai_client()
    if patientorphysician:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[
            {"role": "system", "content": "You help in biology research and personalized disease and drug predictions. Please help me in my queries."}, 
            {"role": "user", "content": f"Provide a concise report on drug metabolism of this rsID and mutation:{ram}; please just provide what drugs this affects and how I should affect my dosage or taking of them"}  
         ]
    )
    else:
         completion = client.chat.completions.create(
            model=MODEL,
            messages=[
            {"role": "system", "content": "You help in biology research and personalized disease and drug predictions. Please help me in my queries."}, # <-- This is the system message that provides context to the model
            {"role": "user", "content": f"""Provide a table based on this drug metabolism data that includes the name of the drug followed by suggested specific (Such as increased or decreased) doseage adjustment/efficacy
             based on mutation from research you have conducted in the clinical literature. Also please include all sources at the bottom and have the catergories be: drug, assoicated mutated rsIDs, Doseage Modification and
             proposed change in efficacy if there is any. When you disuss doseage modification or change in efficacy, be specific, i.e. take more of this drug or according to the literature this drug will not be efficacious
             for you for treating a specific disease. {ram}"""}  
         ]
    )   
    return completion.choices[0].message.content
def generate_drug_metabolism_report(entries,name):
    rsids = []
    for term in rsids:
        term = term.split('\t')
        rsids.append(eval(term[0]))
    metabolismrsids = {}
    with open("./mutationstodrugs",'r') as mtd:
        for line in mtd:
            linebeforesplit = line
            line = line.split("\t")
            rsid = line[0]
            allele = line[1].split(":")[-1]
            conditions = line[3]
            metabolismrsids[(rsid,allele)] = linebeforesplit
    generationstring = ""
    for pair in rsids:
        if pair in metabolismrsids.keys():
            generationstring += metabolismrsids[pair] + ', '
    professionaloutput = get_rsID_report(generationstring,True)
    patientoutput = get_rsID_report(generationstring,False)
    s3.put_object(Bucket="ghcompletedreports", Key=f"{name}/patient_drug_metabolism", Body=patientoutput.encode('utf-8'))
    s3.put_object(Bucket="ghcompletedreports", Key=f"{name}/professional_drug_metabolism", Body=professionaloutput.encode('utf-8'))
def pos2rsid():
    i = 0
    pos2rsid = {}
    with open('./Abridged00','r') as o:
       for line in o:
            print(i)
            i += 1
            line = line.split('\t')
            pos = line[1]
            rsid = line[2]
            pos2rsid[chrs + ':' + pos] = rsid
    return pos2rsid

def get_rsid(line):
    """
    Extract rsID from a VCF line. Tries multiple methods to find the rsID:
    1. First checks the standard ID column (3rd column)
    2. Then looks for rsIDs in the INFO field with various delimiters
    3. Finally does a general search for 'rs' followed by numbers anywhere in the line
    
    Args:
        line (str): A line from a VCF file
        
    Returns:
        str: The rsID if found, or "." if not found
    """
    # Split the line into fields
    fields = line.split('\t')
    
    # Check if there are enough fields and the ID field (3rd column) contains an rsID
    if len(fields) >= 3 and fields[2].startswith('rs'):
        return fields[2]
    
    # If the ID field doesn't have an rsID, look in the INFO field (8th column)
    if len(fields) >= 8:
        info_field = fields[7]
        
        # Method 1: Look for rsID in standard format with pipe delimiters
        pipe_match = re.search(r'\|rs(\d+)\|', info_field)
        if pipe_match:
            return f"rs{pipe_match.group(1)}"
        
        # Method 2: Look for rsID with pipe and ampersand delimiters
        pipe_amp_match = re.search(r'\|rs(\d+)&', info_field)
        if pipe_amp_match:
            return f"rs{pipe_amp_match.group(1)}"
        
        # Method 3: Look for rsID in CSQ field
        if 'CSQ=' in info_field:
            csq_parts = info_field.split('CSQ=')[1].split(',')
            for part in csq_parts:
                rs_match = re.search(r'rs(\d+)', part)
                if rs_match:
                    return f"rs{rs_match.group(1)}"
    
    # Method 4: General search for rsID anywhere in the line
    general_match = re.search(r'rs(\d+)', line)
    if general_match:
        return f"rs{general_match.group(1)}"
    
    # If no rsID found, return "." (standard VCF missing value)
    return "."

def extract_mutations(input_vcf):
    mutations = set()
    # Dictionary for standardizing amino acid names to uppercase three-letter codes
    aa_standardize = {
        'Ala': 'ALA', 'Arg': 'ARG', 'Asn': 'ASN', 'Asp': 'ASP', 'Cys': 'CYS',
        'Glu': 'GLU', 'Gln': 'GLN', 'Gly': 'GLY', 'His': 'HIS', 'Ile': 'ILE',
        'Leu': 'LEU', 'Lys': 'LYS', 'Met': 'MET', 'Phe': 'PHE', 'Pro': 'PRO',
        'Ser': 'SER', 'Thr': 'THR', 'Trp': 'TRP', 'Tyr': 'TYR', 'Val': 'VAL',
        'Ter': 'TER'
    }

    # Read VCF file
    with open(input_vcf, 'r') as vcf:
        for line in vcf:
            print(len(mutations))
            if line.startswith('#') or not line.strip():
                continue
                
            fields = line.split('\t')
            if len(fields) >= 8:
                # Extract chromosome position information
                chrom = fields[0].replace('chr','')
                pos = fields[1]
                ref = fields[3]
                alt = fields[4]
                rsid = get_rsid(line)
                
                info_field = fields[7]
                
                if 'CSQ=' in info_field:
                    csq_parts = info_field.split('CSQ=')[1].split(',')
                    
                    for part in csq_parts:
                        # Check for different types of mutations
                        is_relevant = any(variant_type in part for variant_type in [
                            'missense_variant',
                            'stop_gained',
                            'frameshift_variant',
                            'stop_lost',
                            'inframe_insertion',
                            'inframe_deletion'
                        ])
                        
                        if is_relevant:
                            # Extract NP number
                            np_match = re.search(r'NP_\d+\.\d+', part)
                            if not np_match:
                                continue
                            
                            np_accession = np_match.group(0)
                            
                            # Pattern 1: Standard amino acid changes (e.g., Ala123Ser)
                            aa_match = re.search(r'[^a-z]([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})[^a-z]', part)
                            if aa_match:
                                orig_aa = aa_standardize.get(aa_match.group(1))
                                position = aa_match.group(2)
                                new_aa = aa_standardize.get(aa_match.group(3))
                                
                                if orig_aa and new_aa:
                                    mutation = f"('{rsid}','{alt}')\t{np_accession}\t{position}\t{orig_aa}\t{new_aa}\n"
                                    mutations.add(mutation)
                                continue
                            
                            # Pattern 2: Frameshift mutations (e.g., Gly123ArgfsTer34)
                            fs_match = re.search(r'([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})fs(?:Ter(\d+))?', part)
                            if fs_match:
                                orig_aa = aa_standardize.get(fs_match.group(1))
                                position = fs_match.group(2)
                                new_aa = aa_standardize.get(fs_match.group(3))
                                ter_pos = fs_match.group(4) if fs_match.group(4) else ""
                                
                                if orig_aa and new_aa:
                                    mutation = f"('{rsid}','{alt}')\t{np_accession}\t{position}\t{orig_aa}\t{new_aa}FSTER{ter_pos}\n"
                                    mutations.add(mutation)
                                continue
                            
                            # Pattern 3: Simple frameshift (e.g., Gly123fs)
                            simple_fs_match = re.search(r'([A-Z][a-z]{2})(\d+)fs', part)
                            if simple_fs_match:
                                orig_aa = aa_standardize.get(simple_fs_match.group(1))
                                position = simple_fs_match.group(2)
                                if orig_aa:
                                    mutation = f"('{rsid}','{alt}')\t{np_accession}\t{position}\t{orig_aa}\t{orig_aa}FSTER\n"
                                    mutations.add(mutation)
                                continue
                            
                            # Pattern 4: Termination mutations (e.g., Trp123Ter or Trp123*)
                            ter_match = re.search(r'([A-Z][a-z]{2})(\d+)(?:Ter|\*)', part)
                            if ter_match:
                                orig_aa = aa_standardize.get(ter_match.group(1))
                                position = ter_match.group(2)
                                if orig_aa:
                                    mutation = f"('{rsid}','{alt}')\t{np_accession}\t{position}\t{orig_aa}\t{orig_aa}TER\n"
                                    mutations.add(mutation)
                                continue
                            
                            # Pattern 5: Extension mutations (stop loss) (e.g., Ter123Trpext*)
                            ext_match = re.search(r'(?:Ter|\*)(\d+)([A-Z][a-z]{2})ext', part)
                            if ext_match:
                                position = ext_match.group(1)
                                new_aa = aa_standardize.get(ext_match.group(2))
                                if new_aa:
                                    mutation = f"('{rsid}','{alt}')\t{np_accession}\t{position}\tTER\t{new_aa}\n"
                                    mutations.add(mutation)
                                continue
    
    return mutations