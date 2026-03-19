from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

class BlockType(Enum):
    INTRODUCTION = "introduction"
    EXECUTIVE_SUMMARY = "executive_summary"
    MUTATION_PROFILE = "mutation_profile"
    LITERATURE_EVIDENCE = "literature_evidence"
    RISK_ASSESSMENT = "risk_assessment"
    CLINICAL_IMPLICATIONS = "clinical_implications"
    LIFESTYLE_RECOMMENDATIONS = "lifestyle_recommendations"
    MONITORING_PLAN = "monitoring_plan"
    RESEARCH_OPPORTUNITIES = "research_opportunities"
    GWAS_ANALYSIS = "gwas_analysis"
    CONCLUSION = "conclusion"

@dataclass
class ReportBlock:
    block_type: BlockType
    title: str
    content: str | dict[str, Any]
    template: str
    order: int
    is_required: bool = True
    user_customizable: bool = True
    feedback: str = ''
    modifications: str = ''
    
class BlockTemplate:
    """Defines the structure and LLM prompt for each block type"""
    
    INTRODUCTION = {
        "template": "introduction_block.html",
        "llm_prompt": """
        Generate an introduction section for a precision medicine report focused on {category}.
        This report is for a LAYMAN patient, so use clear, non-technical language.
        
        Include:
        - Overview: 2-3 sentence overview explaining the report's purpose in simple terms.
        - Report Scope: Tighten this up to specifically state what genetic factors are analyzed without being overly verbose.
        - Important things to know: These are key considerations/disclaimers. 
          * Make them TERSE (1-2 lines per bullet).
          * Use catchy titles for each bullet.
          * Focus on things like "Genetic testing limitations" and "VUS classification".
        
        Return JSON:
        {{
            "overview": "Explanation for layman",
            "approach": "Simplified explanation of methodology", 
            "scope": "Clear, tight scope statement",
            "important_things_to_know": [
                {{
                    "title": "Title 1",
                    "content": "1-2 lines of layman-friendly explanation"
                }},
                {{
                    "title": "Title 2",
                    "content": "1-2 lines of layman-friendly explanation"
                }}
            ]
        }}
        """,
        "required_data": ["category", "focus_genes"],
        "order": 1
    }
    
    EXECUTIVE_SUMMARY = {
        "template": "executive_summary_block.html",
        "llm_prompt": """
        Generate a helpful executive summary for a layman patient about their {category} report.
        
        Based on the patient's genetic profile: {mutations_summary}
        
        Provide:
        - Key findings in plain English
        - Helpful, encouraging verbiage
        - Primary recommendations
        - Risk highlights
        - Action items

        CRITICAL REQUIREMENT: DO NOT use the word "Urgent". Instead, use priority levels like "Critical", "Highly Recommended", or "Important Next Steps". Any text that represents high risk must be bolded.
        CRITICAL REQUIREMENT 2: Explicitly state how the patient's risk from the condition is increased relative to the population average (e.g., patient's lifetime risk percentage compared to the average population risk percentage).
        
        Return JSON:
        {{
            "key_findings": ["Finding 1", "Finding 2"],
            "primary_recommendations": ["Recommendation 1", "Recommendation 2"],
            "risk_highlights": "Brief risk summary",
            "action_items": ["Action 1", "Action 2"],
            "summary_statement": "One sentence overall summary"
        }}
        """,
        "required_data": ["category", "mutations_summary"],
        "order": 2
    }
    
    MUTATION_PROFILE = {
        "template": "mutation_profile_block.html", 
        "llm_prompt": """
        Generate a TECHNICAL genetic profile summary for a healthcare provider.
        
        Mutations: {mutations_data}
        
        For each mutation, provide technical details:
        - Gene name and function
        - Variant interpretation
        - Clinical significance
        - Population frequency context
        - Protein change (e.g. p.Gly49Val)
        
        Return JSON:
        {{
            "summary": "Technical genetic profile summary",
            "mutations": [
                {{
                    "rsid": "rs123456",
                    "gene": "GENE_NAME",
                    "variant_type": "missense/nonsense/etc",
                    "clinical_significance": "pathogenic/benign/etc",
                    "interpretation": "Clinical mechanism",
                    "frequency": "Population frequency context",
                    "gene_function": "Biological pathway"
                }}
            ],
            "key_findings": ["Technical finding 1", "Technical finding 2"],
            "genetic_risk_summary": "Technical summary of risk alleles"
        }}
        """,
        "required_data": ["mutations_data", "category"],
        "order": 7
    }
    
    LITERATURE_EVIDENCE = {
        "template": "literature_evidence_block.html",
        "llm_prompt": """
        Generate a TECHNICAL research evidence section for a healthcare provider.
        Include hyperlinks to real studies (e.g. PubMed IDs or DOIs) where available.
        
        Papers: {literature_data}
        Patient genes: {patient_genes}
        
        Organize into:
        - Current research landscape
        - Gene-specific findings with evidence levels
        - Clinical study highlights
        
        Return JSON:
        {{
            "research_landscape": "Technical overview",
            "gene_specific_findings": [
                {{
                    "gene": "GENE_NAME",
                    "key_studies": ["Study citation with DOI/link - finding"],
                    "clinical_relevance": "Clinical mechanism",
                    "evidence_strength": "strong/moderate/limited"
                }}
            ],
            "clinical_studies": ["Citation with DOI/link - results"],
            "emerging_research": "Future directions",
            "evidence_quality": "Technical assessment",
            "research_gaps": ["Technical gap 1"]
        }}
        """,
        "required_data": ["literature_data", "patient_genes", "category"],
        "order": 8
    }
    
    RISK_ASSESSMENT = {
        "template": "risk_assessment_block.html",
        "llm_prompt": """
        Generate a TECHNICAL risk assessment for {category} labeled "Technical Risk Assessment".
        
        Genetic data: {mutations_data}
        Literature evidence: {literature_summary}
        
        Provide:
        - Overall risk level
        - Contributing factors
        - Risk timeline

        CRITICAL REQUIREMENT: DO NOT use the word "Urgent". Instead, use priority levels like "Critical", "Highly Recommended", or "Important Next Steps". Any text that represents high risk must be bolded.
        CRITICAL REQUIREMENT 2: Explicitly state how the patient's risk from the condition is increased relative to the population average (e.g., patient's lifetime risk percentage compared to the average population risk percentage).
        
        Return JSON:
        {{
            "overall_risk": "low/moderate/high",
            "risk_percentage": "Estimated percentage if available",
            "contributing_factors": [
                {{
                    "factor": "Factor name",
                    "impact": "high/moderate/low",
                    "modifiable": true,
                    "description": "Technical basis"
                }}
            ],
            "risk_timeline": "TECHNICAL risk projection",
            "confidence_level": "high/moderate/low",
            "risk_summary": "Technical interpretation"
        }}
        """,
        "required_data": ["mutations_data", "literature_summary", "category"],
        "order": 6
    }
    
    CLINICAL_IMPLICATIONS = {
        "template": "clinical_implications_block.html",
        "llm_prompt": """
        Generate clinical implications and TREATMENT information for {category}.
        Include a section on "Known Medications & Treatments".
        
        Genetic findings: {mutations_data}
        Risk assessment: {risk_data}
        
        Include:
        - Treatment considerations
        - Known Drugs:
          * Explain that treatment is often combined.
          * Medications often target different problems.
          * Response varies between individuals.
          * Medication choices change over time.
          * Provide informational context about commonly prescribed drugs for {category} risk (e.g. condition-specific targeted therapies if applicable).
        - Miscellaneous items helpful to the end user.

        CRITICAL REQUIREMENT: DO NOT use the word "Urgent". Instead, use priority levels like "Critical", "Highly Recommended", or "Important Next Steps". Any text that represents high risk must be bolded.
        
        Return JSON:
        {{
            "treatment_considerations": [
                {{
                    "area": "Treatment area",
                    "recommendation": "Layman recommendation"
                }}
            ],
            "known_drugs": {{
                "info": "General context about combinations and variability",
                "medications": [
                    {{
                        "name": "Drug Class/Name",
                        "purpose": "What it targets",
                        "considerations": "Informational note"
                    }}
                ]
            }},
            "miscellaneous": ["Helpful tip 1", "Helpful tip 2"],
            "screening_recommendations": [
                {{
                    "test": "Screening test",
                    "frequency": "How often",
                    "rationale": "Layman rationale"
                }}
            ]
        }}
        """,
        "required_data": ["mutations_data", "risk_data", "category"],
        "order": 5
    }
    
    LIFESTYLE_RECOMMENDATIONS = {
        "template": "lifestyle_recommendations_block.html",
        "llm_prompt": """
        Generate "{category} Lifestyle Recommendations" for risk reduction.
        
        Genetic profile: {mutations_data}
        Risk factors: {risk_data}
        
        Include evidence-based recommendations for:
        - Diet modifications
        - Exercise
        - Smoking/Alcohol (if relevant to {category})
        - Environmental factors
        
        CRITICAL REQUIREMENT: Under "overall approach" in your lifestyle_summary, you MUST explicitly state how the patient's risk from the condition is increased relative to the population average (e.g., "cumulative risk of 40% compared to a population average of 1.5%").
        
        Return JSON:
        {{
            "diet_recommendations": [
                {{
                    "recommendation": "Advice",
                    "rationale": "Layman rationale"
                }}
            ],
            "exercise_recommendations": [
                {{
                    "type": "Exercise type",
                    "frequency": "How often",
                    "specific_benefits": "Why beneficial"
                }}
            ],
            "lifestyle_summary": "Overall approach"
        }}
        """,
        "required_data": ["mutations_data", "risk_data", "category"],
        "order": 3
    }

    MONITORING_PLAN = {
        "template": "monitoring_plan_block.html",
        "llm_prompt": """
        Generate a monitoring plan for {category}.
        
        Genetic risk: {risk_data}
        
        Include:
        - Warning signs in plain English.
        - Follow-up schedule.

        CRITICAL REQUIREMENT: DO NOT use the word "Urgent". Instead, use priority levels like "Critical", "Highly Recommended", or "Important Next Steps". Any text that represents high risk must be bolded.
        
        Return JSON:
        {{
            "warning_signs": ["Sign 1", "Sign 2"],
            "follow_up_schedule": [
                {{
                    "timepoint": "Timeframe",
                    "assessments": ["Assessment 1"],
                    "focus": "Layman focus"
                }}
            ],
            "summary": "Plan summary"
        }}
        """,
        "required_data": ["risk_data", "category"],
        "order": 4
    }
    
    RESEARCH_OPPORTUNITIES = {
        "template": "research_opportunities_block.html",
        "llm_prompt": """
        Identify research opportunities for {category} relevant to the patient's genetic profile:
        
        Patient genes: {patient_genes}
        Current research: {literature_data}
        
        Include:
        - Clinical trials
        - Research studies
        - Biobanks
        - Future therapies
        
        Return JSON:
        {{
            "clinical_trials": [
                {{
                    "title": "Trial name",
                    "phase": "Phase I/II/III",
                    "eligibility": "Relevant eligibility criteria",
                    "focus": "What the trial is studying"
                }}
            ],
            "research_studies": [
                {{
                    "study_type": "Observational/Genetic/etc",
                    "focus": "Study focus",
                    "relevance": "Why relevant to patient"
                }}
            ],
            "biobank_opportunities": ["Biobank 1", "Biobank 2"],
            "emerging_therapies": [
                {{
                    "therapy": "Therapy name",
                    "target": "What it targets",
                    "timeline": "Expected availability",
                    "relevance": "Why relevant"
                }}
            ],
            "research_summary": "Overall research landscape"
        }}
        """,
        "required_data": ["patient_genes", "literature_data", "category"],
        "order": 9
    }

    CONCLUSION = {
        "template": "conclusion_block.html",
        "llm_prompt": """
        Generate a concluding section for a precision medicine report focused on {category}.
        
        Include:
        - Summary of the clinical significance of findings
        - Next steps for the patient and provider
        - Encouraging final remarks about the value of personalized medicine
        
        Return JSON:
        {{
            "conclusion_summary": "A cohesive summary of the report's main takeaways",
            "next_steps": ["Step 1", "Step 2", "Step 3"],
            "closing_remarks": "Final encouraging statement"
        }}
        """,
        "required_data": ["category"],
        "order": 11
    }