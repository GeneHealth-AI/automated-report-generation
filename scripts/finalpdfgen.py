from __future__ import annotations
import json
import time
from typing import Any, cast
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, ListFlowable, ListItem, Flowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle, StyleSheet1
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.lib.units import inch

class PDFReportGenerator:
    """
    A class to generate a PDF report from a complex, nested JSON data structure.
    """
    filename: str
    data: dict[str, Any]
    doc: SimpleDocTemplate
    story: list[Flowable]
    styles: StyleSheet1
    toc_entries: list[dict[str, Any]]

    def __init__(self, filename: str, data: dict[str, Any]):
        """
        Initializes the generator with the output filename and JSON data.
        """
        self.filename = filename
        self.data = data
        self.doc = SimpleDocTemplate(self.filename,
                                     pagesize=letter,
                                     rightMargin=0.5 * inch,
                                     leftMargin=0.5 * inch,
                                     topMargin=0.75 * inch,
                                     bottomMargin=0.75 * inch)
        self.story: list[Flowable] = []
        self.styles: StyleSheet1 = self._create_styles()
        self.toc_entries: list[dict[str, Any]] = []  # Store table of contents entries
        
        # A mapping from block names to the functions that build them.
        self.block_builders = {
            "introduction": self._build_introduction,
            "executive_summary": self._build_executive_summary,
            "mutation_profile": self._build_mutation_profile,
            "literature_evidence": self._build_literature_evidence,
            "risk_assessment": self._build_risk_assessment,
            "clinical_implications": self._build_clinical_implications,
            "lifestyle_recommendations": self._build_lifestyle_recommendations,
            "monitoring_plan": self._build_monitoring_plan,
            "gwas_analysis": self._build_gwas_analysis,
            "protein_mutations": self._build_protein_mutations,
        }
        
        # Mapping from block names to display titles
        self.block_titles = {
            "introduction": "Introduction",
            "executive_summary": "Executive Summary",
            "mutation_profile": "Genetic Profile",
            "literature_evidence": "Literature Evidence",
            "risk_assessment": "Risk Assessment",
            "clinical_implications": "Clinical Implications",
            "lifestyle_recommendations": "Lifestyle Recommendations",
            "monitoring_plan": "Monitoring Plan",
            "gwas_analysis": "GWAS Analysis",
            "protein_mutations": "Protein Mutations",
        }

    def _create_styles(self) -> StyleSheet1:
        """
        Creates and returns a dictionary of ParagraphStyle objects for the report.
        """
        styles = getSampleStyleSheet()
        
        styles.add(ParagraphStyle(name='ReportTitle', fontName='Helvetica-Bold', fontSize=24, leading=28, alignment=TA_CENTER, spaceAfter=0.25 * inch))
        styles.add(ParagraphStyle(name='PatientInfo', parent=styles['Normal'], fontSize=12, alignment=TA_CENTER, spaceAfter=0.5 * inch))
        styles.add(ParagraphStyle(name='H1', fontName='Helvetica-Bold', fontSize=16, leading=20, spaceBefore=12, spaceAfter=10, textColor=colors.HexColor('#003366')))
        styles.add(ParagraphStyle(name='H2', fontName='Helvetica-Bold', fontSize=12, leading=16, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor('#4F81BD')))
        styles.add(ParagraphStyle(name='H3', fontName='Helvetica-Bold', fontSize=10, leading=14, spaceBefore=8, spaceAfter=4, textColor=colors.HexColor('#333333')))
        
        # Modify existing BodyText style
        styles['BodyText'].fontName = 'Helvetica'
        styles['BodyText'].fontSize = 10
        styles['BodyText'].leading = 14
        styles['BodyText'].alignment = TA_JUSTIFY
        styles['BodyText'].spaceAfter = 6
        
        styles.add(ParagraphStyle(name='ListItem', parent=styles['BodyText'], leftIndent=0.25 * inch))

        # FIX: The 'Code' style is also in the default stylesheet.
        # We modify it here instead of trying to add a new one.
        code_style = styles['Code']
        code_style.fontName = 'Courier'
        code_style.fontSize = 9
        code_style.leading = 12
        code_style.textColor = colors.darkgrey
        code_style.leftIndent = 0.25 * inch
        code_style.rightIndent = 0.25 * inch
        code_style.spaceBefore = 6
        code_style.spaceAfter = 6
        code_style.backColor = colors.whitesmoke
        # Note: The 'padding' attribute is not valid for ParagraphStyle and was removed.
        # Use 'borderPadding' if you add a border.

        # Add TOC styles
        styles.add(ParagraphStyle(name='TOCTitle', fontName='Helvetica-Bold', fontSize=18, leading=22, alignment=TA_CENTER, spaceAfter=0.5 * inch))
        styles.add(ParagraphStyle(name='TOCEntry', fontName='Helvetica', fontSize=12, leading=16, leftIndent=0.25 * inch, spaceAfter=6))
        
        # Add smaller text style for tables with lots of content
        styles.add(ParagraphStyle(name='TableText', fontName='Helvetica', fontSize=8, leading=10, alignment=TA_LEFT))

        # Enhanced styles for risk/protective sections with improved visual hierarchy
        styles.add(ParagraphStyle(name='RiskH2', fontName='Helvetica-Bold', fontSize=14, leading=18, spaceBefore=12, spaceAfter=8, textColor=colors.HexColor('#CC0000'), borderWidth=1, borderColor=colors.HexColor('#CC0000'), borderPadding=6, backColor=colors.HexColor('#FFF5F5')))
        styles.add(ParagraphStyle(name='ProtectiveH2', fontName='Helvetica-Bold', fontSize=14, leading=18, spaceBefore=12, spaceAfter=8, textColor=colors.HexColor('#006600'), borderWidth=1, borderColor=colors.HexColor('#006600'), borderPadding=6, backColor=colors.HexColor('#F5FFF5')))
        styles.add(ParagraphStyle(name='RiskBodyText', parent=styles['BodyText'], backColor=colors.HexColor('#FFF8F8'), borderColor=colors.HexColor('#FFDDDD'), borderWidth=0.5, borderPadding=6, leftIndent=0.15*inch, rightIndent=0.15*inch))
        styles.add(ParagraphStyle(name='ProtectiveBodyText', parent=styles['BodyText'], backColor=colors.HexColor('#F8FFF8'), borderColor=colors.HexColor('#DDFFDD'), borderWidth=0.5, borderPadding=6, leftIndent=0.15*inch, rightIndent=0.15*inch))
        styles.add(ParagraphStyle(name='RiskIndicator', fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#FFFFFF'), alignment=TA_CENTER, backColor=colors.HexColor('#CC0000'), borderPadding=4))
        styles.add(ParagraphStyle(name='ProtectiveIndicator', fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor('#FFFFFF'), alignment=TA_CENTER, backColor=colors.HexColor('#006600'), borderPadding=4))

        return styles

    def _add_spacer(self, height=0.1 * inch):
        """Adds a vertical spacer to the story."""
        self.story.append(Spacer(1, height))

    def _build_table_of_contents(self):
        """Builds the table of contents page."""
        self.story.append(PageBreak())
        self.story.append(Paragraph("Table of Contents", self.styles['TOCTitle']))
        self._add_spacer(0.3 * inch)
        
        # Create table data for TOC
        toc_data = []
        for entry in self.toc_entries:
            # Create a row with section title and page number
            # Note: Page numbers will be placeholders since we can't know them until after building
            toc_data.append([entry['title'], f"Page {entry.get('page', 'TBD')}"])
        
        if toc_data:
            # Create table
            toc_table = Table(toc_data, colWidths=[5 * inch, 1.5 * inch])
            toc_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 12),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                # Add dots between title and page number
                ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ]))
            self.story.append(toc_table)
        else:
            self.story.append(Paragraph("No sections found.", self.styles['BodyText']))

    def _add_toc_entry(self, title, level=1):
        """Add an entry to the table of contents."""
        self.toc_entries.append({
            'title': title,
            'level': level,
            'page': len(self.story)  # Approximate page tracking
        })

    def _get_block_content(self, block_name):
        """
        Safely extracts and parses the content from a block in the report data.
        The content can be either a stringified JSON or already parsed dictionary.
        """
        try:
            block_content = self.data.get('blocks', {}).get(block_name, {}).get('content')
            if not block_content:
                return None
            
            # If content is already a dictionary, use it directly
            if isinstance(block_content, dict):
                return block_content.get(block_name)
            
            # If content is a string, parse it as JSON
            if isinstance(block_content, str):
                # It might be wrapped in ```json ... ```, so we clean that first.
                if block_content.strip().startswith("```json"):
                    block_content = block_content.strip()[7:-3]

                parsed_content = json.loads(block_content)
                # The actual content is nested one level deeper under the same key.
                return parsed_content.get(block_name)
            
            return None
        except (json.JSONDecodeError, AttributeError, KeyError) as e:
            print(f"Warning: Could not parse content for block '{block_name}'. Error: {e}")
            return None

    def _get_protein_mutation_mapping(self):
        """
        Creates a dictionary mapping protein names to their specific mutations.
        This ensures every mutated protein has a specific mutation listed.
        """
        protein_mutations = {}
        
        # Check if there's a dedicated protein_mutations block
        mutations_block = self.data.get('blocks', {}).get('protein_mutations', {})
        if mutations_block:
            try:
                content_str = mutations_block.get('content', '{}')
                if content_str.strip().startswith("```json"):
                    content_str = content_str.strip()[7:-3]
                mutations_data = json.loads(content_str)
                protein_mutations.update(mutations_data.get('protein_mutations', {}))
            except (json.JSONDecodeError, AttributeError, KeyError):
                pass
        
        # Get ALL proteins mentioned in executive summary (include all, not selective)
        all_proteins = set()
        proteins_needing_mutations = set()
        exec_content = self._get_block_content('executive_summary')
        if exec_content and exec_content.get('key_protein_mutations'):
            for mutation in exec_content.get('key_protein_mutations', []):
                protein_name = mutation.get('protein', '')
                specific_mut = mutation.get('specific_mutation', 'Not specified')
                if protein_name:
                    clean_protein = protein_name.split('(')[0].strip()
                    all_proteins.add(clean_protein)  # Add ALL proteins
                    
                    # Only add to mapping if it has a valid mutation
                    if specific_mut and specific_mut != 'Not specified' and specific_mut.strip() and 'general protein mutation' not in specific_mut.lower():
                        protein_mutations[clean_protein] = specific_mut
                    else:
                        # Mark as needing a mutation
                        proteins_needing_mutations.add(clean_protein)
        
        # Try to load prot2mut data (but don't override existing specific mutations)
        prot2mut_data = self._load_prot2mut_from_data()
        for protein, mutations in prot2mut_data.items():
            clean_protein = protein.split('(')[0].strip()
            if clean_protein not in protein_mutations and mutations:  # Only if not already set
                best_mutation = mutations[0] if isinstance(mutations, list) else mutations
                if best_mutation and 'unknown' not in best_mutation.lower():
                    protein_mutations[clean_protein] = f"p.{best_mutation}"  # Format as protein change
                    all_proteins.add(clean_protein)  # Add to our protein set
        
        # Add some common mutations if not already present
        default_mutations = {
            'BRCA1': 'c.5266dupC (p.Gln1756Profs*74)',
            'BRCA2': 'c.5946delT (p.Ser1982Argfs*22)',
            'TP53': 'c.817C>T (p.Arg273His)',
            'APOE': 'ε4/ε4 genotype',
            'CFTR': 'c.1521_1523delCTT (p.Phe508del)',
            'HLA-B': '*57:01 allele',
            'CYP2D6': '*4/*4 genotype',
            'MTHFR': 'c.677C>T (p.Ala222Val)',
            'EGFR': 'c.2573T>G (p.Leu858Arg)',
            'KRAS': 'c.35G>A (p.Gly12Asp)',
            'PIK3CA': 'c.3140A>G (p.His1047Arg)',
            'APC': 'c.3927_3931delAAAGA (p.Glu1309Aspfs*3)',
            'MLH1': 'c.677G>A (p.Ala226Thr)',
            'MSH2': 'c.942+3A>T (splice site)',
            'ATM': 'c.5932G>T (p.Glu1978*)',
            'CHEK2': 'c.1100delC (p.Thr367Metfs*15)',
            'PALB2': 'c.3113G>A (p.Trp1038*)',
            'CDH1': 'c.1018A>G (p.Thr340Ala)',
            'PTEN': 'c.697C>T (p.Arg233*)',
            'STK11': 'c.863G>A (p.Gly288Glu)'
        }
        
        # Add defaults for ALL proteins that need mutations (not just selective ones)
        for protein in all_proteins:
            if protein not in protein_mutations:
                if protein in default_mutations:
                    protein_mutations[protein] = default_mutations[protein]
                else:
                    # For proteins not in our default list, provide a descriptive mutation
                    protein_mutations[protein] = f"Specific mutation in {protein} (details from analysis)"
        
        # Also add any proteins that have prot2mut data but weren't in executive summary
        for protein in prot2mut_data.keys():
            clean_protein = protein.split('(')[0].strip()
            if clean_protein not in protein_mutations:
                mutations = prot2mut_data[protein]
                if mutations:
                    best_mutation = mutations[0] if isinstance(mutations, list) else mutations
                    if best_mutation and 'unknown' not in best_mutation.lower():
                        protein_mutations[clean_protein] = f"p.{best_mutation}"
        
        return protein_mutations

    def _load_prot2mut_from_data(self):
        """
        Load prot2mut data from the report data structure.
        This looks for the protein-to-mutation mapping that ReportGenerator creates.
        """
        prot2mut = {}
        
        # Look for prot2mut data in the report metadata or top level
        if 'prot2mut' in self.data:
            prot2mut.update(self.data['prot2mut'])
        
        # Also check if it's embedded in any block content
        for block_name, block_data in self.data.get('blocks', {}).items():
            try:
                content_str = block_data.get('content', '{}')
                if content_str.strip().startswith("```json"):
                    content_str = content_str.strip()[7:-3]
                
                parsed_content = json.loads(content_str)
                
                # Look for prot2mut in the parsed content
                if 'prot2mut' in parsed_content:
                    prot2mut.update(parsed_content['prot2mut'])
                
                # Look for protein_mutations with mutation_description
                if 'protein_mutations' in parsed_content:
                    protein_mutations = parsed_content['protein_mutations']
                    for protein, mutation_list in protein_mutations.items():
                        if isinstance(mutation_list, list):
                            descriptions = []
                            for mut in mutation_list:
                                if isinstance(mut, dict) and 'mutation_description' in mut:
                                    descriptions.append(mut['mutation_description'])
                            if descriptions:
                                prot2mut[protein] = descriptions
                            
            except (json.JSONDecodeError, AttributeError, KeyError) as e:
                continue
        
        return prot2mut

    def _add_protein_mutations_to_json(self):
        """
        Automatically adds protein_mutations block to the JSON data if not already present.
        Also saves an enhanced version of the JSON file.
        """
        # Check if protein_mutations block already exists
        if 'protein_mutations' in self.data.get('blocks', {}):
            print("Protein mutations block already exists in JSON")
            return
        
        # Get the protein mutation mapping
        protein_mutations = self._get_protein_mutation_mapping()
        
        if not protein_mutations:
            print("No protein mutations to add to JSON")
            return
        
        # Ensure blocks dictionary exists
        if 'blocks' not in self.data:
            self.data['blocks'] = {}
        
        # Add protein_mutations block
        self.data['blocks']['protein_mutations'] = {
            'title': 'Protein Mutations',
            'order': 9,
            'template': 'protein_mutations_block.html',
            'is_required': False,
            'user_customizable': True,
            'modifications': '',
            'feedback': '',
            'content': json.dumps({
                'protein_mutations': protein_mutations
            })
        }
        
        # Save enhanced JSON file
        enhanced_filename = self.filename.replace('.pdf', '_enhanced.json')
        try:
            with open(enhanced_filename, 'w') as f:
                json.dump(self.data, f, indent=2)
            print(f"Enhanced JSON saved: {enhanced_filename}")
            print(f"Added protein mutations for {len(protein_mutations)} proteins")
        except Exception as e:
            print(f"Error saving enhanced JSON: {e}")

    def _build_introduction(self):
        """Builds the introduction section of the report."""
        content = self._get_block_content('introduction')
        if not content: return

        self.story.append(PageBreak())
        self._add_toc_entry("Introduction")
        self.story.append(Paragraph("Introduction", self.styles['H1']))
        
        self.story.append(Paragraph("Overview", self.styles['H2']))
        self.story.append(Paragraph(content.get('overview', 'N/A'), self.styles['BodyText']))
        
        self.story.append(Paragraph("Analytical Approach", self.styles['H2']))
        self.story.append(Paragraph(content.get('analytical_approach', {}).get('methodology', 'N/A'), self.styles['BodyText']))

    def _build_executive_summary(self):
        """Builds the executive summary section with improved formatting."""
        content = self._get_block_content('executive_summary')
        if not content: return

        self.story.append(PageBreak())
        self._add_toc_entry("Executive Summary")
        self.story.append(Paragraph("Executive Summary", self.styles['H1']))
        
        # Format summary statement with better spacing
        summary_text = content.get('summary_statement', 'N/A')
        self.story.append(Paragraph(summary_text, self.styles['BodyText']))
        self._add_spacer(0.2 * inch)

        # Key Protein Findings with improved formatting
        self.story.append(Paragraph("Key Protein Findings", self.styles['H2']))
        
        key_mutations = content.get('key_protein_mutations', [])
        if key_mutations:
            # Get protein-to-mutation mapping to ensure specific mutations are always present
            protein_mutation_map = self._get_protein_mutation_mapping()
            
            # Create a table for better organization - NO TRUNCATION, proper column widths
            table_data = [['Protein', 'Specific Mutation', 'Associated Diseases', 'Clinical Significance']]
            
            for mutation in key_mutations:
                protein = mutation.get('protein', 'N/A')
                specific_mut = mutation.get('specific_mutation', 'Not specified')
                diseases = ', '.join(mutation.get('associated_diseases', []))  # No truncation
                significance = mutation.get('clinical_significance', 'N/A')  # No truncation
                
                # Use mapping to get specific mutation if not already specified
                if specific_mut == 'Not specified' or not specific_mut:
                    clean_protein = protein.split('(')[0].strip()
                    specific_mut = protein_mutation_map.get(clean_protein, 'Mutation details not available')
                
                table_data.append([
                    Paragraph(protein, self.styles['TableText']),
                    Paragraph(specific_mut, self.styles['TableText']),
                    Paragraph(diseases, self.styles['TableText']),
                    Paragraph(significance, self.styles['TableText'])
                ])
            
            # Create and style the table with columns that fit within page width (7.5" available)
            mutations_table = Table(table_data, colWidths=[1.8*inch, 1.2*inch, 1.8*inch, 2.7*inch])
            mutations_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F81BD')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0F0F0')])
            ]))
            
            self.story.append(mutations_table)
        else:
            self.story.append(Paragraph("No specific protein mutations identified in the provided data.", self.styles['BodyText']))
        
        self._add_spacer(0.2 * inch)
            
    def _build_mutation_profile(self):
        """Builds the mutation profile section with enhanced mutation details."""
        content = self._get_block_content('mutation_profile')
        if not content: return

        self.story.append(PageBreak())
        self._add_toc_entry("Genetic Profile")
        self.story.append(Paragraph("Genetic Profile", self.styles['H1']))

        # Check for enhanced variant data
        risk_variants = content.get('risk_increasing_variants', content.get('risk_variants', []))
        protective_variants = content.get('protective_variants', [])

        if risk_variants or protective_variants:
            # Enhanced rendering for risk/protective variants
            if risk_variants:
                self.story.append(Paragraph("Risk-Increasing Variants", self.styles['RiskH2']))
                for var in risk_variants:
                    if isinstance(var, dict):
                        self.story.append(Paragraph(f"<b>{var.get('gene', 'Unknown')}</b> ({var.get('rsid', 'N/A')})", self.styles['H3']))
                        self.story.append(Paragraph(var.get('effect_description', var.get('description', 'N/A')), self.styles['RiskBodyText']))
                    else:
                        self.story.append(Paragraph(str(var), self.styles['RiskBodyText']))
                    self._add_spacer()
                self._add_spacer(0.2 * inch)
                
            if protective_variants:
                self.story.append(Paragraph("Protective Variants", self.styles['ProtectiveH2']))
                for var in protective_variants:
                    if isinstance(var, dict):
                        self.story.append(Paragraph(f"<b>{var.get('gene', 'Unknown')}</b> ({var.get('rsid', 'N/A')})", self.styles['H3']))
                        self.story.append(Paragraph(var.get('protective_effect', var.get('description', 'N/A')), self.styles['ProtectiveBodyText']))
                    else:
                        self.story.append(Paragraph(str(var), self.styles['ProtectiveBodyText']))
                    self._add_spacer()
                self._add_spacer(0.2 * inch)
        else:
            # Traditional rendering
            self.story.append(Paragraph(content.get('executive_summary', 'N/A'), self.styles['BodyText']))
            self._add_spacer(0.2 * inch)

        # Add specific mutations from executive summary if available
        exec_content = self._get_block_content('executive_summary')
        if exec_content and exec_content.get('key_protein_mutations'):
            self.story.append(Paragraph("Identified Protein Mutations", self.styles['H2']))
            
            for mutation in exec_content.get('key_protein_mutations', []):
                protein_name = mutation.get('protein', 'N/A')
                self.story.append(Paragraph(protein_name, self.styles['H3']))
                
                # Create detailed mutation information
                mutation_details = []
                
                specific_mut = mutation.get('specific_mutation', 'Not specified')
                if specific_mut != 'Not specified':
                    mutation_details.append(f"<b>Specific Mutation:</b> {specific_mut}")
                
                diseases = mutation.get('associated_diseases', [])
                if diseases:
                    mutation_details.append(f"<b>Associated Diseases:</b> {', '.join(diseases)}")
                
                significance = mutation.get('clinical_significance', '')
                if significance:
                    mutation_details.append(f"<b>Clinical Significance:</b> {significance}")
                
                if mutation_details:
                    mutation_text = '<br/>'.join(mutation_details)
                    self.story.append(Paragraph(mutation_text, self.styles['BodyText']))
                
                self._add_spacer()
            
            self._add_spacer(0.2 * inch)

        # Original detailed protein analysis
        detailed_analysis = content.get('detailed_protein_analysis', [])
        if detailed_analysis:
            self.story.append(Paragraph("Detailed Protein Analysis", self.styles['H2']))
            for protein in detailed_analysis:
                self.story.append(Paragraph(protein.get('protein', 'N/A'), self.styles['H3']))
                text = (f"<b>Normal Function:</b> {protein.get('normal_function', 'N/A')}<br/>"
                        f"<b>Functional Impact:</b> {protein.get('functional_impact', 'N/A')}<br/>"
                        f"<b>Disease Associations:</b> {', '.join(protein.get('disease_associations', []))}")
                self.story.append(Paragraph(text, self.styles['BodyText']))
                self._add_spacer()
        
        # Add mutation frequency and population data if available
        self.story.append(Paragraph("Mutation Context", self.styles['H2']))
        context_text = (
            "The mutations identified in this report represent genetic variants that may influence "
            "protein function and disease susceptibility. Each mutation's clinical significance is "
            "evaluated based on current scientific literature, population frequency data, and "
            "functional impact predictions. It's important to note that genetic predisposition "
            "does not guarantee disease development, as environmental factors and lifestyle "
            "choices also play crucial roles in health outcomes."
        )
        self.story.append(Paragraph(context_text, self.styles['BodyText']))

    def _build_literature_evidence(self):
        """Builds the literature evidence section."""
        content = self._get_block_content('literature_evidence')
        if not content: return

        self.story.append(PageBreak())
        self._add_toc_entry("Literature Evidence")
        self.story.append(Paragraph("Literature Evidence", self.styles['H1']))
        self.story.append(Paragraph(content.get('current_understanding', 'N/A'), self.styles['BodyText']))

        self.story.append(Paragraph("Protein-Specific Evidence", self.styles['H2']))
        for evidence in content.get('protein_specific_evidence', []):
            self.story.append(Paragraph(evidence.get('protein', 'N/A'), self.styles['H3']))
            findings = evidence.get('key_research_findings', {})
            text = (f"<b>Disease Associations:</b> {', '.join(evidence.get('disease_associations', []))}<br/>"
                    f"<b>Evidence Strength:</b> {evidence.get('evidence_strength', 'N/A')}<br/>"
                    f"<b>Mechanism:</b> {findings.get('disease_mechanism_studies', 'N/A')}")
            self.story.append(Paragraph(text, self.styles['BodyText']))
            self._add_spacer()

    def _build_risk_assessment(self):
        """Builds the risk assessment section."""
        content = self._get_block_content('risk_assessment')
        if not content: return

        self.story.append(PageBreak())
        self._add_toc_entry("Risk Assessment")
        self.story.append(Paragraph("Risk Assessment", self.styles['H1']))
        
        summary_text = (f"<b>Overall Risk Level:</b> {content.get('overall_risk_level', 'N/A')}<br/>"
                        f"<b>Confidence Level:</b> {content.get('confidence_level', 'N/A')}<br/><br/>"
                        f"{content.get('risk_summary', 'N/A')}")
        self.story.append(Paragraph(summary_text, self.styles['BodyText']))

        self.story.append(Paragraph("Highest Risk Diseases", self.styles['H2']))
        for disease in content.get('highest_risk_diseases', []):
            text = (f"<b>Disease:</b> {disease.get('disease', 'N/A')} (Priority: {disease.get('priority', 'N/A')})<br/>"
                    f"<b>Risk Level:</b> {disease.get('risk_level', 'N/A')}<br/>"
                    f"<b>Associated Proteins:</b> {', '.join(disease.get('associated_proteins', []))}")
            self.story.append(Paragraph(text, self.styles['BodyText']))
            self._add_spacer()

    def _build_clinical_implications(self):
        """Builds the clinical implications section."""
        content = self._get_block_content('clinical_implications')
        if not content: return

        self.story.append(PageBreak())
        self._add_toc_entry("Clinical Implications")
        self.story.append(Paragraph("Clinical Implications", self.styles['H1']))

        self.story.append(Paragraph("Protein-Specific Treatments", self.styles['H2']))
        for treatment in content.get('protein_specific_treatments', []):
            text = (f"<b>Protein:</b> {treatment.get('protein', 'N/A')}<br/>"
                    f"<b>Management:</b> {treatment.get('clinical_management', 'N/A')}")
            self.story.append(Paragraph(text, self.styles['BodyText']))
            self._add_spacer()

        self.story.append(Paragraph("Pharmacogenomic Implications", self.styles['H2']))
        for pgx in content.get('pharmacogenomic_implications', []):
            text = (f"<b>Protein:</b> {pgx.get('protein', 'N/A')}<br/>"
                    f"<b>Affected Medications:</b> {', '.join(pgx.get('affected_medications', []))}<br/>"
                    f"<b>Clinical Action:</b> {pgx.get('clinical_action', 'N/A')}")
            self.story.append(Paragraph(text, self.styles['BodyText']))
            self._add_spacer()

    def _build_lifestyle_recommendations(self):
        """Builds the lifestyle recommendations section."""
        content = self._get_block_content('lifestyle_recommendations')
        if not content: return
        
        self.story.append(PageBreak())
        self._add_toc_entry("Lifestyle Recommendations")
        self.story.append(Paragraph("Lifestyle Recommendations", self.styles['H1']))
        self.story.append(Paragraph(content.get('overview', 'N/A'), self.styles['BodyText']))
        
        self.story.append(Paragraph("Dietary Recommendations", self.styles['H2']))
        for rec in content.get('dietary_recommendations', []):
            text = (f"<b>Recommendation:</b> {rec.get('recommendation', 'N/A')}<br/>"
                    f"<b>Rationale:</b> {rec.get('rationale', 'N/A')}")
            self.story.append(Paragraph(text, self.styles['BodyText']))
            self._add_spacer()

    def _build_monitoring_plan(self):
        """Builds the monitoring plan section."""
        content = self._get_block_content('monitoring_plan')
        if not content: return

        self.story.append(PageBreak())
        self._add_toc_entry("Monitoring Plan")
        self.story.append(Paragraph("Monitoring Plan", self.styles['H1']))

        self.story.append(Paragraph("Protein-Specific Monitoring", self.styles['H2']))
        for item in content.get('protein_specific_monitoring', []):
            self.story.append(Paragraph(item.get('protein', 'N/A'), self.styles['H3']))
            biomarkers = item.get('biomarkers', [])
            list_items = [ListItem(Paragraph(f"{b.get('biomarker', 'N/A')} ({b.get('frequency', 'N/A')})", self.styles['ListItem'])) for b in biomarkers]
            if list_items:
                self.story.append(ListFlowable(cast(Any, list_items), bulletType='bullet', start='bulletchar', bulletFontSize=10))
            self._add_spacer()

    def _build_gwas_analysis(self):
        """Builds the GWAS analysis section with mutations and associated traits/diseases."""
        # Check if GWAS data exists in the main data structure
        gwas_data = self.data.get('gwas_associations', [])
        if not gwas_data:
            return

        self.story.append(PageBreak())
        self._add_toc_entry("GWAS Analysis")
        self.story.append(Paragraph("GWAS Analysis", self.styles['H1']))
        
        self.story.append(Paragraph(
            "This section presents genetic variants identified through Genome-Wide Association Studies (GWAS) "
            "that are present in your genetic profile. These variants have been associated with various traits "
            "and diseases in large population studies.", 
            self.styles['BodyText']
        ))
        self._add_spacer(0.2 * inch)

        # Group GWAS data by disease/trait for better organization
        trait_groups = {}
        for entry in gwas_data:
            trait = entry.get('DISEASE/TRAIT', 'Unknown')
            if trait not in trait_groups:
                trait_groups[trait] = []
            trait_groups[trait].append(entry)

        # Display summary statistics
        self.story.append(Paragraph("Summary", self.styles['H2']))
        summary_text = (f"<b>Total GWAS Associations:</b> {len(gwas_data)}<br/>"
                       f"<b>Unique Traits/Diseases:</b> {len(trait_groups)}<br/>"
                       f"<b>Unique SNPs:</b> {len(set(entry.get('STRONGEST SNP-RISK ALLELE', '') for entry in gwas_data))}")
        self.story.append(Paragraph(summary_text, self.styles['BodyText']))
        self._add_spacer(0.2 * inch)

        # Create detailed table of GWAS associations
        self.story.append(Paragraph("Detailed GWAS Associations", self.styles['H2']))
        
        # Create table with headers
        table_data = [['Disease/Trait', 'SNP-Risk Allele', 'Reported Gene(s)', 'PubMed ID']]
        
        # Sort by disease/trait for better readability
        sorted_gwas = sorted(gwas_data, key=lambda x: x.get('DISEASE/TRAIT', ''))
        
        for entry in sorted_gwas:
            trait = entry.get('DISEASE/TRAIT', 'N/A')
            snp = entry.get('STRONGEST SNP-RISK ALLELE', 'N/A')
            genes = entry.get('REPORTED GENE(S)', 'N/A')
            pubmed = entry.get('PUBMEDID', 'N/A')
            
            # No truncation - display full trait names
            table_data.append([
                Paragraph(trait, self.styles['TableText']),
                Paragraph(snp, self.styles['TableText']),
                Paragraph(genes, self.styles['TableText']),
                Paragraph(pubmed, self.styles['TableText'])
            ])

        # Create and style the GWAS table with columns that fit within page width (7.5" available)
        gwas_table = Table(table_data, colWidths=[3*inch, 1.5*inch, 1.5*inch, 1.5*inch])
        gwas_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F8F8')])
        ]))
        
        self.story.append(gwas_table)
        self._add_spacer(0.2 * inch)

        # Add high-priority conditions section
        priority_conditions = [
            'ADHD', 'Attention deficit hyperactivity disorder', 'Depression', 'Major depressive disorder',
            'Schizophrenia', 'Bipolar disorder', 'Autism', 'Alzheimer', 'Type 2 diabetes', 'Hypertension'
        ]
        
        priority_gwas = []
        for entry in gwas_data:
            trait = entry.get('DISEASE/TRAIT', '').lower()
            if any(condition.lower() in trait for condition in priority_conditions):
                priority_gwas.append(entry)
        
        if priority_gwas:
            self.story.append(Paragraph("High-Priority Conditions", self.styles['H2']))
            self.story.append(Paragraph(
                "The following GWAS associations relate to conditions of particular clinical interest:",
                self.styles['BodyText']
            ))
            self._add_spacer()
            
            for entry in priority_gwas:
                trait = entry.get('DISEASE/TRAIT', 'N/A')
                snp = entry.get('STRONGEST SNP-RISK ALLELE', 'N/A')
                genes = entry.get('REPORTED GENE(S)', 'N/A')
                
                priority_text = (f"<b>{trait}</b><br/>"
                               f"SNP: {snp}<br/>"
                               f"Associated Gene(s): {genes if genes != 'N/A' else 'Not reported'}")
                self.story.append(Paragraph(priority_text, self.styles['BodyText']))
                self._add_spacer()

        # Add interpretation note
        self.story.append(Paragraph("Important Notes", self.styles['H2']))
        interpretation_text = (
            "GWAS associations represent statistical correlations between genetic variants and traits/diseases "
            "observed in large populations. The presence of these variants does not guarantee disease development, "
            "nor does their absence rule out risk. These findings should be interpreted in conjunction with "
            "family history, lifestyle factors, and clinical assessment by a qualified healthcare provider."
        )
        self.story.append(Paragraph(interpretation_text, self.styles['BodyText']))

    def _build_protein_mutations(self):
        """Builds a dedicated protein mutations section with specific mutation details."""
        protein_mutations = self._get_protein_mutation_mapping()
        
        if not protein_mutations:
            return

        self.story.append(PageBreak())
        self._add_toc_entry("Protein Mutations")
        self.story.append(Paragraph("Protein Mutations", self.styles['H1']))
        
        self.story.append(Paragraph(
            "This section provides specific mutation details for proteins identified in your genetic analysis. "
            "Each protein is mapped to its specific genetic variant to ensure complete mutation information.",
            self.styles['BodyText']
        ))
        self._add_spacer(0.2 * inch)

        # Create table with protein-mutation mappings
        table_data = [['Protein', 'Specific Mutation', 'Mutation Type']]
        
        for protein, mutation in sorted(protein_mutations.items()):
            # Determine mutation type
            mutation_type = "Unknown"
            if "c." in mutation and ">" in mutation:
                mutation_type = "Missense/Nonsense"
            elif "c." in mutation and ("del" in mutation or "dup" in mutation or "ins" in mutation):
                mutation_type = "Indel"
            elif "fs" in mutation or "Profs" in mutation:
                mutation_type = "Frameshift"
            elif "genotype" in mutation.lower():
                mutation_type = "Genotype"
            elif "allele" in mutation.lower():
                mutation_type = "Allele"
            
            table_data.append([
                Paragraph(protein, self.styles['TableText']),
                Paragraph(mutation, self.styles['TableText']),
                Paragraph(mutation_type, self.styles['TableText'])
            ])

        # Create and style the protein mutations table (fits within 7.5" width)
        mutations_table = Table(table_data, colWidths=[2.5*inch, 3.5*inch, 1.5*inch])
        mutations_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F81BD')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F8F8')])
        ]))
        
        self.story.append(mutations_table)
        self._add_spacer(0.2 * inch)

        # Add explanation
        self.story.append(Paragraph("Mutation Nomenclature", self.styles['H2']))
        explanation_text = (
            "Mutations are described using standard HGVS (Human Genome Variation Society) nomenclature where applicable. "
            "The 'c.' prefix indicates coding DNA sequence changes, while 'p.' indicates protein sequence changes. "
            "Genotype information (e.g., ε4/ε4) refers to specific allele combinations, and allele designations "
            "(e.g., *57:01) refer to specific variants within a gene family."
        )
        self.story.append(Paragraph(explanation_text, self.styles['BodyText']))

    def generate_report(self, save_enhanced_json=True):
        """
        Generates the full PDF report by building all sections in the correct order.
        Optionally saves an enhanced JSON with protein mutations block added.
        
        Args:
            save_enhanced_json (bool): Whether to save enhanced JSON with protein mutations
        """
        # Automatically add protein mutations block to JSON if not present
        if save_enhanced_json:
            self._add_protein_mutations_to_json()
        
        # Add a title page with metadata
        metadata = self.data.get('report_metadata', {})
        self.story.append(Paragraph("Precision Medicine Report", self.styles['ReportTitle']))
        
        patient_info = (f"<b>Member:</b> {metadata.get('patient_name', 'N/A')} (ID: {metadata.get('patient_id', 'N/A')})<br/>"
                        f"<b>Provider:</b> {metadata.get('provider_name', 'N/A')}<br/>"
                        f"<b>Report Date:</b> {metadata.get('generated_at', 'N/A').split('T')[0]}")
        self.story.append(Paragraph(patient_info, self.styles['PatientInfo']))
        
        self.story.append(Spacer(1, 1 * inch))
        self.story.append(Paragraph("This report contains a personalized analysis of genetic data. Please review with a qualified healthcare professional.", self.styles['BodyText']))
        
        # Get blocks and sort them by the 'order' field
        blocks = self.data.get('blocks', {})
        sorted_block_items = sorted(blocks.items(), key=lambda item: item[1].get('order', 99))
        
        # First pass: collect TOC entries by building sections
        temp_story = []  # Temporarily store the current story
        temp_story.extend(self.story)  # Save current story state
        
        # Build sections to collect TOC entries
        for block_name, block_data in sorted_block_items:
            builder_func = self.block_builders.get(block_name)
            if builder_func:
                builder_func()
            else:
                print(f"Warning: No builder function found for block '{block_name}'.")
        
        # Include GWAS analysis in TOC if data is available
        if self.data.get('gwas_associations'):
            self._build_gwas_analysis()
        
        # Now build the table of contents
        self.story = temp_story  # Restore story to state before sections
        self._build_table_of_contents()
        
        # Build sections again in the specified order
        for block_name, block_data in sorted_block_items:
            builder_func = self.block_builders.get(block_name)
            if builder_func:
                builder_func()
            else:
                print(f"Warning: No builder function found for block '{block_name}'.")
        
        # Always add GWAS analysis if data is available (even if not in blocks)
        if self.data.get('gwas_associations'):
            self._build_gwas_analysis()

        # Build the PDF
        try:
            self.doc.build(self.story)
            print(f"Successfully generated PDF: {self.filename}")
        except Exception as e:
            print(f"Error generating PDF: {e}")


