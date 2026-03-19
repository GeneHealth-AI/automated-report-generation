import os
import subprocess

def make_executable_and_run(bash_script_path):
    # Check if the script is executable
    if not os.access(bash_script_path, os.X_OK):
        # Make the script executable
        os.chmod(bash_script_path, 0o755)

    # Run the bash script using subprocess.run
    result = subprocess.run([bash_script_path], capture_output=True, text=True)
def mutation_type(rsid):
    rsid = rsid.upper()
    # Returns the mutation type by looking at the protein mutations
    if 'FS' in rsid or '*' in rsid or 'DEL' in rsid:
        return True
    return False
def runent(rsidlist):
    returnlist = []
    keytoscore = {}
    ENTPRISE_DIR = '/home/ec2-user/entprise'
    SCRIPT       = os.path.join(ENTPRISE_DIR, 'scan_genfea3_pred.job')
    RSID_LST     = os.path.join(ENTPRISE_DIR, 'rsid.lst')
    RSID_OUT     = os.path.join(ENTPRISE_DIR, 'rsid.lst_pred.out')

    # Creates list for score calculation - each mutation on its own line
    with open(RSID_LST, 'w') as rl:
        for item in rsidlist:
            rl.write(item.rstrip('\n') + '\n')

    # Ensure script is executable
    os.chmod(SCRIPT, 0o755)

    result = subprocess.run(
        [SCRIPT, RSID_LST],
        capture_output=True, text=True,
        cwd=ENTPRISE_DIR
    )

    if not os.path.exists(RSID_OUT):
        return returnlist

    with open(RSID_OUT, 'r') as results:
        # Opens results and reformats them to be put in masterfile
        results = results.read()
        results = results.split('\n')
        for i in range(len(results)):
            res = results[i].split("\t")
            for j in range(len(res)):
                res[j] = res[j].strip(' ')
            if res[0]:
                keytoscore[f"{res[0]}\t{res[1]}\t{res[2]}\t{res[3]}"] = res[4]
    for entry in rsidlist:
        if entry.strip('\n') in keytoscore:
            returnlist.append(entry.strip('\n') +'\t' + keytoscore[entry.strip('\n')])

    return returnlist
def runentx(rsidlist):
    # Executes the given frameshift and nonsense mutations for EntpriseX
    ENTPRISEX_DIR = '/home/ec2-user/entpriseX'
    RSID_LST = os.path.join(ENTPRISEX_DIR, 'rsid.lst')
    RSID_OUT = os.path.join(ENTPRISEX_DIR, 'rsid.lst_pred.out')

    returnlist = []
    with open(RSID_LST, 'w') as rl:
        for item in rsidlist:
            rl.write(item.rstrip('\n') + '\n')

    script = os.path.join(ENTPRISEX_DIR, 'scan_pred.job')
    os.chmod(script, 0o755)
    subprocess.run(
        [script, RSID_LST],
        capture_output=True, text=True,
        cwd=ENTPRISEX_DIR
    )

    if not os.path.exists(RSID_OUT):
        return returnlist

    with open(RSID_OUT, 'r') as results:
        results = results.read().split('\n')
        return results
   
    
# entry = f"('{rsid}','{allele}')\t{protein}\t{position}\t{original}\t{change}\t{gene}\t{extract_frequencies(decodedfrequency,allele)}".upper()
    
def ProteinScoreCalculation(rsidlist):
    # Intakes a person's protein mutations; seperates them based on types; and returns them in masterfile format
    vp = set()
    k2t = {}
    entxk2 = {}
    entry = set()
    # Build set of valid protein IDs from human_ref.lst (col 2 = NP accession)
    ent_db = '/home/ec2-user/entprise/human_ref.lst'
    if os.path.exists(ent_db):
        with open(ent_db, 'r') as e:
            for line in e:
                parts = line.strip().split()
                if len(parts) >= 2:
                    vp.add(parts[1])
    else:
        print(f"Warning: human_ref.lst not found at {ent_db}. Scoring might be limited.")
    for term in rsidlist:
        term = term.split("\t")
        if term[1] in vp:
            key = f'{term[1]}\t{term[2]}\t{term[3]}\t{term[4]}'
            k2t[key] = f"{term[0]}\t{term[1]}\t{term[2]}\t{term[3]}\t{term[4]}\tREPLACE\n"
            entry.add(key)
            entxk2[f'{term[1]} {term[2]}'] = f"{term[0]}\t{term[1]}\t{term[2]}\t{term[3]}\t{term[4]}\tREPLACE\n"

    rsidlist = [term for term in entry if not '?' in term]
    entx = [rsid for rsid in rsidlist if mutation_type(rsid)] # EntpriseX list of rsIDs
    ent = [rsid for rsid in rsidlist if not mutation_type(rsid)] # Entprise list of rsIDs
    rlx = []
    if entx:
        rlx = runentx(entx)
    rle = runent(ent)
    returnlist = []
    for entry in rle:
        if not entry:
            continue
        term = entry.strip('\n').split('\t')
        key = f'{term[0]}\t{term[1]}\t{term[2]}\t{term[3]}'
        lin = k2t[key].replace('\n','')
        returnlist.append(lin.replace("REPLACE",term[4])+'\n')# Replaces REPLACE with entprise or entprise x scores
    for entry in rlx:
        if not entry:
            continue
        term = entry.strip('\n').split(' ')
        key = f"{term[0]} {term[1]}"
        score = term[2]
        lin = entxk2[key].replace('\n','')
        new_entry = entxk2[key].replace("REPLACE",score)
        returnlist.append(new_entry.replace('\n','')+'\n') # a second new line character is being added somewhere but this fixes that 
    return returnlist
