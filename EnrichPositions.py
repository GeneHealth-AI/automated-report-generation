import csv
import sys
import json
import os
import anthropic
import google.generativeai as genai

def create_anthropic_client_safe(api_key=None, timeout=240.0):
    """Create Anthropic client with proxy error handling."""
    if api_key is None:
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    
    try:
        return anthropic.Anthropic(api_key=api_key, timeout=timeout)
    except TypeError as e:
        if "proxies" in str(e):
            # Temporarily clear proxy environment variables
            proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy']
            saved_vars = {}
            for var in proxy_vars:
                if var in os.environ:
                    saved_vars[var] = os.environ.pop(var)
            try:
                client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
                return client
            finally:
                for var, value in saved_vars.items():
                    os.environ[var] = value
        else:
            raise

GWAS_PATH = './gwas_catalog_v1.0.2-associations_e114_r2025-07-10.tsv'

def identify_relevant_rsids(rsid_list):
    '''
    Takesin a list of rsIDs and compares them to traits and diseases found through GWAS. Return dictionary mapping rsIDs to GWAS
    
    '''
    rsid2gwas = {}
    with open(GWAS_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            snp_field = row.get('STRONGEST SNP-RISK ALLELE') or row.get('SNP_ID_CURRENT') or ''
            for snp in (s.strip() for s in snp_field.split(',') if s.strip()):
                rsid2gwas[snp] = row
    matched_rsids = []
    for rsid in rsid_list:
        if rsid in rsid2gwas.keys():
            matched_rsids.append(rsid2gwas[rsid])
    return matched_rsids

def extract_mutations(vcf_path):
    mutations_formatted = set()
    with open(vcf_path,'r') as mutations:
        for line_num, line in enumerate(mutations, 1):
            try:
                line = line.split('\t')
                if len(line) < 4:
                    print(f"DEBUG: Line {line_num} has insufficient columns: {line}")
                    continue
                    
                rsid = line[0]
                allele_field = line[3]
                
                # Handle different allele formats
                if '/' in allele_field:
                    allele_parts = allele_field.split('/')
                    if len(allele_parts) == 2:
                        allele1, allele2 = allele_parts
                        mutations_formatted.add(rsid + '-' + allele1)
                        mutations_formatted.add(rsid + '-' + allele2.replace('\n',''))
                    else:
                        print(f"DEBUG: Line {line_num} has unexpected allele format: {allele_field}")
                        # Use the whole field as a single allele
                        mutations_formatted.add(rsid + '-' + allele_field.replace('\n',''))
                else:
                    # Single allele format
                    mutations_formatted.add(rsid + '-' + allele_field.replace('\n',''))
                    
            except Exception as e:
                print(f"DEBUG: Error processing line {line_num}: {e}")
                print(f"DEBUG: Line content: {line}")
                continue
                
    return list(mutations_formatted)

def create_gemini_model_safe():
    """
    Safely creates and configures a Gemini model instance.
    
    Retrieves the API key from the environment variable 'GEMINI_API_KEY'.
    
    Returns:
        A GenerativeModel instance or None if the API key is not found.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.")
        return None
    
    try:
        genai.configure(api_key=api_key)
        # Using gemini-3-flash-preview as it's fast and efficient for classification tasks
        model = genai.GenerativeModel('gemini-3-flash-preview')
        return model
    except Exception as e:
        print(f"Error configuring Gemini: {e}")
        return None

def enrich_positions(vcf_path, prompt, batch_size=500, p_value_threshold=0.05):
    """
    Looks at a list of rsIDs and determines mutations that have GWAS relevant to the report focus.
    Uses the Google Gemini API for relevance filtering.
    
    Returns only the requested fields: Disease/Trait, Strongest SNP-Risk Allele, PubMedID, 
    and Reported Gene(s). Filters entries by p-value significance.
    
    Args:
        vcf_path (str): Path to the VCF file.
        prompt (str): Focus topic for relevance filtering.
        batch_size (int): Number of entries to process in each batch.
        p_value_threshold (float): Maximum p-value to consider significant.
        
    Returns:
        list: A list of dictionaries containing relevant mutation information.
    """
    # 1. Get list of rsIDs with alleles from the VCF file
    rsid_list = extract_mutations(vcf_path)
    
    # 2. Find GWAS catalog entries for the present mutations
    mapped_rsIDs = identify_relevant_rsids(rsid_list)
    
    if not mapped_rsIDs:
        return []
    
    # 3. Filter entries by p-value significance first
    significant_entries = []
    for entry in mapped_rsIDs:
        p_value_str = entry.get('P-VALUE', '1.0')
        try:
            # This logic handles scientific notation like '5E-8' and other formats
            p_value = float(p_value_str)
            if p_value <= p_value_threshold:
                significant_entries.append(entry)
        except (ValueError, TypeError):
            # If p-value can't be parsed, we skip the entry
            continue
    
    if not significant_entries:
        return []
    
    # 4. Create Gemini model instance
    model = create_gemini_model_safe()
    if not model:
        return [] # Stop if the model couldn't be initialized
        
    generation_config = genai.types.GenerationConfig(
        temperature=0,      # For deterministic, consistent output
        max_output_tokens=1024 # Set a reasonable limit for the list of numbers
    )
    
    relevant_rsIDs = []
    
    # 5. Process significant entries in batches using the Gemini API
    for i in range(0, len(significant_entries), batch_size):
        batch = significant_entries[i:i+batch_size]
        
        # Create a numbered list of diseases for the LLM to evaluate
        disease_list = [f"{j+1}. {entry['DISEASE/TRAIT']}" for j, entry in enumerate(batch)]
        diseases_text = "\n".join(disease_list)
        
        # This prompt is adapted for Gemini, merging the system and user prompts
        batch_prompt = f"""You are a precision medicine and disease expert. Your task is to evaluate genetic associations for clinical relevance with extreme precision.

FOCUS TOPIC: {prompt}

STRICT CRITERIA FOR INCLUSION:
- The disease/trait must be DIRECTLY and CLINICALLY related to the focus topic.
- It must have a clear clinical or pathophysiological connection.
- Exclude general traits like "height", "weight", "BMI" unless specifically relevant.
- Exclude broad categories like "metabolic traits" unless the focus is metabolism.
- Only include the association if a specialist in the focus area would find it clinically actionable.

DISEASES/TRAITS TO EVALUATE:
{diseases_text}

INSTRUCTIONS:
- Be very selective; err on the side of exclusion.
- Return ONLY the numbers of the diseases that meet these strict criteria, separated by commas.
- If none meet the criteria, return the word "NONE".

Example Format: 1, 3, 7, 12"""
        
        try:
            response = model.generate_content(
                batch_prompt,
                generation_config=generation_config,
                request_options={"timeout": 600}
            )
            response_text = response.text.strip()
            
            # 6. Parse the response and collect relevant entries
            if response_text.upper() != "NONE":
                relevant_numbers = parse_relevant_numbers(response_text)
                
                for num in relevant_numbers:
                    if 1 <= num <= len(batch):  # Validate number is in range
                        entry = batch[num - 1]
                        filtered_entry = {
                            'DISEASE/TRAIT': entry.get('DISEASE/TRAIT', 'N/A'),
                            'STRONGEST SNP-RISK ALLELE': entry.get('STRONGEST SNP-RISK ALLELE', 'N/A'),
                            'PUBMEDID': entry.get('PUBMEDID', 'N/A'),
                            'REPORTED GENE(S)': entry.get('REPORTED GENE(S)', 'N/A')
                        }
                        relevant_rsIDs.append(filtered_entry)
            
        except Exception as e:
            print(f"Error processing batch with Gemini API: {e}")
            # If you have a fallback function, you could call it here.
            # For now, we'll just skip the batch on error.
            continue
            
    return relevant_rsIDs



def parse_relevant_numbers(response_text):
    """
    Parse the response to extract relevant disease numbers.
    Handles various response formats.
    """
    relevant_numbers = []
    
    # Clean the response
    response_text = response_text.replace('\n', ' ').replace('\r', ' ')
    
    # Extract numbers using regex
    import re
    numbers = re.findall(r'\b\d+\b', response_text)
    
    for num_str in numbers:
        try:
            num = int(num_str)
            if num > 0:  # Only positive numbers
                relevant_numbers.append(num)
        except ValueError:
            continue
    
    return relevant_numbers


def process_batch_individually(batch, prompt, client):
    """
    Fallback function to process a batch individually if batch processing fails.
    """
    relevant_entries = []
    
    for entry in batch:
        disease = entry['DISEASE/TRAIT']
        try:
            message = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                temperature=0,
                messages=[
                    {"role": "user", "content": f"Here is a disease and a focus. If the disease is relevant to the focus return only TRUE else return FALSE. Disease: {disease} Focus: {prompt}"}
                ]
            )
            
            if 'TRUE' in message.content[0].text:
                relevant_entries.append(entry)
                
        except Exception as e:
            print(f"Error processing individual disease '{disease}': {e}")
            continue
    
    return relevant_entries


def process_batch_individually_filtered(batch, prompt, client, p_value_threshold=0.05):
    """
    Fallback function to process a batch individually if batch processing fails.
    Returns only the requested fields: Disease/Trait, Strongest SNP-Risk Allele, PubMedID, 
    and Reported Gene(s). Filters entries by p-value significance.
    
    Args:
        batch: List of entries to process
        prompt: Focus topic for relevance filtering
        client: Anthropic client instance
        p_value_threshold: Maximum p-value to consider significant (default: 0.05)
    """
    relevant_entries = []
    
    for entry in batch:
        # First check if p-value is significant
        p_value_str = entry.get('P-VALUE', '')
        try:
            # Handle scientific notation (e.g., "5E-8") and regular decimals
            if 'E' in p_value_str.upper() or 'e' in p_value_str:
                p_value = float(p_value_str)
            else:
                # Handle values like "5 × 10^-8" or similar text formats
                p_value_str = p_value_str.replace('×', '*').replace('^', '**')
                # Try to evaluate the expression if it contains math operators
                if any(op in p_value_str for op in ['*', '/']):
                    # Use safer approach for math expressions
                    import re
                    # Extract just the numbers
                    numbers = re.findall(r'[\d.]+', p_value_str)
                    if len(numbers) >= 1:
                        p_value = float(numbers[0])
                        # If it contains scientific notation indicators, make it very small
                        if '10-' in p_value_str or '10^-' in p_value_str:
                            p_value = p_value * 1e-10  # Approximate small value
                    else:
                        p_value = 1.0  # Default if parsing fails
                else:
                    p_value = float(p_value_str)
                    
            # Skip entries with non-significant p-values
            if p_value > p_value_threshold:
                continue
                
        except (ValueError, SyntaxError):
            # If p-value can't be parsed, skip this entry
            continue
        
        disease = entry['DISEASE/TRAIT']
        try:
            message = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                temperature=0,
                messages=[
                    {"role": "user", "content": f"Here is a disease and a focus. If the disease is relevant to the focus return only TRUE else return FALSE. Disease: {disease} Focus: {prompt}"}
                ]
            )
            
            if 'TRUE' in message.content[0].text:
                # Extract only the requested fields (excluding P-VALUE)
                filtered_entry = {
                    'DISEASE/TRAIT': entry.get('DISEASE/TRAIT', ''),
                    'STRONGEST SNP-RISK ALLELE': entry.get('STRONGEST SNP-RISK ALLELE', ''),
                    'PUBMEDID': entry.get('PUBMEDID', ''),
                    'REPORTED GENE(S)': entry.get('REPORTED GENE(S)', '')
                }
                relevant_entries.append(filtered_entry)
                
        except Exception as e:
            print(f"Error processing individual disease '{disease}': {e}")
            continue
    
    return relevant_entries


# Optional: Add rate limiting to respect API limits
import time

def enrich_positions_with_rate_limit(vcf_path, prompt, batch_size=50, delay=1):
    """
    Version with rate limiting between API calls.
    """
    rsid_list = extract_mutations(vcf_path)
    mapped_rsIDs = identify_relevant_rsids(rsid_list)
    
    if not mapped_rsIDs:
        return []
    
    # Create Anthropic client using the safe method
    client = create_anthropic_client_safe()
    
    relevant_rsIDs = []
    
    for i in range(0, len(mapped_rsIDs), batch_size):
        batch = mapped_rsIDs[i:i+batch_size]
        
        # Create numbered list of diseases for this batch
        disease_list = []
        for j, entry in enumerate(batch):
            disease = entry['DISEASE/TRAIT']
            disease_list.append(f"{j+1}. {disease}")
        
        diseases_text = "\n".join(disease_list)
        
        batch_prompt = f"""Here is a focus topic and a list of diseases/traits. 
For each disease, determine if it's relevant to the focus topic. Please adhere to the focus; if it is only tangentially related do not include it. Choose ONLY the most relevant diseases not irrelvalent ones. 

Focus: {prompt}

Diseases/Traits:
{diseases_text}

Return only the numbers of diseases that are relevant to the focus (comma-separated).
If none are relevant, return "NONE".
Example: 1, 3, 7, 12"""
        
        try:
            message = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                temperature=0,
                messages=[{"role": "user", "content": batch_prompt}]
            )
            
            response_text = message.content[0].text.strip()
            
            if response_text.upper() != "NONE":
                relevant_numbers = parse_relevant_numbers(response_text)
                
                for num in relevant_numbers:
                    if 1 <= num <= len(batch):
                        relevant_rsIDs.append(batch[num-1])
            
            # Rate limiting
            if i + batch_size < len(mapped_rsIDs):  # Don't delay after last batch
                time.sleep(delay)
                
        except Exception as e:
            print(f"Error processing batch {i//batch_size + 1}: {e}")
            relevant_rsIDs.extend(process_batch_individually(batch, prompt, client))
    
    return relevant_rsIDs
