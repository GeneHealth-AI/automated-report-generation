import boto3
import heapdict
import statistics

MIN_SCORE = .2
s3 = boto3.client('s3')

def get_file_from_bucket(file_name,bucket_name):
    response = s3.get_object(Bucket=bucket_name, Key=file_name)
    file_content = response['Body'].read().decode('utf-8')
    lines = file_content.split('\n')
    return lines 
def create_s3_file(file_name,bucket_name, text):
    s3.put_object(Bucket=bucket_name, Key=file_name, Body=text.encode('utf-8'))
def get_protein_numbers():
    """Returns a dictionary that given a protein returns the number of protein-protein interactions it has
    """
    ppi = {}
    hippie = get_file_from_bucket("hippie_current.txt",'masterfilebucket')
    for line in hippie:
        if line:
            line = line.split('\t')
            prot = line[0].replace('_HUMAN','')
            if not prot in ppi.keys():
                ppi[prot] = set()
            ppi[prot].add(line[2])
    ppinum = {}
    for term in ppi.keys():
        ppinum[term] = len(ppi[term])
    return ppinum
def generate_pathways():
    '''
    Returns a dictionary that given a pathway returns all the proteins it interacts with
    '''
    GenePathwaysFile = get_file_from_bucket('CTD_genes_pathways.txt','masterfilebucket')
    GenePathways = {}
    for line in GenePathwaysFile:
        if not 'GeneSymbol' in line and line:
            line = line.strip('\n').split(" | ")
            for i in range(len(line)):
                line[i] = line[i].strip()
            pathway = line[1]
            gene = line[0]
            if not pathway in GenePathways.keys():
                GenePathways[pathway] = []
            GenePathways[pathway].append(gene)
    return GenePathways
def Generate_Protein_Associations():
    '''Returns a protein to the list of all the proteins it interacts with according to HIPPIE (Human Integrated Protein Protein )'''
    GetInteractionsFiles = get_file_from_bucket('hippie_current.txt','masterfilebucket')
    Protein2Interactions = {}
    for line in GetInteractionsFiles:
        line = line.split('\t')
        protein1 = line[0].replace("_HUMAN",'')
        protein2 = line[2].replace("_HUMAN",'')
        if not protein1 in Protein2Interactions.keys():
            Protein2Interactions[protein1] = set()
        Protein2Interactions[protein1].add(protein2)
    return Protein2Interactions
def construct_knowgene_results():
    '''
    Returns a dictionary that gives a gene's disease predictions from knowgene above minimum score'''
    MINIMUM_SCORE = .3
    gene2predictions = {}
    knowgeneresults = get_file_from_bucket('allproteins2knowgene','masterfilebucket')
    for line in knowgeneresults:
        line = line.split('\t')
        diseaselist = []
        gene = line[0]
        diseases = line[1].split(';')
        for entry in diseases:
            entry = entry.split(':')
            if eval(entry[0]) > MINIMUM_SCORE:
                diseaselist.append(entry[1])
        gene2predictions[gene] = diseaselist
    return gene2predictions
def protein2genes():
    file = get_file_from_bucket('allowableproteins','masterfilebucket')
    protein2gene = {}
    for line in file:
        if line:
            line = line.split(' ')
            protein2gene[line[2]] = line[1]
    return protein2gene
def toNP():
    file = get_file_from_bucket('allowableproteins','masterfilebucket')
    gene2protein = {}
    for line in file:
        if line:
            line = line.split(' ')
            gene2protein[line[1]] = line[2]
    return gene2protein
def pathway_diseases():
    """
    returns top knowgene hits for a pathway by looking all of the proteins in the pathway and keeping track of the 
    number of times each disease appeared
    """
    convertproteins = toNP()
    protein2predictions = construct_knowgene_results()
    pathways = generate_pathways()
    pathwaytodiseases = {}
    for pathway in pathways.keys():
        pathwaytodiseases[pathway] = heapdict.heapdict()
        hp = pathwaytodiseases[pathway]
        proteins = pathways[pathway]
        for protein in proteins:
            if protein in convertproteins.keys():
                protein = convertproteins[protein]
                if protein in protein2predictions.keys():
                    diseases = protein2predictions[protein]
                    for disease in diseases:
                        if not disease in hp.keys():
                            hp[disease] = -1
                        else:
                            hp[disease] -= 1
    return pathwaytodiseases
