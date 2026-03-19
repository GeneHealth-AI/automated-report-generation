"""
Enterprise/EnterpriseX scoring wrapper.
Extracts protein mutations from annotated VCF, runs Enterprise (missense)
and EnterpriseX (frameshift/nonsense), outputs disease scores.
"""
import sys
import os
import re
import subprocess

ENTPRISE_DIR = os.environ.get('ENTPRISE_DIR', '/home/ec2-user/entprise')
ENTPRISEX_DIR = os.environ.get('ENTPRISEX_DIR', '/home/ec2-user/entpriseX')

AA_STANDARDIZE = {
    'Ala': 'ALA', 'Arg': 'ARG', 'Asn': 'ASN', 'Asp': 'ASP', 'Cys': 'CYS',
    'Glu': 'GLU', 'Gln': 'GLN', 'Gly': 'GLY', 'His': 'HIS', 'Ile': 'ILE',
    'Leu': 'LEU', 'Lys': 'LYS', 'Met': 'MET', 'Phe': 'PHE', 'Pro': 'PRO',
    'Ser': 'SER', 'Thr': 'THR', 'Trp': 'TRP', 'Tyr': 'TYR', 'Val': 'VAL',
    'Ter': 'TER'
}


def get_rsid(line):
    """Extract rsID from a VCF line."""
    fields = line.split('\t')
    if len(fields) >= 3 and fields[2].startswith('rs'):
        return fields[2]
    if len(fields) >= 8:
        info_field = fields[7]
        for pattern in [r'\|rs(\d+)\|', r'\|rs(\d+)&', r'rs(\d+)']:
            m = re.search(pattern, info_field)
            if m:
                return f"rs{m.group(1)}"
    general = re.search(r'rs(\d+)', line)
    if general:
        return f"rs{general.group(1)}"
    return "."


def load_gene_to_np_mapping():
    """Build gene name -> NP_ accession mapping from list_ref_gene.lst."""
    mapping = {}
    ref_gene_lst = os.path.join(ENTPRISE_DIR, 'list_ref_gene.lst')
    if os.path.exists(ref_gene_lst):
        with open(ref_gene_lst, 'r') as f:
            for line in f:
                parts = line.strip().split()
                # Format: N00001 NP_001005218.1 309 OR5B21
                if len(parts) >= 4 and parts[1].startswith('NP_'):
                    gene_name = parts[3]
                    # Keep first mapping per gene (or could keep all)
                    if gene_name not in mapping:
                        mapping[gene_name] = parts[1]
    return mapping


