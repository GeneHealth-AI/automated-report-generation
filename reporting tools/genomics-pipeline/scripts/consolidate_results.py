"""
Consolidate VCF annotations, rsIDs, and Enterprise disease scores into a final report.
"""
import sys
import re
import argparse
import os


def parse_args():
    parser = argparse.ArgumentParser(description='Consolidate VCF + Enterprise scores')
    parser.add_argument('--vcf', required=True, help='Annotated VCF file')
    parser.add_argument('--scores', required=True, help='Enterprise scores output file')
    parser.add_argument('--mapping', required=False, help='Gene to NP mapping file (list_ref_gene.lst)')
    parser.add_argument('--output', required=True, help='Final consolidated output file')
    return parser.parse_args()


def load_mapping(mapping_path):
    """Load Gene Symbol -> NP_ ID mapping."""
    mapping = {}
    if not mapping_path or not os.path.exists(mapping_path):
        return mapping
    with open(mapping_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 4:
                mapping[parts[3]] = parts[1]  # gene_symbol -> NP_ID
    return mapping


def load_scores(scores_path):
    """Load Enterprise scores keyed by (rsID, alt) tuple string."""
    scores = {}
    if not scores_path or not os.path.exists(scores_path):
        return scores
    with open(scores_path, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            match = re.search(r"\('.*?','.*?'\)", line)
            if match:
                scores[match.group(0)] = line.strip()
    return scores


def parse_aa_change(hgvs_p):
    """Parse HGVS.p like p.Ala234Ser -> (pos, REF_AA, ALT_AA)."""
    if not hgvs_p or not hgvs_p.startswith("p."):
        return None
    change = hgvs_p[2:]
    aa3 = ['Ala', 'Arg', 'Asn', 'Asp', 'Cys', 'Gln', 'Glu', 'Gly', 'His', 'Ile',
           'Leu', 'Lys', 'Met', 'Phe', 'Pro', 'Ser', 'Thr', 'Trp', 'Tyr', 'Val', 'Ter']
    try:
        first_aa = change[:3]
        if first_aa not in aa3:
            return None
        remaining = change[3:]
        digits = "".join(c for c in remaining if c.isdigit())
        if not digits:
            return None
        second_aa = remaining[len(digits):][:3]
        if second_aa in aa3:
            return (digits, first_aa.upper(), second_aa.upper())
    except Exception:
        pass
    return None


def main():
    args = parse_args()
    gene_map = load_mapping(args.mapping)
    ent_scores = load_scores(args.scores)

    print(f"Loaded {len(gene_map)} gene mappings.")
    print(f"Loaded {len(ent_scores)} enterprise scores.")

    with open(args.vcf, 'r') as f_in, open(args.output, 'w') as f_out:
        # Write header
        f_out.write("# rsID\tAllele\tProtein_ID\tPosition\tRef_AA\tAlt_AA\tDisease_Score\tGene\n")

        for line in f_in:
            if line.startswith('#'):
                continue
            parts = line.strip().split('\t')
            if len(parts) < 8:
                continue

            chrom, pos_dna, rsid, ref, alt, _, _, info = parts[:8]
            display_id = rsid if rsid != '.' else f"{chrom}:{pos_dna}"

            ann_field = None
            for item in info.split(';'):
                if item.startswith('ANN='):
                    ann_field = item[4:]
                    break
            if not ann_field:
                continue

            for ann in ann_field.split(','):
                fields = ann.split('|')
                if len(fields) < 11:
                    continue

                gene_symbol = fields[3]
                transcript_id = fields[6]
                hgvs_p = fields[10]
                if not hgvs_p:
                    continue

                parsed = parse_aa_change(hgvs_p)
                if parsed:
                    p_pos, p_ref, p_alt = parsed
                    variant_key = f"('{display_id}','{fields[0]}')"
                    protein_id = gene_map.get(gene_symbol, transcript_id)

                    score_line = ent_scores.get(variant_key)
                    if score_line:
                        f_out.write(f"{score_line}\n")
                    else:
                        f_out.write(f"{variant_key}\t{protein_id}\t{p_pos}\t{p_ref}\t{p_alt}\t.\t{gene_symbol}\n")


if __name__ == "__main__":
    main()