def pathway_statistics(ppicounts):
    """
    Given a list of the number that each protein interacts with it return the ppi average and standard deviation of a given pathway
    """
    if len(ppicounts) > 1:
        std_dev = statistics.stdev(ppicounts)
        avg = statistics.mean(ppicounts)
    else:
        std_dev = 0
        avg = 0
    return std_dev, avg
def generate_disease_categories():
    disease_categories = get_file_from_bucket('final_specific_refined_reclassified_diseases.tsv','masterfilebucket')
    disease2categories = {}
    for line in disease_categories:
        if not line.startswith('Disease,Category') and line:
            line = line.strip('\n').split('\t')
            categories = line[-1].split(',')
            disease2categories[line[0]] = categories
    return disease2categories

def generate_pathway_predictions(mutatedproteins):
    """
    Intakes protein mutation and outputs score for each pathway
    score is calculated by take z-score * 100 of all the mutated proteins in a pathway divided by the number of proteins in the pathway
    """
    pathwaytoscore = {}
    pathwaytoproteins = generate_pathways()
    proteinnums = get_protein_numbers()
    for pathway in pathwaytoproteins.keys():
        proteins = pathwaytoproteins[pathway]
        containsmutatedprotein = False
        for protein in mutatedproteins:
            if protein in proteins:
                containsmutatedprotein = True
                break
        if containsmutatedprotein:
            pathproteincounts = []
            for protein in proteins:
                if protein in proteinnums.keys():
                    num = proteinnums[protein]
                    pathproteincounts.append(num)
                else:
                    proteins.remove(protein)
            sd, avg = pathway_statistics(pathproteincounts)
            score = 1
            for protein in mutatedproteins:
                if protein in proteins and protein in proteinnums.keys():
                    indscore = (proteinnums[protein] - avg)/sd * 100 if sd != 0 else 1
                    score *= indscore
            pathwaytoscore[pathway] = score
    return pathwaytoscore


def generate_diseases(mutated_proteins,mendeliandiseases,entscore):
    '''
    Given the mutated proteins returns the top 5 diseases from the top 20 disease associated pathways (maximum of 100 diseases return)
    '''
    protein2diseases = construct_knowgene_results()
    fixedmutated_proteins = []
    proteingene = protein2genes()
    for protein in mutated_proteins:
        if protein in proteingene.keys():
            fixedmutated_proteins.append(proteingene[protein])
    mutated_proteins = fixedmutated_proteins
    pathwaytoscore = generate_pathway_predictions(mutated_proteins)
    pathway2diseases = pathway_diseases()
    maxscores = heapdict.heapdict()
    for pathway in pathwaytoscore.keys():
        maxscores[pathway] = -1 * pathwaytoscore[pathway]
    top20pathways = []
    for i in range(10000):
        if len(maxscores) > 0:
            top20pathways.append(maxscores.popitem())
    topdiseases = {}
    for pathway in top20pathways:
        diseases = pathway2diseases[pathway[0]]
        for i in range(30):
            if diseases:
                r = diseases.popitem()
                disease = r[0]
                if disease not in topdiseases.keys():
                    topdiseases[disease] = []
                topdiseases[disease].append(pathway[0])
    g2p = toNP()
    reporttext = ''
    disease2category = generate_disease_categories()
    categories = {}
    diseaselist = []
    for disease in topdiseases.keys():
        try: 
            diseaselist.append(disease)
            category = disease2category[disease]
            for cat in category:
                if cat not in categories.keys():
                    categories[cat] = []
            entry = f"{disease}\t{', '.join(topdiseases[disease])}\t"
            relevantproteins = []
            for protein in mutated_proteins:
                gp = g2p[protein]
                if gp in protein2diseases.keys() and disease in protein2diseases[gp]:
                    relevantproteins.append(protein)
            for c in category:
                if relevantproteins:
                    score = statistics.mean([entscore[g2p[p]] for p in relevantproteins])
                    relevantproteins = list(set(relevantproteins))
                    categories[c].append(entry + ', '.join(relevantproteins)+'\t' + str(score) + '\n')
        except KeyError:
            print(disease)
    for category in categories.keys():
        
        reporttext += f"{category}:\n"
        diseaseentries = categories[category]
        for i in range(len(diseaseentries)):
            reporttext += f"{i+1}\t{diseaseentries[i]}\n"
    reporttext += 'Mendelian Predictions:'
    for i in range(len(mendeliandiseases)):
        disease = mendeliandiseases[i]
        if disease in diseaselist:
            reporttext += f"{i+1}\t{mendeliandiseases[i]}\tYes\n"
        else:
            reporttext += f"{i+1}\t{mendeliandiseases[i]}\tNo\n"
    return reporttext
