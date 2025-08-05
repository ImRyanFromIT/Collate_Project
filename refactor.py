#!/usr/bin/env python3
import json
import sys
import os
import pandas as pd
from functools import lru_cache
from datetime import datetime, timedelta
import argparse
import glob
import re

# Load configuration
def load_config():
    """Load configuration from config.json"""
    with open('config.json', 'r') as f:
        return json.load(f)

CONFIG = load_config()

# Cache implementation
class SimpleCache:
    def __init__(self, ttl_seconds=3600):
        self._cache = {}
        self._ttl = timedelta(seconds=ttl_seconds)
    
    def get(self, key):
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now() - timestamp < self._ttl:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key, value):
        self._cache[key] = (value, datetime.now())
    
    def clear(self):
        self._cache.clear()

# Initialize cache
cache = SimpleCache(ttl_seconds=CONFIG['cache']['ttl_seconds'])

def parse_ticket(ticket_file_path):
    """
    Extract hostnames from local .txt ticket file.
    Input: Path to .txt file containing ticket description
    Returns: {"hostnames": ["hostname1", "hostname2", ...]}
    """
    try:
        # Read the ticket file
        with open(ticket_file_path, 'r', encoding='utf-8') as f:
            description = f.read()
        
        # If no content, return empty
        if not description.strip():
            return {"hostnames": []}
        
        # Pattern to match "Server: hostname" (case insensitive)
        pattern = r'Server:\s*([^\s\n]+)'
        
        # Find all hostnames
        hostnames = re.findall(pattern, description, re.IGNORECASE)
        
        # Clean up hostnames (remove empty strings, strip whitespace)
        hostnames = [hostname.strip() for hostname in hostnames if hostname.strip()]
        
        # Remove duplicates while preserving order
        unique_hostnames = []
        for hostname in hostnames:
            if hostname not in unique_hostnames:
                unique_hostnames.append(hostname)
        
        return {"hostnames": unique_hostnames}
    
    except FileNotFoundError:
        return {"hostnames": [], "error": f"Ticket file not found: {ticket_file_path}"}
    except Exception as e:
        return {"hostnames": [], "error": str(e)}

def get_support_group(hostname, use_cache=True):
    """
    Find support group for a hostname from CSV file.
    CSV format: hostname (column 1), support_group (column 7)
    Returns: {"hostname": str, "support_group": str|None, "found": bool}
    """
    # Check cache first
    if use_cache and CONFIG['cache']['enabled']:
        cached_result = cache.get(f"support_group:{hostname}")
        if cached_result is not None:
            return cached_result
    
    try:
        # Get CSV file path from config
        csv_file_path = CONFIG['csv_files']['assets_csv']
        
        # Read CSV file using pandas
        df = pd.read_csv(csv_file_path)
        
        # Ensure we have enough columns
        if len(df.columns) < 7:
            return {"hostname": hostname, "support_group": None, "found": False, "error": "CSV file has insufficient columns"}
        
        # Search for hostname in column 1 (index 0) - case insensitive
        hostname_match = df[df.iloc[:, 0].str.strip().str.upper() == hostname.strip().upper()]
        
        if not hostname_match.empty:
            # Get the support group from column 7 (index 6)
            support_group = hostname_match.iloc[0, 6] if pd.notna(hostname_match.iloc[0, 6]) else None
            
            result = {
                "hostname": hostname,
                "support_group": support_group,
                "found": True
            }
            
            # Cache the result
            if CONFIG['cache']['enabled']:
                cache.set(f"support_group:{hostname}", result)
            
            return result
        
        # Not found
        result = {"hostname": hostname, "support_group": None, "found": False}
        if CONFIG['cache']['enabled']:
            cache.set(f"support_group:{hostname}", result)
        return result
        
    except FileNotFoundError:
        return {"hostname": hostname, "support_group": None, "found": False, "error": f"CSV file not found: {CONFIG['csv_files']['assets_csv']}"}
    except KeyError as e:
        return {"hostname": hostname, "support_group": None, "found": False, "error": f"Configuration missing: {str(e)}"}
    except Exception as e:
        return {"hostname": hostname, "support_group": None, "found": False, "error": str(e)}

def process_ticket(ticket_file_path):
    """
    Main processing function: parse ticket file and collate results by support group.
    Input: Path to ticket .txt file
    """
    # Step 1: Parse ticket
    parse_result = parse_ticket(ticket_file_path)
    
    hostnames = parse_result.get('hostnames', [])
    
    if not hostnames:
        return {
            "status": "success",
            "message": "No hostnames found in ticket",
            "results": {},
            "errors": parse_result.get('error', {})
        }
    
    # Step 2: Process hostnames and group by support group
    groups = {}
    not_found = []
    
    for hostname in hostnames:
        # Get support group
        support_info = get_support_group(hostname)
        
        if not support_info['found']:
            not_found.append(hostname)
            continue
        
        support_group = support_info['support_group']
        
        # Group results
        if support_group not in groups:
            groups[support_group] = {
                "hostnames": [],
                "support_group_name": support_group
            }
        
        groups[support_group]["hostnames"].append(hostname)
    
    # Step 3: Create summary
    return {
        "status": "success",
        "summary": {
            "total_hostnames": len(hostnames),
            "grouped_into": len(groups),
            "not_found": len(not_found)
        },
        "results": groups,
        "errors": {
            "hostnames_not_found": not_found
        }
    }

