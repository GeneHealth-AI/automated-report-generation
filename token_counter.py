import tiktoken
import json
import sys
import logging
from typing import Dict, Any, Union, List, Optional

# Configure logger
logger = logging.getLogger(__name__)

def count_tokens_in_string(text: str, model: str = "claude-3-sonnet-20240229") -> int:
    """
    Count the number of tokens in a string for a specific model.
    
    Args:
        text: The text to count tokens for
        model: The model name to use for token counting
    
    Returns:
        Number of tokens in the text
    """
    # For Claude models, use cl100k_base encoding which is close to Claude's tokenization
    if model.startswith("claude"):
        encoding = tiktoken.get_encoding("cl100k_base")
    # For GPT models, use their specific encodings
    elif "gpt-4" in model:
        encoding = tiktoken.encoding_for_model("gpt-4")
    elif "gpt-3.5" in model:
        encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    else:
        # Default to cl100k_base for unknown models
        encoding = tiktoken.get_encoding("cl100k_base")
    
    # Count tokens
    tokens = encoding.encode(text)
    return len(tokens)

def count_tokens_in_dict(data: Dict[str, Any], model: str = "claude-3-sonnet-20240229") -> Dict[str, Any]:
    """
    Count tokens in each field of a dictionary and the total.
    
    Args:
        data: Dictionary containing data for block generation
        model: The model name to use for token counting
    
    Returns:
        Dictionary with token counts for each field and total
    """
    result = {
        "fields": {},
        "total": 0
    }
    
    # Process each field in the dictionary
    for key, value in data.items():
        if isinstance(value, str):
            token_count = count_tokens_in_string(value, model)
            result["fields"][key] = {
                "tokens": token_count,
                "bytes": len(value.encode('utf-8'))
            }
            result["total"] += token_count
        elif isinstance(value, (dict, list)):
            # Convert to string for token counting
            value_str = json.dumps(value)
            token_count = count_tokens_in_string(value_str, model)
            result["fields"][key] = {
                "tokens": token_count,
                "bytes": len(value_str.encode('utf-8'))
            }
            result["total"] += token_count
        else:
            # Convert other types to string
            value_str = str(value)
            token_count = count_tokens_in_string(value_str, model)
            result["fields"][key] = {
                "tokens": token_count,
                "bytes": len(value_str.encode('utf-8'))
            }
            result["total"] += token_count
    
    # Add byte count for the total
    total_bytes = sum(field_data["bytes"] for field_data in result["fields"].values())
    result["total_bytes"] = total_bytes
    
    return result

def analyze_block_data(data: Dict[str, Any], model: str = "claude-3-sonnet-20240229") -> Dict[str, Any]:
    """
    Analyze token usage in block data and provide recommendations.
    
    Args:
        data: Dictionary containing data for block generation
        model: The model name to use for token counting
    
    Returns:
        Analysis results with token counts and recommendations
    """
    # Count tokens
    token_counts = count_tokens_in_dict(data, model)
    
    # Determine model limits
    model_limits = {
        "claude-3-opus-20240229": {"tokens": 200000, "bytes": 9000000},
        "claude-3-sonnet-20240229": {"tokens": 200000, "bytes": 9000000},
        "claude-3-haiku-20240307": {"tokens": 200000, "bytes": 9000000},
        "claude-3-5-sonnet-20240620": {"tokens": 200000, "bytes": 9000000},
        "gpt-4": {"tokens": 8192, "bytes": None},
        "gpt-4-turbo": {"tokens": 128000, "bytes": None},
        "gpt-3.5-turbo": {"tokens": 16385, "bytes": None}
    }
    
    # Get limits for the specified model, default to Claude Sonnet limits
    limits = model_limits.get(model, {"tokens": 200000, "bytes": 9000000})
    
    # Calculate percentages of limit used
    token_percentage = (token_counts["total"] / limits["tokens"]) * 100 if limits["tokens"] else 0
    byte_percentage = (token_counts["total_bytes"] / limits["bytes"]) * 100 if limits["bytes"] else 0
    
    # Add analysis information
    analysis = {
        "token_counts": token_counts,
        "model_info": {
            "name": model,
            "token_limit": limits["tokens"],
            "byte_limit": limits["bytes"]
        },
        "usage": {
            "tokens_used": token_counts["total"],
            "bytes_used": token_counts["total_bytes"],
            "token_percentage": token_percentage,
            "byte_percentage": byte_percentage
        },
        "status": "OK"
    }
    
    # Add warnings if approaching limits
    warnings = []
    if token_percentage > 90:
        warnings.append(f"TOKEN LIMIT WARNING: Using {token_percentage:.1f}% of available tokens")
    if byte_percentage > 90 and limits["bytes"]:
        warnings.append(f"BYTE LIMIT WARNING: Using {byte_percentage:.1f}% of available bytes")
    
    # Add recommendations if needed
    recommendations = []
    if token_percentage > 80 or byte_percentage > 80:
        # Find the largest fields
        sorted_fields = sorted(
            [(k, v["tokens"], v["bytes"]) for k, v in token_counts["fields"].items()],
            key=lambda x: x[1],
            reverse=True
        )
        
        # Recommend reducing the top 3 largest fields
        for field, tokens, bytes_count in sorted_fields[:3]:
            field_token_percentage = (tokens / token_counts["total"]) * 100
            if field_token_percentage > 10:  # Only suggest fields that are significant
                recommendations.append(f"Consider reducing '{field}' field ({field_token_percentage:.1f}% of tokens)")
    
    if warnings:
        analysis["warnings"] = warnings
        analysis["status"] = "WARNING"
    
    if recommendations:
        analysis["recommendations"] = recommendations
    
    return analysis