def extract_mutations(input_vcf):
    """Parse annotated VCF and extract protein mutations with rsIDs."""
    mutations = set()
    gene_to_np = load_gene_to_np_mapping()
    print(f"Loaded {len(gene_to_np)} gene-to-NP mappings for accession resolution.")

    with open(input_vcf, 'r') as vcf:
        for line in vcf:
            if line.startswith('#') or not line.strip():
                continue

            fields = line.split('\t')
            if len(fields) < 8:
                continue

            alt = fields[4]
            rsid = get_rsid(line)
            info_field = fields[7]

            if 'ANN=' not in info_field and 'CSQ=' not in info_field:
                continue

            tag = 'CSQ=' if 'CSQ=' in info_field else 'ANN='
            csq_parts = info_field.split(tag)[1].split(';')[0].split(',')

            for part in csq_parts:
                is_relevant = any(vt in part for vt in [
                    'missense_variant', 'stop_gained', 'frameshift_variant',
                    'stop_lost', 'inframe_insertion', 'inframe_deletion'
                ])
                if not is_relevant:
                    continue

                ann_fields = part.split('|') if tag == 'ANN=' else []

                # Extract protein accession
                np_accession = None
                np_match = re.search(r'NP_\d+\.\d+', part)
                if np_match:
                    np_accession = np_match.group(0)
                elif tag == 'ANN=' and len(ann_fields) > 10:
                    feat_id = ann_fields[6]
                    if feat_id.startswith('NP_'):
                        np_accession = feat_id
                    elif feat_id.startswith('NM_'):
                        # Map NM_ transcript to NP_ protein via gene name
                        gene_name = ann_fields[3] if len(ann_fields) > 3 else None
                        if gene_name and gene_name in gene_to_np:
                            np_accession = gene_to_np[gene_name]
                        else:
                            np_accession = feat_id  # fallback to NM_

                if not np_accession:
                    continue

                # Extract HGVS.p
                hgvs_p = ""
                if tag == 'ANN=':
                    ann_fields = part.split('|')
                    if len(ann_fields) > 10:
                        hgvs_p = ann_fields[10]

                search_str = hgvs_p if hgvs_p else part

                # Missense: Ala123Ser
                aa_match = re.search(r'([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})', search_str)
                if aa_match:
                    orig_aa = AA_STANDARDIZE.get(aa_match.group(1))
                    position = aa_match.group(2)
                    new_aa = AA_STANDARDIZE.get(aa_match.group(3))
                    if orig_aa and new_aa:
                        mutations.add(f"('{rsid}','{alt}')\t{np_accession}\t{position}\t{orig_aa}\t{new_aa}\n")
                    continue

                # Frameshift: Gly123ArgfsTer34
                fs_match = re.search(r'([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})fs(?:Ter(\d+))?', part)
                if fs_match:
                    orig_aa = AA_STANDARDIZE.get(fs_match.group(1))
                    position = fs_match.group(2)
                    new_aa = AA_STANDARDIZE.get(fs_match.group(3))
                    ter = fs_match.group(4) or ""
                    if orig_aa and new_aa:
                        mutations.add(f"('{rsid}','{alt}')\t{np_accession}\t{position}\t{orig_aa}\t{new_aa}FSTER{ter}\n")
                    continue

                # Simple frameshift: Gly123fs
                sfs_match = re.search(r'([A-Z][a-z]{2})(\d+)fs', part)
                if sfs_match:
                    orig_aa = AA_STANDARDIZE.get(sfs_match.group(1))
                    position = sfs_match.group(2)
                    if orig_aa:
                        mutations.add(f"('{rsid}','{alt}')\t{np_accession}\t{position}\t{orig_aa}\t{orig_aa}FSTER\n")
                    continue

                # Stop gained: Trp123Ter
                ter_match = re.search(r'([A-Z][a-z]{2})(\d+)(?:Ter|\*)', part)
                if ter_match:
                    orig_aa = AA_STANDARDIZE.get(ter_match.group(1))
                    position = ter_match.group(2)
                    if orig_aa:
                        mutations.add(f"('{rsid}','{alt}')\t{np_accession}\t{position}\t{orig_aa}\t{orig_aa}TER\n")
                    continue

                # Stop loss extension: Ter123Trpext*
                ext_match = re.search(r'(?:Ter|\*)(\d+)([A-Z][a-z]{2})ext', part)
                if ext_match:
                    position = ext_match.group(1)
                    new_aa = AA_STANDARDIZE.get(ext_match.group(2))
                    if new_aa:
                        mutations.add(f"('{rsid}','{alt}')\t{np_accession}\t{position}\tTER\t{new_aa}\n")

    return mutations


def is_frameshift_or_nonsense(mutation_key):
    """Check if mutation is frameshift/nonsense (for EnterpriseX)."""
    key_upper = mutation_key.upper()
    return any(tag in key_upper for tag in ['FS', '*', 'DEL', 'TER', 'FSTER'])


def run_entprise(mutations_list):
    """Run Enterprise scoring on missense mutations."""
    rsid_file = os.path.join(ENTPRISE_DIR, 'rsid.lst')
    rsid_out = os.path.join(ENTPRISE_DIR, 'rsid.lst_pred.out')
    script = os.path.join(ENTPRISE_DIR, 'scan_genfea3_pred.job')

    with open(rsid_file, 'w') as f:
        for item in mutations_list:
            f.write(item.rstrip('\n') + '\n')

    os.chmod(script, 0o755)
    result = subprocess.run([script, rsid_file], capture_output=True, text=True, cwd=ENTPRISE_DIR)

    key_to_score = {}
    if os.path.exists(rsid_out):
        with open(rsid_out, 'r') as f:
            for line in f:
                parts = line.strip().split('\t')
                parts = [p.strip() for p in parts]
                if parts[0]:
                    key = f"{parts[0]}\t{parts[1]}\t{parts[2]}\t{parts[3]}"
                    if len(parts) > 4:
                        key_to_score[key] = parts[4]

    scored = []
    for entry in mutations_list:
        entry_stripped = entry.strip('\n')
        if entry_stripped in key_to_score:
            scored.append(f"{entry_stripped}\t{key_to_score[entry_stripped]}")
    return scored