def get_mendelian():
    file = get_file_from_bucket('MendelianMissense','masterfilebucket')
    key2disease = {}
    for line in file:
        if line:
            line = line.strip('\n').split('\t')
            key2disease[eval(line[0])] = line[1]
    return key2disease
def intake_vcf(muts,filename):
    mendelianmapping = get_mendelian()
    keys = set()
    proteins = []
    entscore = {}
    rsidallele = []
    for mut in muts:
        line = mut.strip('\n').split('\t')
        protein = line[1]
        #rsidallele.append(eval(line[0]))
        if float(line[5]) > MIN_SCORE:
            entscore[protein] = float(line[5])
            proteins.append(protein)
    '''for line in muts:
        line = line.split("\t")
        chromosome = line[0].strip().replace('chr','')
        position = line[1].strip()
        allele = line[3]
        key = (f'{chromosome}:{position}',allele)
        keys.add(key)
    key2protein = {}
    pos2rsid = {}
    masterfile = get_file_from_bucket('masterfile','masterfilebucket')
    for line in masterfile: 
        if line:
            line = line.split('\t')
            allele = eval(line[0])[1]
            position = line[-1]
            if line[5] != '_' and line[5] != 'REPLACE' and eval(line[5]) > 0.5:
                if (position.strip('\n'),allele) not in key2protein.keys():
                    key2protein[(position.strip('\n'),allele)] = []
                key2protein[(position.strip('\n'),allele)].append(line[1])
            rsid = eval(line[0])[0]
            pos2rsid[position] = rsid
    rsidallele = set()
    for term in keys:
        if term[0] in pos2rsid.keys():
            newkey = (pos2rsid[term[0]],term[1])
            rsidallele.add(newkey)
        if term in key2protein.keys():
            proteins.extend(key2protein[term])'''
    mendelian_diseases = []
    #for term in muts:
    #    k = eval(term.split(' \t ')[0])
    #    if k in mendelianmapping.keys() and len(mendelian_diseases) < 3:
    #        mendelian_diseases.append(mendelianmapping[k])
    report = generate_diseases(proteins, mendelian_diseases,entscore)
    create_s3_file(f"{filename}/Complete_Disease_Report",'ghcompletedreports',report)
#muts = open('/home/ec2-user/entprise/AqAm4_ae435b_CKDN250003960-1A_22TG57LT4_L4rsid.lst_pred.out','r').readlines()
#intake_vcf(muts,'AqAm4_ae435b_CKDN250003960-1A_22TG57LT4_L4_disease_report')


# How will incorporate knowgene predictions into this? 
# we have
#   what genes are on each pathways and what genes they ineract with and what proteins each proteins interacts with
# majority prediction on each pathway rule

'''New Prediction Pipeline (this is from purely a biological and biological algorithms report)
1. rsID to protein mutation
2. protein mutation to entprise(X) score
3. protein mutation also to KnowGene predictions
4. Count number of protein mutations in each pathway both total numnber and as percentages of genes in pathway
5. Take top N pathways both in terms of percentage of mutated genes and number of mutated genes
6. Take top M predictions from the protein in the pathway from knowgene and report those as the diseases
7. Additionally take top N proteins with largest number of protein protein interactions and report those diseases as well
    a. We need to verify if knowgene incorporates the number of protein protein interactions into determining disease associations because this may make this method moot

'''