def print_token_analysis(data: Dict[str, Any], model: str = "claude-3-sonnet-20240229") -> None:
    """
    Print a formatted analysis of token usage.
    
    Args:
        data: Dictionary containing data for block generation
        model: The model name to use for token counting
    """
    analysis = analyze_block_data(data, model)
    
    print("\n" + "="*60)
    print(f"TOKEN ANALYSIS FOR {model}")
    print("="*60)
    
    # Print usage summary
    print(f"\nTOTAL TOKENS: {analysis['usage']['tokens_used']:,} / {analysis['model_info']['token_limit']:,} " +
          f"({analysis['usage']['token_percentage']:.1f}%)")
    
    if analysis['model_info']['byte_limit']:
        print(f"TOTAL BYTES:  {analysis['usage']['bytes_used']:,} / {analysis['model_info']['byte_limit']:,} " +
              f"({analysis['usage']['byte_percentage']:.1f}%)")
    
    # Print status
    status_color = "\033[91m" if analysis['status'] == "WARNING" else "\033[92m"  # Red for warning, green for OK
    print(f"\nSTATUS: {status_color}{analysis['status']}\033[0m")
    
    # Print warnings
    if "warnings" in analysis:
        print("\nWARNINGS:")
        for warning in analysis["warnings"]:
            print(f"  - \033[93m{warning}\033[0m")  # Yellow for warnings
    
    # Print recommendations
    if "recommendations" in analysis:
        print("\nRECOMMENDATIONS:")
        for rec in analysis["recommendations"]:
            print(f"  - {rec}")
    
    # Print top 5 largest fields
    print("\nLARGEST FIELDS:")
    sorted_fields = sorted(
        [(k, v["tokens"], v["bytes"]) for k, v in analysis["token_counts"]["fields"].items()],
        key=lambda x: x[1],
        reverse=True
    )
    
    for i, (field, tokens, bytes_count) in enumerate(sorted_fields[:5]):
        token_percentage = (tokens / analysis["usage"]["tokens_used"]) * 100
        print(f"  {i+1}. {field}: {tokens:,} tokens ({token_percentage:.1f}%), {bytes_count:,} bytes")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    # Example usage
    if len(sys.argv) > 1:
        # Read JSON file specified as command line argument
        try:
            with open(sys.argv[1], 'r') as f:
                data = json.load(f)
            model = sys.argv[2] if len(sys.argv) > 2 else "claude-3-sonnet-20240229"
            print_token_analysis(data, model)
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("Usage: python token_counter.py <json_file> [model_name]")
        print("Example: python token_counter.py block_data.json claude-3-sonnet-20240229")