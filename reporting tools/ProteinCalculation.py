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
    # CReates list for score calculation
    with open(f'./entprise/rsid.lst','w') as rl:
        for item in rsidlist:
            rl.write(f'{item}\n')
    ENTPRISE_DIR = '/home/ec2-user/entprise'
    SCRIPT       = os.path.join(ENTPRISE_DIR, 'scan_genfea3_pred.job')
    RSID_LST     = os.path.join(ENTPRISE_DIR, 'rsid.lst')
    RSID_OUT     = os.path.join(ENTPRISE_DIR, 'rsid.lst_pred.out')
    #os.system("./home/ec2-user/entprise/scan_genfea3_pred.job .entprise/rsid.lst")
    
    result = subprocess.run(
        [SCRIPT, RSID_LST],
        capture_output=True, text=True
    )# Executes script to calculate scores for given rsIDs
    #while not (f'rsid.lst_pred.out' in os.listdir('./entprise')): # Waits for results of calculation 
    #    i = 1

    with open(f"./entprise/rsid.lst_pred.out",'r') as results:
        # Opens results and reformats them to be put in masyerfile 
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
    '''try:
        os.remove("./entprise/rsid.lst_pred.out")
        os.remove("./entprise/rsid.lst_pred.lst")
        os.remove("./entprise/rsid.lst_fea.txt")
        #os.remove("./entprise/rsid.lst")
        print('great')
    except Exception:
        print("File clean up failed")'''
    
    return returnlist
def runentx(rsidlist):
    # Executes the given frameshift and nonsense mutations for Entprise
    returnlist = []
    with open(f'./entpriseX/rsid.lst','w') as rl:
        for item in rsidlist:
            rl.write(f'{item}\n')

    os.system('/home/ec2-user/entpriseX/scan_pred.job /home/ec2-user/entpriseX/rsid.lst') # exexcutes Entprise X 
    while not (f'rsid.lst_pred.out' in os.listdir('./entpriseX')):
        i = 1
    with open(f"./entpriseX/rsid.lst_pred.out",'r') as results:
        results = results.read().split('\n')
        return results
   
    
# entry = f"('{rsid}','{allele}')\t{protein}\t{position}\t{original}\t{change}\t{gene}\t{extract_frequencies(decodedfrequency,allele)}".upper()
    
def ProteinScoreCalculation(rsidlist):
    # Intakes a person's protein mutations; seperates them based on types; and returns them in masterfile format
    vp = []
    k2t = {}
    entxk2 = {}
    entry = set()
    with open('./result_genekb', 'r') as e:
        for line in e:
            line = line.split(' ')
            vp.append(line[2])
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