def run_entprisex(mutations_list):
    """Run EnterpriseX scoring on frameshift/nonsense mutations."""
    rsid_file = os.path.join(ENTPRISEX_DIR, 'rsid.lst')
    rsid_out = os.path.join(ENTPRISEX_DIR, 'rsid.lst_pred.out')
    script = os.path.join(ENTPRISEX_DIR, 'scan_pred.job')

    with open(rsid_file, 'w') as f:
        for item in mutations_list:
            f.write(item.rstrip('\n') + '\n')

    os.chmod(script, 0o755)
    subprocess.run([script, rsid_file], capture_output=True, text=True, cwd=ENTPRISEX_DIR)

    results = []
    if os.path.exists(rsid_out):
        with open(rsid_out, 'r') as f:
            results = [line.strip() for line in f if line.strip()]
    return results


def score_mutations(mutations_set):
    """Split mutations into Enterprise vs EnterpriseX and score them."""
    mutations_list = list(mutations_set)
    if not mutations_list:
        print("No protein mutations found to score.")
        return []

    print(f"Found {len(mutations_list)} protein mutations.")

    # Load valid proteins from Enterprise database
    valid_proteins = set()
    # Primary: list_ref_gene.lst has NP_ accessions in column 2 (N00001 NP_xxx.x 309 GENE)
    ref_gene_lst = os.path.join(ENTPRISE_DIR, 'list_ref_gene.lst')
    if os.path.exists(ref_gene_lst):
        with open(ref_gene_lst, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1].startswith(('NP_', 'NM_')):
                    valid_proteins.add(parts[1])
    # Fallback: result_genekb (3+ columns, accession in col 3)
    if not valid_proteins:
        ent_db = os.path.join(ENTPRISE_DIR, 'result_genekb')
        if os.path.exists(ent_db):
            with open(ent_db, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        valid_proteins.add(parts[2])
    print(f"Loaded {len(valid_proteins)} valid proteins from Enterprise database.")

    # Filter and classify mutations
    ent_inputs = []
    entx_inputs = []
    key_to_template = {}
    entx_key_to_template = {}

    for mutation in mutations_list:
        parts = mutation.strip().split('\t')
        if len(parts) < 5:
            continue
        if parts[1] not in valid_proteins:
            continue
        if '?' in mutation:
            continue

        key = f"{parts[1]}\t{parts[2]}\t{parts[3]}\t{parts[4]}"
        template = f"{parts[0]}\t{parts[1]}\t{parts[2]}\t{parts[3]}\t{parts[4]}\tREPLACE\n"
        key_to_template[key] = template
        entx_key_to_template[f"{parts[1]} {parts[2]}"] = template

        if is_frameshift_or_nonsense(key):
            entx_inputs.append(key)
        else:
            ent_inputs.append(key)

    print(f"Enterprise (missense): {len(ent_inputs)} mutations")
    print(f"EnterpriseX (fs/nonsense): {len(entx_inputs)} mutations")

    results = []

    # Run Enterprise
    if ent_inputs:
        ent_scored = run_entprise(ent_inputs)
        for entry in ent_scored:
            if not entry:
                continue
            parts = entry.strip().split('\t')
            key = f"{parts[0]}\t{parts[1]}\t{parts[2]}\t{parts[3]}"
            if key in key_to_template:
                line = key_to_template[key].replace('\n', '').replace('REPLACE', parts[4])
                results.append(line + '\n')

    # Run EnterpriseX
    if entx_inputs:
        entx_scored = run_entprisex(entx_inputs)
        for entry in entx_scored:
            if not entry:
                continue
            parts = entry.strip().split(' ')
            if len(parts) >= 3:
                key = f"{parts[0]} {parts[1]}"
                score = parts[2]
                if key in entx_key_to_template:
                    line = entx_key_to_template[key].replace('\n', '').replace('REPLACE', score)
                    results.append(line + '\n')

    print(f"Scored {len(results)} mutations total.")
    return results


def main(input_vcf, output_file):
    print(f"Processing VCF for Enterprise scoring: {input_vcf}")

    mutations = extract_mutations(input_vcf)
    scored = score_mutations(mutations)

    with open(output_file, 'w') as f:
        for line in scored:
            f.write(line)

    print(f"Results written to {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python run_enterprise.py <input_vcf> <output_file>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