def process_batch_tickets(file_patterns):
    """
    Process multiple ticket files and aggregate all hostnames together.
    Input: List of file patterns to process
    Returns: Aggregated results from all tickets
    """
    all_hostnames = []
    processed_files = []
    file_errors = []
    
    # Step 1: Collect all hostnames from all files
    for pattern in file_patterns:
        files = glob.glob(pattern)
        
        for file_path in files:
            try:
                parse_result = parse_ticket(file_path)
                hostnames = parse_result.get('hostnames', [])
                
                if hostnames:
                    all_hostnames.extend(hostnames)
                    processed_files.append(file_path)
                else:
                    processed_files.append(file_path)
                
                if 'error' in parse_result:
                    file_errors.append(f"{file_path}: {parse_result['error']}")
                    
            except Exception as e:
                file_errors.append(f"{file_path}: {str(e)}")
    
    # Remove duplicates while preserving order
    unique_hostnames = []
    for hostname in all_hostnames:
        if hostname not in unique_hostnames:
            unique_hostnames.append(hostname)
    
    if not unique_hostnames:
        return {
            "status": "success",
            "message": "No hostnames found in any ticket files",
            "files_processed": processed_files,
            "results": {},
            "errors": {
                "file_errors": file_errors,
                "hostnames_not_found": []
            }
        }
    
    # Step 2: Process all unique hostnames and group by support group
    groups = {}
    not_found = []
    
    for hostname in unique_hostnames:
        # Get support group
        support_info = get_support_group(hostname)
        
        if not support_info['found']:
            not_found.append(hostname)
            continue
        
        support_group = support_info['support_group']
        
        # Group results
        if support_group not in groups:
            groups[support_group] = {
                "hostnames": [],
                "support_group_name": support_group
            }
        
        groups[support_group]["hostnames"].append(hostname)
    
    # Step 3: Create aggregated summary
    return {
        "status": "success",
        "summary": {
            "files_processed": len(processed_files),
            "total_hostnames": len(unique_hostnames),
            "grouped_into": len(groups),
            "not_found": len(not_found)
        },
        "files_processed": processed_files,
        "results": groups,
        "errors": {
            "file_errors": file_errors,
            "hostnames_not_found": not_found
        }
    }

def format_results(results):
    """Format results for display"""
    output = []
    
    output.append("\n=== TICKET PROCESSING RESULTS ===\n")
    
    # Summary
    if 'summary' in results:
        if 'files_processed' in results['summary']:
            # Batch processing format
            output.append(f"Files Processed: {results['summary']['files_processed']}")
        output.append(f"Total Hostnames: {results['summary']['total_hostnames']}")
        output.append(f"Support Groups: {results['summary']['grouped_into']}")
        output.append(f"Not Found: {results['summary']['not_found']}\n")
    
    # Show processed files for batch results
    if 'files_processed' in results:
        output.append("Processed Files:")
        for file_path in results['files_processed']:
            output.append(f"  - {file_path}")
        output.append("")
    
    # Group details
    if results.get('results'):
        for group_name, group_data in results['results'].items():
            output.append(f"\n[{group_name}]")
            output.append(f"Hostnames: {', '.join(group_data['hostnames'])}")
    
    # Errors
    if results.get('errors', {}).get('hostnames_not_found'):
        output.append(f"\nHostnames not found: {', '.join(results['errors']['hostnames_not_found'])}")
    
    if results.get('errors', {}).get('file_errors'):
        output.append(f"\nFile errors:")
        for error in results['errors']['file_errors']:
            output.append(f"  - {error}")
    
    return '\n'.join(output)

def main():
    parser = argparse.ArgumentParser(description='Refactored Ticket Processing System - CSV Based')
    
    # Single ticket processing
    parser.add_argument('--ticket', type=str, help='Process a single ticket file (.txt)')
    
    # Batch processing
    parser.add_argument('--batch', nargs='+', help='Process multiple ticket files')
    
    # Lookup functions
    parser.add_argument('--lookup', type=str, help='Look up support group for a hostname')
    
    # Cache control
    parser.add_argument('--clear-cache', action='store_true', help='Clear the cache')
    
    # Output format
    parser.add_argument('--json', action='store_true', help='Output in JSON format')
    
    args = parser.parse_args()
    
    # Clear cache if requested
    if args.clear_cache:
        cache.clear()
        print("Cache cleared.")
        return
    
    # Single hostname lookup
    if args.lookup:
        result = get_support_group(args.lookup)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result['found']:
                print(f"Hostname: {result['hostname']}")
                print(f"Support Group: {result['support_group']}")
            else:
                print(f"Hostname '{args.lookup}' not found")
                if 'error' in result:
                    print(f"Error: {result['error']}")
        return
    
    # Single ticket processing
    if args.ticket:
        try:
            results = process_ticket(args.ticket)
            
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                print(format_results(results))
        
        except Exception as e:
            print(f"Error processing ticket: {str(e)}")
            sys.exit(1)
        return
    
    # Batch processing
    if args.batch:
        try:
            results = process_batch_tickets(args.batch)
            
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                print(format_results(results))
        
        except Exception as e:
            print(f"Error processing batch: {str(e)}")
            sys.exit(1)
        
        return
    
    # No arguments provided
    parser.print_help()

if __name__ == "__main__":
    main()