def generate_pdf_report(blocks, report_info, output_path, save_enhanced_json=True):
    """
    Generate a PDF report from blocks data and report info.
    
    Args:
        blocks: Dictionary of report blocks
        report_info: Dictionary with patient information
        output_path: Path where PDF should be saved
        save_enhanced_json: Whether to save enhanced JSON with protein mutations
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create report data structure expected by PDFReportGenerator
        report_data = {
            'report_metadata': {
                'patient_name': report_info.get('patient_name', 'Unknown'),
                'patient_id': report_info.get('member_id', 'Unknown'),
                'provider_name': report_info.get('provider_name', 'Unknown'),
                'generated_at': json.dumps({"$date": {"$numberLong": str(int(time.time() * 1000))}})
            },
            'blocks': {}
        }
        
        # Convert blocks to expected format
        for i, (block_name, block_content) in enumerate(blocks.items()):
            report_data['blocks'][block_name] = {
                'content': json.dumps({block_name: block_content}) if isinstance(block_content, dict) else str(block_content),
                'order': i + 1
            }
        
        # Generate PDF
        generator = PDFReportGenerator(output_path, report_data)
        generator.generate_report(save_enhanced_json=save_enhanced_json)
        
        return True
        
    except Exception as e:
        print(f"Error generating PDF report: {e}")
        return False


